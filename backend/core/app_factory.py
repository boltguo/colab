"""FastAPI application factory for same-origin Web Studio static hosting and Colab native proxy."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import AppSettings
from .gpu import probe_gpu_stats, probe_host_stats
from .models import (
    AccessMode,
    PresetItem,
    SystemStatusResponse,
    TaskListResponse,
    TaskResponse,
    UploadedFileResponse,
)
from .security import ensure_safe_path, same_origin
from .storage import MediaStorage
from .task_manager import ProgressCallback, TaskManager

_DISABLED_GATEWAY_PATHS = frozenset(
    {"docs", "redoc", "openapi.json", "auth/login", "auth/logout", "auth/api-key"}
)
_COLAB_PROXY_SUFFIXES = (".colab.dev", ".colab.googleusercontent.com")


@dataclass
class FeaturePlugin:
    name: str
    title: str
    subtitle: str
    engine: str
    version: str
    validate_params: Callable[[Dict[str, Any]], Dict[str, Any]]
    execute: Callable[[Dict[str, Any], MediaStorage, AppSettings, ProgressCallback], Dict[str, Any]]
    register_presets: Optional[Callable[[MediaStorage], None]] = None
    build_router: Optional[Callable[[TaskManager, MediaStorage, AppSettings], APIRouter]] = None
    on_shutdown: Optional[Callable[[], None]] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)


def _read_spa_index(index_path: Path) -> str:
    return index_path.read_text(encoding="utf-8", errors="replace")


def _origin_from_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url.strip())
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw_url.strip().rstrip("/")


def create_feature_app(plugin: FeaturePlugin, settings: Optional[AppSettings] = None) -> FastAPI:
    cfg = settings or AppSettings.from_env(feature_override=plugin.name)
    storage = MediaStorage(cfg.data_dir)
    if plugin.register_presets:
        plugin.register_presets(storage)

    def _run_task(params: Dict[str, Any], progress_cb: ProgressCallback) -> Dict[str, Any]:
        return plugin.execute(params, storage, cfg, progress_cb)

    task_manager = TaskManager(
        feature=plugin.name,
        executor=_run_task,
        data_dir=cfg.data_dir,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task_manager.start(asyncio.get_running_loop())
        try:
            yield
        finally:
            task_manager.stop()
            if plugin.on_shutdown:
                plugin.on_shutdown()

    app = FastAPI(
        title=f"{plugin.title} — Web Studio",
        description=plugin.subtitle,
        version=plugin.version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def _read_proxy_metadata() -> Tuple[str, Optional[AccessMode]]:
        proxy_file = cfg.data_dir / "proxy_info.json"
        if proxy_file.is_file() and not proxy_file.is_symlink():
            try:
                raw = json.loads(proxy_file.read_text(encoding="utf-8", errors="replace"))
                url_val = str(raw.get("public_url") or "").strip().rstrip("/")
                mode_val = str(raw.get("access_mode") or "").strip()
                resolved_mode: Optional[AccessMode] = (
                    mode_val if mode_val in ("local", "colab") else None  # type: ignore[assignment]
                )
                return (url_val if url_val and "<" not in url_val else ""), resolved_mode
            except Exception:
                pass
        return "", None

    def _allowed_origins() -> Tuple[str, ...]:
        candidates: List[str] = []
        if cfg.proxy_origin:
            candidates.append(_origin_from_url(cfg.proxy_origin))
        meta_url, _ = _read_proxy_metadata()
        if meta_url:
            candidates.append(_origin_from_url(meta_url))
        return tuple(dict.fromkeys(c for c in candidates if c))

    def _resolve_access_info(request: Request) -> Tuple[str, AccessMode]:
        public_url, meta_mode = _read_proxy_metadata()
        access_mode: AccessMode = meta_mode or "local"

        if cfg.proxy_origin:
            if not public_url:
                public_url = cfg.proxy_origin
            if access_mode == "local":
                access_mode = "colab"

        host_header = (
            (request.headers.get("x-forwarded-host") or request.headers.get("host") or "")
            .split(",")[0]
            .strip()
        )
        proto_header = (
            (request.headers.get("x-forwarded-proto") or request.url.scheme or "http")
            .split(",")[0]
            .strip()
        )
        hostname_only = host_header.split(":")[0].lower()

        if hostname_only.endswith(_COLAB_PROXY_SUFFIXES):
            access_mode = "colab"
            if host_header:
                public_url = public_url or f"{proto_header}://{host_header}".rstrip("/")

        if not public_url and host_header:
            public_url = f"{proto_header}://{host_header}".rstrip("/")

        return public_url, access_mode

    @app.middleware("http")
    async def web_only_guard_and_headers(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(
            request, extra_origins=_allowed_origins()
        ):
            return JSONResponse(
                {"detail": "仅允许从当前 Web 工作台同源发起请求。"},
                status_code=403,
            )
        response = await call_next(request)
        path = request.url.path
        if response.status_code == 200 and (
            path.startswith("/assets/") or path.endswith((".woff2", ".woff", ".ttf"))
        ):
            response.headers["Cache-Control"] = "private, max-age=604800, immutable, no-transform"
        elif response.headers.get("content-type", "").startswith("text/event-stream"):
            cc = response.headers.get("Cache-Control", "")
            if "no-transform" not in cc:
                response.headers["Cache-Control"] = f"{cc}, no-transform" if cc else "no-cache, no-transform"
        else:
            response.headers["Cache-Control"] = "private, no-store, no-transform"
        return response

    core_router = APIRouter(prefix="/api/v1", tags=["Core"])

    @core_router.get("/health", summary="轻量健康检查")
    async def health_check() -> Dict[str, Any]:
        return {"status": "ok", "feature": plugin.name, "version": plugin.version}

    @core_router.get("/system", response_model=SystemStatusResponse, summary="系统、GPU 显存与任务队列状态")
    async def get_system_status(request: Request) -> SystemStatusResponse:
        public_url, access_mode = _resolve_access_info(request)
        return SystemStatusResponse(
            feature=plugin.name,
            title=plugin.title,
            subtitle=plugin.subtitle,
            version=plugin.version,
            engine=plugin.engine,
            mock_mode=cfg.mock_inference,
            public_url=public_url,
            access_mode=access_mode,
            gpu=probe_gpu_stats(),
            host=probe_host_stats(cfg.data_dir),
            queue=task_manager.queue_stats(),
        )

    @core_router.get("/presets", response_model=List[PresetItem], summary="获取当前应用的内置示例素材列表")
    async def list_presets() -> List[PresetItem]:
        return storage.list_presets()

    @core_router.get("/presets/{preset_id}", summary="读取内置示例素材文件")
    async def get_preset_file(preset_id: str) -> FileResponse:
        path = storage.get_preset_path(preset_id)
        return FileResponse(path, filename=path.name)

    @core_router.post(
        "/files",
        response_model=UploadedFileResponse,
        summary="上传参考音频/图像/视频文件，获取 file_id",
    )
    async def upload_media_file(
        file: UploadFile = File(..., description="要上传的多媒体文件"),
    ) -> UploadedFileResponse:
        return await storage.save_upload(file)

    @core_router.get("/files/{file_id}", summary="读取已上传文件")
    async def get_uploaded_file(
        file_id: str,
        download: bool = Query(default=False, description="是否作为附件下载"),
    ) -> FileResponse:
        path = storage.get_upload_path(file_id)
        disposition = "attachment" if download else "inline"
        return FileResponse(
            path,
            filename=path.name,
            content_disposition_type=disposition,
        )

    @core_router.get("/outputs/{filename}", summary="下载或流式播放模型生成的输出文件")
    async def get_output_file(
        filename: str,
        download: bool = Query(default=False, description="是否作为附件下载"),
    ) -> FileResponse:
        path = storage.get_output_path(filename)
        disposition = "attachment" if download else "inline"
        return FileResponse(
            path,
            filename=path.name,
            content_disposition_type=disposition,
        )

    @core_router.get("/tasks", response_model=TaskListResponse, summary="获取最近任务列表")
    async def list_tasks(
        limit: int = Query(default=30, ge=1, le=100),
    ) -> TaskListResponse:
        return TaskListResponse(items=task_manager.list_recent(limit=limit))

    @core_router.get("/tasks/{task_id}", response_model=TaskResponse, summary="轮询单个任务状态与结果")
    async def get_task_status(task_id: str) -> TaskResponse:
        return task_manager.get(task_id)

    @core_router.delete("/tasks/{task_id}", response_model=TaskResponse, summary="取消排队中的任务")
    async def cancel_task(task_id: str) -> TaskResponse:
        return task_manager.cancel(task_id)

    @app.websocket("/api/v1/tasks/{task_id}/ws")
    async def stream_task_ws(websocket: WebSocket, task_id: str) -> None:
        if not same_origin(websocket, extra_origins=_allowed_origins()):
            await websocket.close(code=4403, reason="Forbidden")
            return
        await websocket.accept()
        sub_q = task_manager.subscribe(task_id)
        try:
            current = task_manager.get(task_id)
            await websocket.send_json(current.model_dump())
            if current.status in {"succeeded", "failed", "cancelled"}:
                return
            while True:
                try:
                    event = await asyncio.wait_for(sub_q.get(), timeout=20.0)
                    await websocket.send_json(event)
                    if event.get("status") in {"succeeded", "failed", "cancelled"}:
                        break
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping", "task_id": task_id})
        except HTTPException:
            await websocket.send_json({"error": f"任务不存在：{task_id}"})
        except WebSocketDisconnect:
            pass
        finally:
            task_manager.unsubscribe(task_id, sub_q)

    app.include_router(core_router)

    if plugin.build_router:
        feature_router = plugin.build_router(task_manager, storage, cfg)
        app.include_router(feature_router)

    # Mount static frontend dist if present
    dist_dir = cfg.dist_dir
    if dist_dir and dist_dir.is_dir():
        ensure_safe_path(dist_dir)
        index_file = ensure_safe_path(dist_dir / "index.html", stop_at=dist_dir)

        @app.get("/", include_in_schema=False)
        async def serve_spa_root():
            return HTMLResponse(
                content=_read_spa_index(index_file),
                headers={"Cache-Control": "private, no-store, no-transform, must-revalidate"},
            )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa_assets_or_fallback(full_path: str):
            normalized = full_path.strip("/")
            if full_path.startswith(("api/", "v1/")) or normalized in _DISABLED_GATEWAY_PATHS:
                return JSONResponse(status_code=404, content={"detail": "路由不存在"})
            candidate = (dist_dir / full_path).resolve()
            dist_resolved = dist_dir.resolve()
            if (
                str(candidate).startswith(str(dist_resolved) + "/")
                and candidate.is_file()
                and not candidate.is_symlink()
            ):
                return FileResponse(candidate)
            return HTMLResponse(
                content=_read_spa_index(index_file),
                headers={"Cache-Control": "private, no-store, no-transform, must-revalidate"},
            )
    else:
        @app.get("/", include_in_schema=False)
        async def serve_backend_only_placeholder():
            return JSONResponse(
                content={
                    "service": plugin.title,
                    "feature": plugin.name,
                    "note": "未检测到前端静态构建产物 dist/，仅 Web 工作台后端服务运行中。",
                }
            )

    return app
