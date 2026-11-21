"""FastAPI plugin registration for H3 Character Swap (Single & Multi-Person Studio)."""
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException

from backend.core.app_factory import FeaturePlugin
from backend.core.config import AppSettings
from backend.core.models import TaskResponse
from backend.core.storage import MediaStorage
from backend.core.task_manager import ProgressCallback, TaskManager
from .runner import (
    CLIP_FILENAME,
    SAM_CHECKPOINT_FILENAME,
    SWAP_LORA_FILENAME,
    TURBO_LORA_FILENAME,
    UNET_FILENAME,
    H3CharacterSwapRunner,
)
from .schemas import H3CharacterSwapGenerateRequest


class _RunnerHolder:
    """Thread-safe lazy holder binding H3CharacterSwapRunner to (data_dir, mock_mode)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: Optional[Tuple[Path, bool]] = None
        self._runner: Optional[H3CharacterSwapRunner] = None

    def get(
        self, storage: MediaStorage, settings: Optional[AppSettings] = None
    ) -> H3CharacterSwapRunner:
        data_dir = settings.data_dir.resolve() if settings else storage.base_dir.resolve()
        mock_mode = bool(settings.mock_inference) if settings else False
        key = (data_dir, mock_mode)
        with self._lock:
            if self._runner is None or self._key != key or self._runner.storage is not storage:
                self._runner = H3CharacterSwapRunner(
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


def _validate_swap_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    try:
        validated = H3CharacterSwapGenerateRequest.model_validate(raw)
        return validated.model_dump()
    except Exception as exc:
        raise ValueError(str(exc)) from exc


def _register_presets(_storage: MediaStorage) -> None:
    return None


def _execute_swap_task(
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
) -> APIRouter:
    runner = _RUNNER_HOLDER.get(storage, settings)
    router = APIRouter(prefix="/api/v1", tags=["H3 Character Swap"])

    @router.post(
        "/generate",
        response_model=TaskResponse,
        summary="异步提交 H3 单人 / 多人视频人物替换任务",
        description=(
            "基于 MiniMax-H3 Ref2VA INT8 + FL2V Turbo 8 步 + Character Swap V1.5 + SAM 3.1 自动人物跟踪遮罩（8 步 ER-SDE 采样），"
            "锁定原视频背景并重绘目标人物外观，保留动作表情与原声，支持可选关键帧锚点与多时间窗连续拼接。"
        ),
    )
    async def submit_generate(
        req: H3CharacterSwapGenerateRequest,
    ) -> TaskResponse:
        try:
            storage.resolve_input_ref(req.source_video)
            for slot in req.characters:
                storage.resolve_input_ref(slot.image)
            for guide in req.guide_frames:
                storage.resolve_input_ref(guide.image)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return task_manager.submit(req.model_dump())

    @router.get(
        "/models",
        summary="查询当前 H3 Character Swap 推理模型配置",
    )
    async def list_swap_models() -> Dict[str, object]:
        return {
            "models": [
                {
                    "id": "minimax_h3_ref2va_int8",
                    "filename": UNET_FILENAME,
                    "label": "MiniMax-H3 Ref2VA (INT8 ConvRot 基座模型)",
                    "recommended_for": ["单人人物替换", "多人同框分别替换"],
                },
                {
                    "id": "minimax_h3_fl2v_turbo_8step",
                    "filename": TURBO_LORA_FILENAME,
                    "label": "MiniMax-H3 FL2V Turbo (8 步 ER-SDE 加速 LoRA)",
                    "recommended_for": ["8 步高保真人物替换加速采样"],
                },
                {
                    "id": "h3_character_swap_v1_5",
                    "filename": SWAP_LORA_FILENAME,
                    "label": "Character Swap LoRA V1.5 (人物参考替换 LoRA)",
                    "recommended_for": ["单人/多人外观与服装完整替换", "保留原动作与音轨"],
                },
                {
                    "id": "sam3_1_multiplex",
                    "filename": SAM_CHECKPOINT_FILENAME,
                    "label": "SAM 3.1 Multiplex (人物跟踪与背景锁定遮罩)",
                    "recommended_for": ["自动检测并全程跟踪人物区域，锁死原背景"],
                },
                {
                    "id": "qwen3vl_32b_int8",
                    "filename": CLIP_FILENAME,
                    "label": "Qwen3-VL 32B H3 Multimodal Encoder (INT8 ConvRot)",
                    "recommended_for": ["源视频与参考人物图视觉+文本联合条件编码"],
                },
            ]
        }

    @router.post(
        "/model/release",
        summary="手动卸载模型并释放 GPU 显存",
    )
    async def release_loaded_models() -> Dict[str, Any]:
        runner.release_vram()
        return {"status": "ok", "feature": "h3-character-swap"}

    return router


H3_CHARACTER_SWAP_PLUGIN = FeaturePlugin(
    name="h3-character-swap",
    title="H3 Character Swap",
    subtitle="Character / Multi-Person Video Swap · Ref2VA + V1.5 + SAM 3.1",
    engine="Headless ComfyUI Worker (MiniMax-H3 Ref2VA INT8 + Turbo8 + Character Swap V1.5 + SAM 3.1)",
    version="0.1.0",
    validate_params=_validate_swap_params,
    execute=_execute_swap_task,
    register_presets=_register_presets,
    build_router=_build_router,
    on_shutdown=_RUNNER_HOLDER.release,
)
