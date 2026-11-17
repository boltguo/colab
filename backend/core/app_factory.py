"""FastAPI application factory with Cloudflare compatibility, SPA static hosting, and unified API."""
import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from .config import AppSettings
from .gpu import probe_gpu_stats, probe_host_stats
from .models import (
    GenericTaskCreateRequest,
    PresetItem,
    SystemStatusResponse,
    TaskListResponse,
    TaskResponse,
    TunnelMode,
    UploadedFileResponse,
)
from .security import AuthState, ensure_safe_path, make_auth_dependency, verify_ws_auth
from .web_access import install_web_access
from .storage import MediaStorage
from .task_manager import ProgressCallback, TaskManager


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
    build_router: Optional[Callable[[TaskManager, MediaStorage, AppSettings, Any], APIRouter]] = None
    on_shutdown: Optional[Callable[[], None]] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)


def _render_cf_safe_index(index_path: Path) -> str:
    html = index_path.read_text(encoding="utf-8", errors="replace")
    if 'data-cfasync="false"' not in html:
        html = html.replace("<script ", '<script data-cfasync="false" ')
    return html


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
        title=f"{plugin.title} — Web & API Service",
        description=plugin.subtitle,
        version=plugin.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    auth = AuthState(cfg.access_password, cfg.data_dir, cfg.api_key)
    install_web_access(app, auth)

    @app.middleware("http")
    async def cloudflare_safe_headers(request: Request, call_next):
        response = await call_next(request)
        if auth.access_password or auth.api_required:
            response.headers["Cache-Control"] = "private, no-store, no-transform"
            return response
        path = request.url.path
        if response.status_code == 200 and (
            path.startswith("/assets/") or path.endswith((".woff2", ".woff", ".ttf"))
        ):
            response.headers["Cache-Control"] = "public, max-age=604800, immutable, no-transform"
        else:
            cc = response.headers.get("Cache-Control", "")
            if "no-transform" not in cc:
                response.headers["Cache-Control"] = f"{cc}, no-transform" if cc else "no-transform"
        return response

    auth_dep = make_auth_dependency(auth)

    core_router = APIRouter(prefix="/api/v1", tags=["Core"])

    @core_router.get("/health", summary="轻量健康检查（免鉴权）")
    async def health_check() -> Dict[str, Any]:
        return {"status": "ok", "feature": plugin.name, "version": plugin.version}

    def _resolve_tunnel_info(request: Request) -> Tuple[str, TunnelMode]:
        public_url = ""
        tunnel_mode: TunnelMode = "local"

        tunnel_file = cfg.data_dir / "tunnel_info.json"
        if tunnel_file.is_file() and not tunnel_file.is_symlink():
            try:
                raw = json.loads(tunnel_file.read_text(encoding="utf-8", errors="replace"))
                url_val = str(raw.get("public_url") or "").strip().rstrip("/")
                mode_val = str(raw.get("tunnel_mode") or "").strip()
                if url_val and "<" not in url_val:
                    public_url = url_val
                if mode_val in ("quick", "custom", "local"):
                    tunnel_mode = mode_val  # type: ignore[assignment]
            except Exception:
                pass

        host_header = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
        proto_header = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
        hostname_only = host_header.split(":")[0].lower()

        if hostname_only and hostname_only not in ("127.0.0.1", "localhost", "::1"):
            req_origin = f"{proto_header}://{host_header}".rstrip("/")
            if hostname_only.endswith(".trycloudflare.com"):
                tunnel_mode = "quick"
                public_url = public_url or req_origin
            else:
                if tunnel_mode == "local":
                    tunnel_mode = "custom"
                if not public_url:
                    public_url = req_origin

        if not public_url and host_header:
            public_url = f"{proto_header}://{host_header}".rstrip("/")

        return public_url, tunnel_mode

    @core_router.get("/system", response_model=SystemStatusResponse, summary="系统、GPU 显存与任务队列状态")
    async def get_system_status(request: Request) -> SystemStatusResponse:
        public_url, tunnel_mode = _resolve_tunnel_info(request)
        return SystemStatusResponse(
            feature=plugin.name,
            title=plugin.title,
            subtitle=plugin.subtitle,
            version=plugin.version,
            engine=plugin.engine,
            auth_required=auth.api_required,
            web_auth_required=bool(cfg.access_password),
            api_key_configured=auth.api_key_configured,
            browser_authenticated=auth.browser_authenticated(request),
            mock_mode=cfg.mock_inference,
            public_url=public_url,
            tunnel_mode=tunnel_mode,
            gpu=probe_gpu_stats(),
            host=probe_host_stats(cfg.data_dir),
            queue=task_manager.queue_stats(),
        )

    @core_router.get("/presets", response_model=List[PresetItem], summary="获取当前应用的内置示例素材列表")
    async def list_presets(_: None = Depends(auth_dep)) -> List[PresetItem]:
        return storage.list_presets()

    @core_router.get("/presets/{preset_id}", summary="读取内置示例素材文件")
    async def get_preset_file(preset_id: str, _: None = Depends(auth_dep)) -> FileResponse:
        path = storage.get_preset_path(preset_id)
        return FileResponse(path, filename=path.name)

    @core_router.post(
        "/files",
        response_model=UploadedFileResponse,
        summary="上传参考音频/图像/视频文件，获取 file_id",
    )
    async def upload_media_file(
        file: UploadFile = File(..., description="要上传的多媒体文件"),
        _: None = Depends(auth_dep),
    ) -> UploadedFileResponse:
        return await storage.save_upload(file)

    @core_router.get("/files/{file_id}", summary="读取已上传文件")
    async def get_uploaded_file(
        file_id: str,
        download: bool = Query(default=False, description="是否作为附件下载"),
        _: None = Depends(auth_dep),
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
        _: None = Depends(auth_dep),
    ) -> FileResponse:
        path = storage.get_output_path(filename)
        disposition = "attachment" if download else "inline"
        return FileResponse(
            path,
            filename=path.name,
            content_disposition_type=disposition,
        )

    @core_router.post(
        "/tasks",
        response_model=TaskResponse,
        summary="通用异步任务提交接口（立即返回 task_id）",
    )
    async def create_generic_task(
        payload: GenericTaskCreateRequest,
        _: None = Depends(auth_dep),
    ) -> TaskResponse:
        try:
            validated = plugin.validate_params(payload.params)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return task_manager.submit(validated)

    @core_router.get("/tasks", response_model=TaskListResponse, summary="获取最近任务列表")
    async def list_tasks(
        limit: int = Query(default=30, ge=1, le=100),
        _: None = Depends(auth_dep),
    ) -> TaskListResponse:
        return TaskListResponse(items=task_manager.list_recent(limit=limit))

    @core_router.get("/tasks/{task_id}", response_model=TaskResponse, summary="轮询单个任务状态与结果")
    async def get_task_status(task_id: str, _: None = Depends(auth_dep)) -> TaskResponse:
        return task_manager.get(task_id)

    @core_router.delete("/tasks/{task_id}", response_model=TaskResponse, summary="取消排队中的任务")
    async def cancel_task(task_id: str, _: None = Depends(auth_dep)) -> TaskResponse:
        return task_manager.cancel(task_id)

    @app.websocket("/api/v1/tasks/{task_id}/ws")
    async def stream_task_ws(websocket: WebSocket, task_id: str) -> None:
        if not verify_ws_auth(websocket, auth):
            await websocket.close(code=4401, reason="Unauthorized")
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
        feature_router = plugin.build_router(task_manager, storage, cfg, auth_dep)
        app.include_router(feature_router)

    # Mount static frontend dist if present
    dist_dir = cfg.dist_dir
    if dist_dir and dist_dir.is_dir():
        ensure_safe_path(dist_dir)
        index_file = ensure_safe_path(dist_dir / "index.html", stop_at=dist_dir)

        @app.get("/", include_in_schema=False)
        async def serve_spa_root():
            html = _render_cf_safe_index(index_file)
            return HTMLResponse(
                content=html,
                headers={"Cache-Control": "no-store, no-transform, must-revalidate"},
            )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa_assets_or_fallback(full_path: str):
            if full_path.startswith(("api/", "v1/")):
                return JSONResponse(status_code=404, content={"detail": "API 路由不存在"})
            candidate = (dist_dir / full_path).resolve()
            dist_resolved = dist_dir.resolve()
            if (
                str(candidate).startswith(str(dist_resolved) + "/")
                and candidate.is_file()
                and not candidate.is_symlink()
            ):
                return FileResponse(candidate)
            html = _render_cf_safe_index(index_file)
            return HTMLResponse(
                content=html,
                headers={"Cache-Control": "no-store, no-transform, must-revalidate"},
            )
    else:
        @app.get("/", include_in_schema=False)
        async def serve_backend_only_placeholder():
            return JSONResponse(
                content={
                    "service": plugin.title,
                    "feature": plugin.name,
                    "docs": "/docs",
                    "note": "未检测到前端静态构建产物 dist/，API 服务正常运行中。",
                }
            )

    return app
