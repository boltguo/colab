"""FastAPI plugin registration for H3 Character Swap (Single & Multi-Person Studio)."""
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from backend.core.app_factory import FeaturePlugin
from backend.core.config import AppSettings
from backend.core.models import TaskResponse
from backend.core.storage import MediaStorage
from backend.core.task_manager import ProgressCallback, TaskManager
from .runner import CLIP_FILENAME, UNET_FILENAME, H3CharacterSwapRunner
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
    auth_dep: Any,
) -> APIRouter:
    runner = _RUNNER_HOLDER.get(storage, settings)
    router = APIRouter(prefix="/api/v1", tags=["H3 Character Swap"])

    @router.post(
        "/generate",
        response_model=TaskResponse,
        summary="异步提交 H3 单人 / 多人视频人物替换任务",
        description=(
            "基于 Viggle Remake Swap (MiniMax-H3 FL2VA INT8 ConvRot · 6 步采样)，"
            "支持单人与多人视频人物替换、保留原始动作表情与音轨、可选关键帧锚点引导及多时间窗连续拼接。"
        ),
    )
    async def submit_generate(
        req: H3CharacterSwapGenerateRequest,
        _: None = Depends(auth_dep),
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
    async def list_swap_models(_: None = Depends(auth_dep)) -> Dict[str, object]:
        return {
            "models": [
                {
                    "id": "viggle_remake_swap_int8",
                    "filename": UNET_FILENAME,
                    "label": "Viggle Remake Swap (MiniMax-H3 FL2VA INT8 ConvRot · 6 步 Euler)",
                    "recommended_for": ["单人全身/风格跨次元人物替换", "多人同框分别替换与原声保留"],
                },
                {
                    "id": "qwen3vl_32b_int8",
                    "filename": CLIP_FILENAME,
                    "label": "Qwen3-VL 32B H3 Text Encoder (INT8 ConvRot)",
                    "recommended_for": ["多人物/六段式结构化替换描述编码"],
                },
            ]
        }

    @router.post(
        "/model/release",
        summary="手动卸载模型并释放 GPU 显存",
    )
    async def release_loaded_models(_: None = Depends(auth_dep)) -> Dict[str, Any]:
        runner.release_vram()
        return {"status": "ok", "feature": "h3-character-swap"}

    return router


H3_CHARACTER_SWAP_PLUGIN = FeaturePlugin(
    name="h3-character-swap",
    title="H3 Character Swap",
    subtitle="Character / Multi-Person Video Swap · Viggle Remake",
    engine="Headless ComfyUI Worker (Viggle Remake Swap INT8 ConvRot · MiniMax-H3 FL2VA)",
    version="0.1.0",
    validate_params=_validate_swap_params,
    execute=_execute_swap_task,
    register_presets=_register_presets,
    build_router=_build_router,
    on_shutdown=_RUNNER_HOLDER.release,
)
