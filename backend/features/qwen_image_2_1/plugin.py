"""FastAPI plugin registration for Qwen-Image 2.1 Studio + Dynamic LoRA Hot-Loader API."""
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
from .runner import QwenImageRunner
from .schemas import ASPECT_RATIOS, QwenImageGenerateRequest, compute_preset_dimensions


class _RunnerHolder:
    """Thread-safe lazy holder binding QwenImageRunner to the active app's (data_dir, mock_mode)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: Optional[Tuple[Path, bool]] = None
        self._runner: Optional[QwenImageRunner] = None

    def get(self, storage: MediaStorage, settings: Optional[AppSettings] = None) -> QwenImageRunner:
        data_dir = settings.data_dir.resolve() if settings else storage.base_dir.resolve()
        mock_mode = bool(settings.mock_inference) if settings else False
        key = (data_dir, mock_mode)
        with self._lock:
            if self._runner is None or self._key != key or self._runner.storage is not storage:
                self._runner = QwenImageRunner(
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


def _validate_qwen_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if raw.get("__task_kind__") == "lora_download":
            dl = LoraDownloadRequest.model_validate(raw.get("payload") or {})
            return {"__task_kind__": "lora_download", "payload": dl.model_dump()}
        validated = QwenImageGenerateRequest.model_validate(raw)
        return validated.model_dump()
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _register_presets(_storage: MediaStorage) -> None:
    # No synthetic demo images: users upload or paste their own reference images directly.
    return None


def _execute_qwen_task(
    params: Dict[str, Any],
    storage: MediaStorage,
    settings: AppSettings,
    progress_cb: ProgressCallback,
) -> Dict[str, Any]:
    runner = _RUNNER_HOLDER.get(storage, settings)
    return runner.execute_task(params, progress_cb)


def _build_router(
    task_manager: TaskManager,
    storage: MediaStorage,
    settings: AppSettings,
    auth_dep: Any,
) -> APIRouter:
    runner = _RUNNER_HOLDER.get(storage, settings)
    router = APIRouter(prefix="/api/v1", tags=["Qwen-Image 2.1"])

    @router.post(
        "/generate",
        response_model=TaskResponse,
        summary="异步提交 Qwen-Image 2.1 文生图 / 单图编辑 / 双图融合 / 多 LoRA 推理任务",
        description=(
            "统一支持原生 2K 文生图、单图指令精修、双图/多图主体场景融合、多 LoRA 动态叠加与在线热挂载。"
            "提交后立即返回 `task_id`，可通过 `WS /api/v1/tasks/{task_id}/ws` 或 `GET /api/v1/tasks/{task_id}` 获取实时采样步数进度。"
        ),
    )
    async def submit_generate(
        req: QwenImageGenerateRequest,
        _: None = Depends(auth_dep),
    ) -> TaskResponse:
        try:
            if req.mode != "t2i":
                for ref in req.effective_references():
                    storage.resolve_input_ref(ref)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return task_manager.submit(req.model_dump())

    @router.get(
        "/loras",
        response_model=LoraListResponse,
        summary="列出内置精选 LoRA 与当前实例已缓存的 .safetensors 权重",
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
        summary="删除已缓存的自定义/精选 LoRA 以释放实例磁盘空间",
    )
    async def remove_lora(
        filename: str,
        _: None = Depends(auth_dep),
    ) -> Dict[str, object]:
        return runner.lora_manager.delete_lora(filename)

    @router.get(
        "/resolution-presets",
        summary="查询 1K / 2K 各画幅精确像素宽高对照表",
    )
    async def get_resolution_presets(_: None = Depends(auth_dep)) -> Dict[str, object]:
        table = {}
        for tier in ("2K", "1K"):
            table[tier] = {
                ar: {"width": w, "height": h}
                for ar in ASPECT_RATIOS
                for w, h in [compute_preset_dimensions(tier, ar)]  # type: ignore[arg-type]
            }
        return {"presets": table}

    @router.post(
        "/model/release",
        summary="手动通知内部无头推理引擎卸载模型并释放 GPU 显存",
    )
    async def release_loaded_models(_: None = Depends(auth_dep)) -> Dict[str, Any]:
        runner.release_vram()
        return {"status": "ok", "feature": "qwen-image-2.1"}

    return router


QWEN_IMAGE_2_1_PLUGIN = FeaturePlugin(
    name="qwen-image-2.1",
    title="Qwen-Image 2.1 图像生成工作台",
    subtitle="原生 2K 文生图 · 图生图（可选多图参考） · 在线 LoRA 挂载",
    engine="Headless ComfyUI Worker (Qwen-Image 2.1 BF16 + Qwen3-VL-8B)",
    version="0.1.0",
    validate_params=_validate_qwen_params,
    execute=_execute_qwen_task,
    register_presets=_register_presets,
    build_router=_build_router,
    on_shutdown=_RUNNER_HOLDER.release,
)
