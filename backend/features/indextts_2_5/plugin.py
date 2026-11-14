"""FastAPI feature plugin registration for IndexTTS 2.5."""
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from backend.core.app_factory import FeaturePlugin
from backend.core.config import AppSettings
from backend.core.models import TaskResponse
from backend.core.storage import MediaStorage
from backend.core.task_manager import TaskManager
from .runner import ENGINE_MANAGER, execute_indextts_task
from .schemas import IndexTTSGenerateRequest

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _validate_indextts_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    try:
        validated = IndexTTSGenerateRequest.model_validate(raw)
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    return validated.model_dump()


def _register_presets(storage: MediaStorage) -> None:
    sample_mp3 = ASSETS_DIR / "ref_audio.mp3"
    if sample_mp3.is_file():
        storage.register_preset(
            preset_id="ref_audio",
            file_path=sample_mp3,
            label="内置示例参考音色 (ref_audio.mp3)",
            description="官方预置清晰普通话示例人声，可直接用于测试克隆或跨语种合成",
            kind="audio",
        )


def _build_router(
    task_manager: TaskManager,
    storage: MediaStorage,
    settings: AppSettings,
    auth_dep: Any,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["IndexTTS 2.5"])

    @router.post(
        "/generate",
        response_model=TaskResponse,
        summary="提交 IndexTTS 2.5 语音克隆/情感合成异步任务",
        description=(
            "统一支持零样本音色克隆、8 维情绪向量滑块、双参考音频情绪分离、以及自然语言情感描述（QwenEmotion）。"
            "提交后立即返回 `task_id`，可通过 `GET /api/v1/tasks/{task_id}` 轮询或连接 `WS /api/v1/tasks/{task_id}/ws` 获取实时进度。"
        ),
    )
    async def submit_indextts_generate(
        payload: IndexTTSGenerateRequest,
        _: None = Depends(auth_dep),
    ) -> TaskResponse:
        try:
            storage.resolve_input_ref(payload.speaker_audio)
            if payload.emotion_mode == "reference" and payload.emotion_audio:
                storage.resolve_input_ref(payload.emotion_audio)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return task_manager.submit(payload.model_dump())

    @router.post(
        "/model/release",
        summary="手动卸载已驻留显存中的 IndexTTS 2.5 模型实例",
    )
    async def release_loaded_models(_: None = Depends(auth_dep)) -> Dict[str, Any]:
        info = ENGINE_MANAGER.release()
        if info.get("busy"):
            raise HTTPException(status_code=409, detail="模型正在加载或合成语音，请在任务完成后释放显存。")
        return {"status": "ok", **info}

    return router


INDEXTTS_2_5_PLUGIN = FeaturePlugin(
    name="indextts-2.5",
    title="IndexTTS 2.5 语音合成工作台",
    subtitle="多语种音色克隆 · 情绪控制 · 音频与字幕导出",
    engine="Native IndexTTS-2.5 (PyTorch)",
    version="0.1.0",
    validate_params=_validate_indextts_params,
    execute=execute_indextts_task,
    register_presets=_register_presets,
    build_router=_build_router,
    on_shutdown=lambda: ENGINE_MANAGER.release(),
)
