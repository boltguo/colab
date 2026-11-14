"""FastAPI plugin registration for SeedVR2 Video & Image 4K Super-Resolution Studio."""
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from backend.core.app_factory import FeaturePlugin
from backend.core.config import AppSettings
from backend.core.models import TaskResponse
from backend.core.storage import MediaStorage
from backend.core.task_manager import ProgressCallback, TaskManager
from .runner import SeedVR2Runner
from .schemas import SeedVR2GenerateRequest


class _RunnerHolder:
    """Thread-safe lazy holder binding SeedVR2Runner to the active app's (data_dir, mock_mode)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: Optional[Tuple[Path, bool]] = None
        self._runner: Optional[SeedVR2Runner] = None

    def get(self, storage: MediaStorage, settings: Optional[AppSettings] = None) -> SeedVR2Runner:
        data_dir = settings.data_dir.resolve() if settings else storage.base_dir.resolve()
        mock_mode = bool(settings.mock_inference) if settings else False
        key = (data_dir, mock_mode)
        with self._lock:
            if self._runner is None or self._key != key or self._runner.storage is not storage:
                self._runner = SeedVR2Runner(
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


def _validate_seedvr2_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    try:
        validated = SeedVR2GenerateRequest.model_validate(raw)
        return validated.model_dump()
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _register_presets(_storage: MediaStorage) -> None:
    # Distraction-free input hygiene: users upload or paste their own videos/images directly.
    return None


def _execute_seedvr2_task(
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
    router = APIRouter(prefix="/api/v1", tags=["SeedVR2 Super-Resolution"])

    @router.post(
        "/generate",
        response_model=TaskResponse,
        summary="异步提交 SeedVR2 视频超分修复 / 图片 4K 超分任务",
        description=(
            "统一承载 SeedVR2 7B Sharp（旗舰锐化）与 3B Fast（长视频极速）全精度视频/图像超分修复，"
            "支持任意放大倍数、固定短边/长边档位、Split Latent 时间分块融合与 CIELAB/小波色彩对齐。"
            "提交后立即返回 `task_id`，可通过 `WS /api/v1/tasks/{task_id}/ws` 或 `GET /api/v1/tasks/{task_id}` 获取实时进度。"
        ),
    )
    async def submit_generate(
        req: SeedVR2GenerateRequest,
        _: None = Depends(auth_dep),
    ) -> TaskResponse:
        try:
            storage.resolve_input_ref(req.input_file)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return task_manager.submit(req.model_dump())

    @router.get(
        "/models",
        summary="查询当前内置的 SeedVR2 超分主模型规格说明",
    )
    async def list_seedvr2_models(_: None = Depends(auth_dep)) -> Dict[str, object]:
        return {
            "models": [
                {
                    "id": "7b_sharp",
                    "filename": "seedvr2_7b_sharp_fp16.safetensors",
                    "label": "SeedVR2 7B Sharp (FP16 · 15.35 GiB)",
                    "recommended_for": ["单图 4x 真 4K 细节重绘", "短视频高锐度超分修复"],
                },
                {
                    "id": "3b_fast",
                    "filename": "seedvr2_3b_fp16.safetensors",
                    "label": "SeedVR2 3B Fast (FP16 · 6.32 GiB)",
                    "recommended_for": ["长视频 2x/4x 高吞吐极速超分", "40GB 显卡配合 Split Latent"],
                },
            ]
        }

    @router.post(
        "/model/release",
        summary="手动通知内部无头推理引擎卸载模型并释放 GPU 显存",
    )
    async def release_loaded_models(_: None = Depends(auth_dep)) -> Dict[str, Any]:
        runner.release_vram()
        return {"status": "ok", "feature": "seedvr2"}

    return router


SEEDVR2_PLUGIN = FeaturePlugin(
    name="seedvr2",
    title="SeedVR2 超分修复工作台",
    subtitle="视频超分保原声 · 单图 4K 纹理重绘 · 7B Sharp / 3B Fast · A/B 滑动对比",
    engine="Headless ComfyUI Worker (SeedVR2 7B Sharp / 3B FP16 + EMA Tiled VAE)",
    version="0.1.0",
    validate_params=_validate_seedvr2_params,
    execute=_execute_seedvr2_task,
    register_presets=_register_presets,
    build_router=_build_router,
    on_shutdown=_RUNNER_HOLDER.release,
)
