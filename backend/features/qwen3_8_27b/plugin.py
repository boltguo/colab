"""FeaturePlugin definition and OpenAI/Anthropic/Playground routes for Qwen3.8-27B."""
import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from ...core.app_factory import FeaturePlugin
from ...core.config import AppSettings
from ...core.models import TaskResponse
from ...core.storage import MediaStorage
from ...core.task_manager import TaskManager
from .runner import (
    build_mock_anthropic_messages_response,
    build_mock_models_payload,
    build_mock_openai_chat_response,
    execute_qwen_task,
    forward_vllm_json_or_stream,
    rewrite_openai_payload_uploads,
    stream_playground_sse,
)
from .schemas import QwenChatRequest

SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _validate_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    return QwenChatRequest.model_validate(raw).model_dump()


def _extract_forward_headers(request: Request) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Content-Type": request.headers.get("content-type") or "application/json",
    }
    for key in ("accept", "anthropic-version", "anthropic-beta"):
        val = request.headers.get(key)
        if val:
            headers[key] = val
    return headers


def _build_router(
    task_manager: TaskManager,
    storage: MediaStorage,
    cfg: AppSettings,
    auth_dep: Any,
) -> APIRouter:
    router = APIRouter()

    # 1. Studio Playground Streaming Endpoint + Async Batch Endpoint
    @router.post(
        "/api/v1/chat/stream",
        tags=["Qwen3.8-27B Studio"],
        summary="多模态深度思考 SSE 流式对话（Web 工作台主接口）",
    )
    async def chat_stream_endpoint(
        payload: QwenChatRequest,
        _: None = Depends(auth_dep),
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
        _: None = Depends(auth_dep),
    ) -> TaskResponse:
        return task_manager.submit(payload.model_dump())

    # 2. Standard OpenAI & Anthropic Compatible Gateway (/v1/*)
    @router.get(
        "/v1/models",
        tags=["OpenAI & Anthropic Gateway"],
        summary="查询可用模型列表（OpenAI / Anthropic 兼容）",
    )
    async def list_v1_models(
        request: Request,
        _: None = Depends(auth_dep),
    ) -> Response:
        if cfg.mock_inference:
            return JSONResponse(content=build_mock_models_payload())
        status_code, ctype, body, _ = await forward_vllm_json_or_stream(
            "GET",
            "/v1/models",
            None,
            _extract_forward_headers(request),
        )
        return Response(content=body or b"{}", status_code=status_code, media_type=ctype)

    @router.post(
        "/v1/chat/completions",
        tags=["OpenAI & Anthropic Gateway"],
        summary="OpenAI 标准 Chat Completions 接口（支持流式、多模态与工具调用）",
    )
    async def openai_chat_completions(
        request: Request,
        _: None = Depends(auth_dep),
    ) -> Response:
        raw_bytes = await request.body()
        try:
            body_dict = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"无效的 JSON 请求体：{exc}") from exc

        try:
            sanitized = rewrite_openai_payload_uploads(body_dict, storage)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if cfg.mock_inference:
            is_stream, mock_res = await build_mock_openai_chat_response(sanitized)
            if is_stream:
                return StreamingResponse(mock_res, media_type="text/event-stream", headers=dict(SSE_HEADERS))
            return JSONResponse(content=mock_res)

        out_bytes = json.dumps(sanitized, ensure_ascii=False).encode("utf-8")
        status_code, ctype, imm_body, stream_iter = await forward_vllm_json_or_stream(
            "POST",
            "/v1/chat/completions",
            out_bytes,
            _extract_forward_headers(request),
        )
        if stream_iter is not None:
            return StreamingResponse(
                stream_iter,
                status_code=status_code,
                media_type="text/event-stream",
                headers=dict(SSE_HEADERS),
            )
        return Response(content=imm_body or b"{}", status_code=status_code, media_type=ctype)

    @router.post(
        "/v1/messages",
        tags=["OpenAI & Anthropic Gateway"],
        summary="Anthropic Messages 原生协议接口（支持 Claude Code 直连）",
    )
    async def anthropic_messages(
        request: Request,
        _: None = Depends(auth_dep),
    ) -> Response:
        raw_bytes = await request.body()
        if cfg.mock_inference:
            try:
                body_dict = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
            except Exception:
                body_dict = {}
            is_stream, mock_res = await build_mock_anthropic_messages_response(body_dict)
            if is_stream:
                return StreamingResponse(mock_res, media_type="text/event-stream", headers=dict(SSE_HEADERS))
            return JSONResponse(content=mock_res)

        query = f"?{request.url.query}" if request.url.query else ""
        status_code, ctype, imm_body, stream_iter = await forward_vllm_json_or_stream(
            "POST",
            f"/v1/messages{query}",
            raw_bytes,
            _extract_forward_headers(request),
        )
        if stream_iter is not None:
            return StreamingResponse(
                stream_iter,
                status_code=status_code,
                media_type="text/event-stream",
                headers=dict(SSE_HEADERS),
            )
        return Response(content=imm_body or b"{}", status_code=status_code, media_type=ctype)

    @router.post(
        "/v1/messages/count_tokens",
        tags=["OpenAI & Anthropic Gateway"],
        summary="Anthropic Messages Token 计数接口（Claude Code 兼容）",
    )
    async def anthropic_count_tokens(
        request: Request,
        _: None = Depends(auth_dep),
    ) -> Response:
        raw_bytes = await request.body()
        if cfg.mock_inference:
            return JSONResponse(content={"input_tokens": max(1, len(raw_bytes) // 4)})
        status_code, ctype, imm_body, _ = await forward_vllm_json_or_stream(
            "POST",
            "/v1/messages/count_tokens",
            raw_bytes,
            _extract_forward_headers(request),
        )
        return Response(content=imm_body or b"{}", status_code=status_code, media_type=ctype)

    for passthrough_path in ("/v1/completions", "/v1/responses", "/tokenize", "/detokenize"):
        def _make_passthrough(route_path: str):
            async def _handler(request: Request, _: None = Depends(auth_dep)) -> Response:
                raw_bytes = await request.body()
                if cfg.mock_inference:
                    return JSONResponse(content={"mock": True, "route": route_path})
                status_code, ctype, imm_body, stream_iter = await forward_vllm_json_or_stream(
                    "POST",
                    route_path,
                    raw_bytes,
                    _extract_forward_headers(request),
                )
                if stream_iter is not None:
                    return StreamingResponse(
                        stream_iter,
                        status_code=status_code,
                        media_type="text/event-stream",
                        headers=dict(SSE_HEADERS),
                    )
                return Response(content=imm_body or b"{}", status_code=status_code, media_type=ctype)

            return _handler

        router.add_api_route(
            passthrough_path,
            _make_passthrough(passthrough_path),
            methods=["POST"],
            tags=["OpenAI & Anthropic Gateway"],
        )

    return router


QWEN_3_8_27B_PLUGIN = FeaturePlugin(
    name="qwen3.8-27b",
    title="Qwen3.8-27B 多模态推理工作台",
    subtitle="256K 上下文 · 图像/视频理解 · 深度思考流 · OpenAI & Claude Code 原生协议",
    engine="Native vLLM (256K + MTP)",
    version="0.1.0",
    validate_params=_validate_params,
    execute=execute_qwen_task,
    register_presets=None,
    build_router=_build_router,
)
