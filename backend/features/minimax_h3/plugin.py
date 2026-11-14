"""FastAPI plugin registration for MiniMax-H3 Joint Video + Audio Studio & Full-Parameter API."""
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from backend.core.app_factory import FeaturePlugin
from backend.core.config import AppSettings
from backend.core.lora_manager import LoraCatalogEntry, LoraDownloadRequest, LoraListResponse
from backend.core.models import TaskResponse
from backend.core.storage import MediaStorage
from backend.core.task_manager import ProgressCallback, TaskManager
from .runner import MiniMaxH3Runner
from .schemas import (
    ASPECT_RATIOS,
    MiniMaxH3GenerateRequest,
    NATIVE_FPS,
    compute_h3_dimensions,
    duration_to_h3_frames,
)


class _RunnerHolder:
    """Thread-safe lazy holder binding MiniMaxH3Runner to the active app's (data_dir, mock_mode)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: Optional[Tuple[Path, bool]] = None
        self._runner: Optional[MiniMaxH3Runner] = None

    def get(self, storage: MediaStorage, settings: Optional[AppSettings] = None) -> MiniMaxH3Runner:
        data_dir = settings.data_dir.resolve() if settings else storage.base_dir.resolve()
        mock_mode = bool(settings.mock_inference) if settings else False
        key = (data_dir, mock_mode)
        with self._lock:
            if self._runner is None or self._key != key or self._runner.storage is not storage:
                self._runner = MiniMaxH3Runner(
                    storage=storage,
                    data_dir=data_dir,
                    mock_mode=mock_mode,
                )
                self._key = key
            return self._runner

    def release(self) -> None:
        with self._lock:
            runner = self._runner
        if runner is not None:
            runner.release_vram()


_RUNNER_HOLDER = _RunnerHolder()


def _validate_h3_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if raw.get("__task_kind__") == "lora_download":
            dl = LoraDownloadRequest.model_validate(raw.get("payload") or {})
            return {"__task_kind__": "lora_download", "payload": dl.model_dump()}
        validated = MiniMaxH3GenerateRequest.model_validate(raw)
        return validated.model_dump()
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _register_presets(_storage: MediaStorage) -> None:
    # No synthetic demo images or videos: users upload or paste their own media directly.
    return None


def _execute_h3_task(
    params: Dict[str, Any],
    storage: MediaStorage,
    settings: AppSettings,
    progress_cb: ProgressCallback,
) -> Dict[str, Any]:
    runner = _RUNNER_HOLDER.get(storage, settings)
    return runner.execute_task(params, progress_cb)


def _validate_request_refs(req: MiniMaxH3GenerateRequest, storage: MediaStorage) -> None:
    for opt_ref in (req.first_frame, req.last_frame, req.guide_image, req.guide_audio):
        if opt_ref:
            storage.resolve_input_ref(opt_ref)
    if req.mode == "r2v":
        for img_ref in req.effective_ref_images():
            storage.resolve_input_ref(img_ref)
        for vid_slot in req.effective_ref_videos():
            storage.resolve_input_ref(vid_slot.file_id)
        for aud_ref in req.effective_ref_audios():
            storage.resolve_input_ref(aud_ref)


def _build_router(
    task_manager: TaskManager,
    storage: MediaStorage,
    settings: AppSettings,
    auth_dep: Any,
) -> APIRouter:
    runner = _RUNNER_HOLDER.get(storage, settings)
    router = APIRouter(prefix="/api/v1", tags=["MiniMax-H3"])

    @router.post(
        "/generate",
        response_model=TaskResponse,
        summary="异步提交 MiniMax-H3 文生视频 / 首尾帧视频 / 多模态参考音画生成任务",
        description=(
            "单接口统一支持文生音画视频 (`t2v`)、首帧或首尾帧图生视频 (`fl2v` / `i2v`)、多模态参考生视频 (`r2v`，支持 "
            "`<Picture N>` / `<Video K>` / `<Audio J>`)、8/4 步 Turbo 加速与自定义 LoRA 热挂载。"
            "提交后立即返回 `task_id`，可通过 `WS /api/v1/tasks/{task_id}/ws` 或 `GET /api/v1/tasks/{task_id}` 获取实时步数进度。"
        ),
    )
    async def submit_generate(
        req: MiniMaxH3GenerateRequest,
        _: None = Depends(auth_dep),
    ) -> TaskResponse:
        try:
            _validate_request_refs(req, storage)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return task_manager.submit(req.model_dump())

    @router.get(
        "/loras",
        response_model=LoraListResponse,
        summary="列出官方 Turbo LoRA 与当前实例已缓存的自定义 .safetensors 权重",
    )
    async def list_loras(_: None = Depends(auth_dep)) -> LoraListResponse:
        return runner.lora_manager.list_all()

    @router.post(
        "/loras/download",
        response_model=TaskResponse,
        summary="异步从 Hugging Face 或 HTTPS 直链下载并校验 .safetensors LoRA 权重",
    )
    async def download_lora(
        req: LoraDownloadRequest,
        _: None = Depends(auth_dep),
    ) -> TaskResponse:
        return task_manager.submit(
            {
                "__task_kind__": "lora_download",
                "payload": req.model_dump(),
            }
        )

    @router.post(
        "/loras/upload",
        response_model=LoraCatalogEntry,
        summary="上传本地 .safetensors LoRA 权重（含二进制头安全校验）",
    )
    async def upload_lora(
        file: UploadFile = File(...),
        _: None = Depends(auth_dep),
    ) -> LoraCatalogEntry:
        return await runner.lora_manager.save_upload(file)

    @router.delete(
        "/loras/{filename}",
        summary="删除已缓存的自定义 LoRA 以释放实例磁盘空间",
    )
    async def remove_lora(
        filename: str,
        _: None = Depends(auth_dep),
    ) -> Dict[str, object]:
        return runner.lora_manager.delete_lora(filename)

    @router.get(
        "/resolution-presets",
        summary="查询 MiniMax-H3 各分辨率档位画幅宽高与 17k+5 帧数网格对照表",
    )
    async def get_resolution_presets(_: None = Depends(auth_dep)) -> Dict[str, object]:
        res_table: Dict[str, Dict[str, Dict[str, int]]] = {}
        for tier in ("540p", "768p", "1080p"):
            res_table[tier] = {
                ar: {"width": w, "height": h}
                for ar in ASPECT_RATIOS
                for w, h in [compute_h3_dimensions(tier, ar)]
            }
        duration_grid = [
            {
                "requested_sec": sec,
                "aligned_frames": frames,
                "actual_sec": round(frames / float(NATIVE_FPS), 2),
            }
            for sec in (2, 3, 5, 8, 10, 12, 15)
            for frames in [duration_to_h3_frames(sec)]
        ]
        return {"resolutions": res_table, "duration_grid": duration_grid, "native_fps": NATIVE_FPS}

    @router.post(
        "/model/release",
        summary="手动通知内部无头推理引擎卸载模型并释放 GPU 显存",
    )
    async def release_loaded_models(_: None = Depends(auth_dep)) -> Dict[str, Any]:
        runner.release_vram()
        return {"status": "ok", "feature": "minimax-h3"}

    return router


MINIMAX_H3_PLUGIN = FeaturePlugin(
    name="minimax-h3",
    title="MiniMax-H3 音画视频工作台",
    subtitle="音画同步文生视频 · 首尾帧图生视频 · 多模态参考视频 · Turbo 加速与标准 API",
    engine="Headless ComfyUI Worker (MiniMax-H3 INT8 ConvRot + Qwen3-VL-32B)",
    version="0.1.0",
    validate_params=_validate_h3_params,
    execute=_execute_h3_task,
    register_presets=_register_presets,
    build_router=_build_router,
    on_shutdown=_RUNNER_HOLDER.release,
)
