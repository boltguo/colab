"""FeaturePlugin definition and Web Playground routes for Qwen3.8-27B."""
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ...core.app_factory import FeaturePlugin
from ...core.config import AppSettings
from ...core.models import TaskResponse
from ...core.storage import MediaStorage
from ...core.task_manager import TaskManager
from .runner import execute_qwen_task, stream_playground_sse
from .schemas import QwenChatRequest

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _validate_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    return QwenChatRequest.model_validate(raw).model_dump()


def _build_router(
    task_manager: TaskManager,
    storage: MediaStorage,
    cfg: AppSettings,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/v1/chat/stream",
        tags=["Qwen3.8-27B Studio"],
        summary="多模态深度思考 SSE 流式对话（Web 工作台主接口）",
    )
    async def chat_stream_endpoint(
        payload: QwenChatRequest,
    ) -> StreamingResponse:
        return StreamingResponse(
            stream_playground_sse(payload, storage, cfg),
            media_type="text/event-stream",
            headers=dict(SSE_HEADERS),
        )

    @router.post(
        "/api/v1/generate",
        response_model=TaskResponse,
        tags=["Qwen3.8-27B Studio"],
        summary="提交异步多模态推理任务（返回 task_id，可通过 WebSocket/轮询获取结果）",
    )
    async def submit_generate_task(
        payload: QwenChatRequest,
    ) -> TaskResponse:
        return task_manager.submit(payload.model_dump())

    return router


QWEN_3_8_27B_PLUGIN = FeaturePlugin(
    name="qwen3.8-27b",
    title="Qwen3.8-27B 多模态推理工作台",
    subtitle="256K 上下文 · 图像/视频理解 · 深度思考流",
    engine="Native vLLM (256K + MTP)",
    version="0.1.0",
    validate_params=_validate_params,
    execute=execute_qwen_task,
    register_presets=None,
    build_router=_build_router,
)
