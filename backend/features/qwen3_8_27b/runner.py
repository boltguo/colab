"""Native vLLM runner, multimodal attachment resolver, and OpenAI/Anthropic streaming gateway."""
import asyncio
import base64
import http.client
import json
import mimetypes
import os
from pathlib import Path
import socket
import threading
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid

from ...core.config import AppSettings
from ...core.storage import MediaStorage
from ...core.task_manager import ProgressCallback
from .schemas import QwenAttachment, QwenChatMessage, QwenChatRequest

DEFAULT_VLLM_BASE = "http://127.0.0.1:8189"
SERVED_MODEL_IDS = ["qwen3.8-27b", "Qwen/Qwen3.8-27B"]


def get_vllm_base_url() -> str:
    return (os.environ.get("VLLM_BASE_URL") or DEFAULT_VLLM_BASE).strip().rstrip("/")


def _allow_local_file_scheme() -> bool:
    return os.environ.get("VLLM_ALLOW_LOCAL_MEDIA", "").strip() in ("1", "true", "yes")


def _encode_file_for_vllm(path: Path, kind: str) -> str:
    """Encode a validated local upload path into file:// (when vLLM allows local media) or data: URI."""
    mime = mimetypes.guess_type(path.name)[0] or ""
    _validate_media_type(mime, kind)
    if _allow_local_file_scheme():
        return path.resolve().as_uri()
    raw = path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _validate_media_type(mime: str, kind: str) -> None:
    if not mime.lower().startswith(f"{kind}/"):
        label = "视频" if kind == "video" else "图片"
        raise ValueError(f"附件类型不匹配：请选择{label}文件，当前类型为 {mime or '未知格式'}。")


def _validate_external_media_url(url: str, kind: str) -> None:
    lowered = url.lower()
    if lowered.startswith("file:"):
        raise ValueError("外部请求不支持直接传入 file:// 路径，请先调用 POST /api/v1/files 上传。")
    if lowered.startswith("data:"):
        mime = url[5:].split(",", 1)[0].split(";", 1)[0]
        _validate_media_type(mime, kind)


def _rewrite_media_part(part: Dict[str, Any], storage: MediaStorage) -> Dict[str, Any]:
    part_copy = dict(part)
    for url_key, kind in (("image_url", "image"), ("video_url", "video")):
        sub = part_copy.get(url_key)
        url = sub.get("url") if isinstance(sub, dict) else sub
        if not isinstance(url, str):
            continue
        url = url.strip()
        _validate_external_media_url(url, kind)
        if url.startswith("upload:"):
            local_path = storage.resolve_input_ref(url[len("upload:") :])
            media_url = _encode_file_for_vllm(local_path, kind)
            part_copy[url_key] = {**sub, "url": media_url} if isinstance(sub, dict) else media_url
    return part_copy


def resolve_attachment_to_part(att: QwenAttachment, storage: MediaStorage) -> Dict[str, Any]:
    ref = (att.file_id or "").strip()
    if not ref:
        raise ValueError("多模态附件缺少 file_id。")

    _validate_external_media_url(ref, att.kind)
    if ref.lower().startswith(("https://", "http://", "data:")):
        media_url = ref
    else:
        clean_ref = ref[len("upload:") :] if ref.startswith("upload:") else ref
        local_path = storage.resolve_input_ref(clean_ref)
        media_url = _encode_file_for_vllm(local_path, att.kind)

    if att.kind == "video":
        return {"type": "video_url", "video_url": {"url": media_url}}
    return {"type": "image_url", "image_url": {"url": media_url}}


def _convert_message_to_openai(msg: QwenChatMessage, storage: MediaStorage) -> Dict[str, Any]:
    out: Dict[str, Any] = {"role": msg.role}
    if msg.role == "assistant" and msg.reasoning_content is not None:
        out["reasoning_content"] = msg.reasoning_content
    if msg.name:
        out["name"] = msg.name
    if msg.tool_call_id:
        out["tool_call_id"] = msg.tool_call_id
    if msg.tool_calls:
        out["tool_calls"] = msg.tool_calls

    if isinstance(msg.content, list):
        parts: List[Dict[str, Any]] = []
        for item in msg.content:
            if not isinstance(item, dict):
                continue
            parts.append(_rewrite_media_part(item, storage))
        for att in msg.attachments:
            parts.append(resolve_attachment_to_part(att, storage))
        out["content"] = parts
        return out

    text_val = msg.content or ""
    if msg.attachments and msg.role == "user":
        parts = [resolve_attachment_to_part(att, storage) for att in msg.attachments]
        if text_val:
            parts.append({"type": "text", "text": text_val})
        out["content"] = parts
    else:
        out["content"] = text_val
    return out


def rewrite_openai_payload_uploads(payload: Dict[str, Any], storage: MediaStorage) -> Dict[str, Any]:
    """Sanitize file:// URLs and resolve upload:<file_id> shortcuts in raw /v1/chat/completions calls."""
    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        return payload
    updated_msgs = []
    for m in msgs:
        if not isinstance(m, dict):
            updated_msgs.append(m)
            continue
        content = m.get("content")
        if not isinstance(content, list):
            updated_msgs.append(m)
            continue
        new_parts = []
        for part in content:
            if not isinstance(part, dict):
                new_parts.append(part)
                continue
            new_parts.append(_rewrite_media_part(part, storage))
        updated_msgs.append({**m, "content": new_parts})
    return {**payload, "messages": updated_msgs}


def build_vllm_chat_payload(
    req: QwenChatRequest,
    storage: MediaStorage,
    stream: bool,
) -> Dict[str, Any]:
    openai_messages = [_convert_message_to_openai(m, storage) for m in req.effective_messages()]
    model_name = req.model.strip() or "qwen3.8-27b"

    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": openai_messages,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "top_k": req.top_k,
        "min_p": req.min_p,
        "presence_penalty": req.presence_penalty,
        "frequency_penalty": req.frequency_penalty,
        "repetition_penalty": req.repetition_penalty,
        "stream": stream,
        "chat_template_kwargs": {
            "enable_thinking": bool(req.enable_thinking),
            "preserve_thinking": bool(req.preserve_thinking),
        },
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    if req.enable_thinking:
        payload["reasoning_effort"] = req.reasoning_effort
    if req.seed is not None:
        payload["seed"] = req.seed
    if req.stop:
        payload["stop"] = req.stop
    if req.response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}
    if req.tools:
        payload["tools"] = req.tools
        if req.tool_choice is not None:
            payload["tool_choice"] = req.tool_choice
    return payload


def _open_vllm_connection(timeout: float = 600.0) -> Tuple[http.client.HTTPConnection, str]:
    base = get_vllm_base_url()
    parsed = urlparse(base)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 8189)
    base_path = parsed.path.rstrip("/")
    if parsed.scheme == "https":
        return http.client.HTTPSConnection(host, port, timeout=timeout), base_path
    return http.client.HTTPConnection(host, port, timeout=timeout), base_path


async def forward_vllm_json_or_stream(
    method: str,
    path_and_query: str,
    body: Optional[bytes],
    headers: Dict[str, str],
) -> Tuple[int, str, Optional[bytes], Optional[AsyncIterator[bytes]]]:
    """Forward an HTTP request to internal vLLM, supporting both instant JSON and live SSE streaming."""
    loop = asyncio.get_running_loop()
    header_future: asyncio.Future[Tuple[int, str, Optional[bytes]]] = loop.create_future()
    chunk_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=64)
    abort_evt = threading.Event()
    conn_holder: List[http.client.HTTPConnection] = []
    socket_holder: List[socket.socket] = []
    pending_puts: List[Any] = []

    def _abort() -> None:
        abort_evt.set()
        for pending in list(pending_puts):
            pending.cancel()
        # shutdown wakes a worker blocked in getresponse/readline before close
        # touches the response's buffered reader. Keep the socket even when an
        # HTTP/1.0 response has detached it from HTTPConnection.
        sockets = list(socket_holder)
        for conn in conn_holder:
            active_socket = conn.sock
            if active_socket is not None:
                sockets.append(active_socket)
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for conn in conn_holder:
            try:
                conn.close()
            except Exception:
                pass

    def _publish_headers(status: int, ctype: str, data: Optional[bytes]) -> None:
        def _set_result() -> None:
            if not header_future.done():
                header_future.set_result((status, ctype, data))

        if not abort_evt.is_set():
            loop.call_soon_threadsafe(_set_result)

    def _put_chunk(chunk: Optional[bytes]) -> bool:
        if abort_evt.is_set():
            return False
        pending = asyncio.run_coroutine_threadsafe(chunk_queue.put(chunk), loop)
        pending_puts.append(pending)
        try:
            if abort_evt.is_set():
                return False
            # Backpressure must not discard the terminal sentinel. Cancellation
            # explicitly cancels this future if the downstream stops reading.
            pending.result()
            return True
        finally:
            pending.cancel()
            pending_puts.remove(pending)

    def _worker() -> None:
        conn: Optional[http.client.HTTPConnection] = None
        resp: Optional[http.client.HTTPResponse] = None
        try:
            conn, base_path = _open_vllm_connection(timeout=600.0)
            conn_holder.append(conn)
            if abort_evt.is_set():
                return
            target_path = f"{base_path}{path_and_query}"
            conn.request(method, target_path, body=body, headers=headers)
            active_socket = conn.sock
            if active_socket is not None:
                socket_holder.append(active_socket)
            if abort_evt.is_set():
                return
            resp = conn.getresponse()
            status = resp.status
            ctype = resp.getheader("Content-Type") or "application/json"
            is_sse = "text/event-stream" in ctype.lower()

            if not is_sse or status >= 400:
                data = resp.read()
                _publish_headers(status, ctype, data)
                return

            _publish_headers(status, ctype, None)
            while not abort_evt.is_set():
                line = resp.readline()
                if not line:
                    break
                if not _put_chunk(line):
                    break
        except Exception as exc:
            err_payload = json.dumps(
                {"error": {"message": f"连接内部 vLLM 引擎失败：{exc}", "type": "engine_unavailable"}},
                ensure_ascii=False,
            ).encode("utf-8")
            if not header_future.done():
                _publish_headers(502, "application/json", err_payload)
        finally:
            if not header_future.done():
                _publish_headers(502, "application/json", b'{"error":"vLLM closed"}')
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            try:
                _put_chunk(None)
            except Exception:
                pass

    threading.Thread(target=_worker, name="vllm-proxy-stream", daemon=True).start()
    try:
        status_code, content_type, immediate_body = await header_future
    except asyncio.CancelledError:
        _abort()
        raise

    if immediate_body is not None:
        return status_code, content_type, immediate_body, None

    async def _iter_sse() -> AsyncIterator[bytes]:
        try:
            while True:
                chunk = await chunk_queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            _abort()

    return status_code, content_type, None, _iter_sse()


# ---------------------------------------------------------------------------
# Normalized Studio Playground SSE Stream (Real vLLM + Rich Mock Mode)
# ---------------------------------------------------------------------------


def _summarize_mock_attachments(req: QwenChatRequest, storage: MediaStorage) -> List[str]:
    notes: List[str] = []
    for m in req.effective_messages():
        for att in m.attachments:
            label = att.filename or att.file_id
            size_kb = ""
            if att.file_id and not att.file_id.startswith(("http://", "https://", "data:")):
                try:
                    clean_ref = att.file_id[len("upload:") :] if att.file_id.startswith("upload:") else att.file_id
                    p = storage.resolve_input_ref(clean_ref)
                    size_kb = f" ({p.stat().st_size / 1024:.1f} KB)"
                except Exception:
                    size_kb = ""
            notes.append(f"{'视频' if att.kind == 'video' else '图像'} `{label}`{size_kb}")
    return notes


def _build_mock_text_and_thinking(
    req: QwenChatRequest,
    storage: MediaStorage,
) -> Tuple[str, str, Optional[List[Dict[str, Any]]]]:
    msgs = req.effective_messages()
    last_user_text = ""
    for m in reversed(msgs):
        if m.role == "user":
            last_user_text = m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)
            break

    att_notes = _summarize_mock_attachments(req, storage)
    thinking = ""
    if req.enable_thinking:
        att_clause = f"同时检测到多模态输入：{', '.join(att_notes)}。" if att_notes else "当前为纯文本多轮上下文。"
        thinking = (
            f"正在分析用户请求：「{last_user_text[:90]}」\n"
            f"1. 推理档位：`reasoning_effort={req.reasoning_effort}`，温度 `T={req.temperature}`，`Top-P={req.top_p}`，`Top-K={req.top_k}`。\n"
            f"2. {att_clause}\n"
            f"3. 组织结构化、清晰简洁的中文回答。"
        )

    if req.tools and req.tool_choice != "none":
        first_tool = req.tools[0]
        fn_spec = first_tool.get("function", first_tool) if isinstance(first_tool, dict) else {}
        fn_name = fn_spec.get("name", "sample_tool")
        tool_calls = [
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": fn_name,
                    "arguments": json.dumps({"query": last_user_text[:60] or "test"}, ensure_ascii=False),
                },
            }
        ]
        return thinking, "", tool_calls

    if req.response_format == "json_object":
        json_ans = json.dumps(
            {
                "model": "Qwen/Qwen3.8-27B",
                "mock": True,
                "summary": f"已按 JSON 模式响应：{last_user_text[:80]}",
                "attachments": att_notes,
                "sampling": {
                    "enable_thinking": req.enable_thinking,
                    "reasoning_effort": req.reasoning_effort,
                    "temperature": req.temperature,
                    "top_p": req.top_p,
                    "top_k": req.top_k,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        return thinking, json_ans, None

    att_section = (
        f"\n\n**已解析多模态附件**：{'、'.join(att_notes)}（在 Colab GPU 环境下将由 Qwen3.8-27B 原生视觉编码器直接理解画面细节与时序动作）。"
        if att_notes
        else ""
    )
    answer = (
        f"你好！这是 **Qwen3.8-27B** 本地 Mock 预览模式的流式响应。\n\n"
        f"你刚才发送的内容是：\n> {last_user_text or '（多模态输入）'}{att_section}\n\n"
        f"```python\n"
        f"# 当前生效采样参数\n"
        f"config = {{\n"
        f'    "enable_thinking": {req.enable_thinking},\n'
        f'    "temperature": {req.temperature},\n'
        f'    "top_p": {req.top_p},\n'
        f'    "top_k": {req.top_k},\n'
        f'    "max_tokens": {req.max_tokens},\n'
        f"}}\n"
        f"```\n\n"
        f"部署到 Colab A100 / H100 后，底层 `vLLM`（`262144` 上下文 + MTP 投机解码）将同时承载此对话工作台、OpenAI `/v1/chat/completions` 与 Claude Code `/v1/messages`。"
    )
    return thinking, answer, None


def _chunk_string(text: str, step: int = 8) -> List[str]:
    return [text[i : i + step] for i in range(0, len(text), step)]


async def stream_playground_sse(
    req: QwenChatRequest,
    storage: MediaStorage,
    cfg: AppSettings,
) -> AsyncIterator[bytes]:
    """Yield normalized SSE JSON frames for the Studio Playground."""
    started = time.perf_counter()

    def _sse(obj: Dict[str, Any]) -> bytes:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8")

    if cfg.mock_inference:
        thinking, answer, tool_calls = _build_mock_text_and_thinking(req, storage)
        think_started = time.perf_counter()
        if thinking:
            for piece in _chunk_string(thinking, 10):
                await asyncio.sleep(0.025)
                yield _sse({"type": "delta", "reasoning": piece, "content": ""})
        thinking_sec = round(time.perf_counter() - think_started, 2) if thinking else 0.0

        if tool_calls:
            yield _sse({"type": "delta", "reasoning": "", "content": "", "tool_calls": tool_calls})
            finish_reason = "tool_calls"
        else:
            for piece in _chunk_string(answer, 12):
                await asyncio.sleep(0.02)
                yield _sse({"type": "delta", "reasoning": "", "content": piece})
            finish_reason = "stop"

        elapsed = max(0.05, time.perf_counter() - started)
        comp_tokens = max(8, (len(thinking) + len(answer)) // 2)
        prompt_tokens = max(16, sum(len(str(m.content)) for m in req.effective_messages()) // 2)
        yield _sse(
            {
                "type": "usage",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": comp_tokens,
                "total_tokens": prompt_tokens + comp_tokens,
                "thinking_sec": thinking_sec,
                "elapsed_sec": round(elapsed, 2),
                "tokens_per_sec": round(comp_tokens / elapsed, 1),
                "mock": True,
            }
        )
        yield _sse({"type": "done", "finish_reason": finish_reason})
        return

    raw_iter: Optional[AsyncIterator[bytes]] = None
    try:
        payload = build_vllm_chat_payload(req, storage, stream=True)
        body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status_code, _ctype, err_body, raw_iter = await forward_vllm_json_or_stream(
            "POST",
            "/v1/chat/completions",
            body_bytes,
            {"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        if err_body is not None or raw_iter is None:
            detail = err_body.decode("utf-8", errors="replace") if err_body else f"HTTP {status_code}"
            yield _sse({"type": "error", "error": f"vLLM 请求失败 ({status_code})：{detail}"})
            return

        tool_calls_map: Dict[int, Dict[str, Any]] = {}
        prompt_tokens = 0
        completion_tokens = 0
        finish_reason: Optional[str] = None
        saw_done = False
        think_start_ts: Optional[float] = None
        think_end_ts: Optional[float] = None

        async for raw_line in raw_iter:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                saw_done = True
                break
            try:
                chunk = json.loads(data_str)
            except Exception:
                continue

            if not isinstance(chunk, dict):
                continue
            if chunk.get("error"):
                error = chunk["error"]
                detail = error.get("message") if isinstance(error, dict) else str(error)
                yield _sse({"type": "error", "error": detail or str(error)})
                return

            usage = chunk.get("usage")
            if isinstance(usage, dict):
                prompt_tokens = int(usage.get("prompt_tokens") or prompt_tokens)
                completion_tokens = int(usage.get("completion_tokens") or completion_tokens)

            choices = chunk.get("choices")
            if not isinstance(choices, list) or not choices:
                continue
            choice0 = choices[0]
            if not isinstance(choice0, dict):
                continue
            if choice0.get("finish_reason"):
                finish_reason = str(choice0["finish_reason"])
            delta = choice0.get("delta") or {}
            if not isinstance(delta, dict):
                continue

            r_piece = delta.get("reasoning_content") or delta.get("reasoning") or ""
            c_piece = delta.get("content") or ""

            if r_piece and think_start_ts is None:
                think_start_ts = time.perf_counter()
            if c_piece and think_start_ts is not None and think_end_ts is None:
                think_end_ts = time.perf_counter()

            tc_deltas = delta.get("tool_calls")
            if isinstance(tc_deltas, list):
                for tc in tc_deltas:
                    idx = int(tc.get("index", 0))
                    cur = tool_calls_map.setdefault(
                        idx,
                        {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                    )
                    if tc.get("id"):
                        cur["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        cur["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        cur["function"]["arguments"] += fn["arguments"]

            if r_piece or c_piece:
                yield _sse({"type": "delta", "reasoning": r_piece, "content": c_piece})

        if finish_reason is None and not saw_done:
            yield _sse({"type": "error", "error": "vLLM 响应流意外中断，回复尚未完成，请重试。"})
            return

        if tool_calls_map:
            ordered_calls = [tool_calls_map[k] for k in sorted(tool_calls_map)]
            yield _sse({"type": "delta", "reasoning": "", "content": "", "tool_calls": ordered_calls})

        now_ts = time.perf_counter()
        elapsed = max(0.05, now_ts - started)
        thinking_sec = (
            round((think_end_ts or now_ts) - think_start_ts, 2)
            if think_start_ts is not None
            else 0.0
        )
        yield _sse(
            {
                "type": "usage",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "thinking_sec": thinking_sec,
                "elapsed_sec": round(elapsed, 2),
                "tokens_per_sec": round(completion_tokens / elapsed, 1) if completion_tokens else 0.0,
                "mock": False,
            }
        )
        yield _sse({"type": "done", "finish_reason": finish_reason or "stop"})
    except Exception as exc:
        yield _sse({"type": "error", "error": f"生成失败：{exc}"})
    finally:
        if raw_iter is not None:
            close = getattr(raw_iter, "aclose", None)
            if close is not None:
                await close()


def execute_qwen_task(
    params: Dict[str, Any],
    storage: MediaStorage,
    cfg: AppSettings,
    progress_cb: ProgressCallback,
) -> Dict[str, Any]:
    """Async TaskManager execution entrypoint for POST /api/v1/generate."""
    req = QwenChatRequest.model_validate(params)
    started = time.perf_counter()
    progress_cb(0.15, "正在准备多模态上下文与采样参数...")

    if cfg.mock_inference:
        time.sleep(0.25)
        thinking, answer, tool_calls = _build_mock_text_and_thinking(req, storage)
        progress_cb(0.95, "推理完成")
        elapsed = round(max(0.05, time.perf_counter() - started), 2)
        comp_tokens = max(8, (len(thinking) + len(answer)) // 2)
        return {
            "model": req.model,
            "reasoning_content": thinking,
            "content": answer,
            "tool_calls": tool_calls,
            "usage": {
                "prompt_tokens": 32,
                "completion_tokens": comp_tokens,
                "total_tokens": 32 + comp_tokens,
                "tokens_per_sec": round(comp_tokens / elapsed, 1),
            },
            "elapsed_sec": elapsed,
            "mock": True,
        }

    payload = build_vllm_chat_payload(req, storage, stream=False)
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    progress_cb(0.35, "正在调用 vLLM 执行 Qwen3.8-27B 推理...")

    conn, base_path = _open_vllm_connection(timeout=600.0)
    try:
        conn.request(
            "POST",
            f"{base_path}/v1/chat/completions",
            body=body_bytes,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        raw = resp.read()
    finally:
        conn.close()

    if resp.status >= 400:
        raise RuntimeError(f"vLLM 返回错误 ({resp.status})：{raw.decode('utf-8', errors='replace')}")

    data = json.loads(raw.decode("utf-8", errors="replace"))
    choice0 = (data.get("choices") or [{}])[0]
    message = choice0.get("message") or {}
    usage = data.get("usage") or {}
    elapsed = round(max(0.05, time.perf_counter() - started), 2)
    comp_tokens = int(usage.get("completion_tokens") or 0)
    progress_cb(1.0, "生成完成")
    return {
        "model": data.get("model") or req.model,
        "reasoning_content": message.get("reasoning_content") or message.get("reasoning") or "",
        "content": message.get("content") or "",
        "tool_calls": message.get("tool_calls"),
        "finish_reason": choice0.get("finish_reason") or "stop",
        "usage": {
            **usage,
            "tokens_per_sec": round(comp_tokens / elapsed, 1) if comp_tokens else 0.0,
        },
        "elapsed_sec": elapsed,
        "mock": False,
    }


# ---------------------------------------------------------------------------
# Mock OpenAI /v1/chat/completions & Anthropic /v1/messages Helpers
# ---------------------------------------------------------------------------


def build_mock_models_payload() -> Dict[str, Any]:
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": mid,
                "object": "model",
                "created": created,
                "owned_by": "Qwen",
                "max_model_len": 262144,
            }
            for mid in SERVED_MODEL_IDS
        ],
    }


async def build_mock_openai_chat_response(
    raw_body: Dict[str, Any],
) -> Tuple[bool, Any]:
    stream = bool(raw_body.get("stream"))
    model = str(raw_body.get("model") or "qwen3.8-27b")
    msgs = raw_body.get("messages") or []
    last_text = ""
    if isinstance(msgs, list):
        for m in reversed(msgs):
            if isinstance(m, dict) and m.get("role") == "user":
                last_text = str(m.get("content") or "")
                break
    enable_thinking = True
    ctk = raw_body.get("chat_template_kwargs")
    if isinstance(ctk, dict) and "enable_thinking" in ctk:
        enable_thinking = bool(ctk["enable_thinking"])

    reasoning_text = f"Mock 思考过程：分析请求「{last_text[:60]}」。" if enable_thinking else ""
    reply_text = f"[Qwen3.8-27B Mock] 已收到 OpenAI 协议请求：{last_text[:120]}"
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:16]}"
    created = int(time.time())

    if not stream:
        return False, {
            "id": chat_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "reasoning_content": reasoning_text or None,
                        "content": reply_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 28, "total_tokens": 48},
        }

    async def _gen() -> AsyncIterator[bytes]:
        if reasoning_text:
            chunk = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "reasoning_content": reasoning_text}, "finish_reason": None}],
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
            await asyncio.sleep(0.02)
        chunk2 = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": reply_text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 28, "total_tokens": 48},
        }
        yield f"data: {json.dumps(chunk2, ensure_ascii=False)}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"

    return True, _gen()


async def build_mock_anthropic_messages_response(
    raw_body: Dict[str, Any],
) -> Tuple[bool, Any]:
    stream = bool(raw_body.get("stream"))
    model = str(raw_body.get("model") or "qwen3.8-27b")
    msgs = raw_body.get("messages") or []
    last_text = ""
    if isinstance(msgs, list) and msgs:
        last_m = msgs[-1]
        if isinstance(last_m, dict):
            last_text = str(last_m.get("content") or "")
    reply_text = f"[Qwen3.8-27B Mock / Anthropic Messages] 已收到请求：{last_text[:120]}"
    msg_id = f"msg_{uuid.uuid4().hex[:16]}"

    if not stream:
        return False, {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": reply_text}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {"input_tokens": 24, "output_tokens": 26},
        }

    async def _gen() -> AsyncIterator[bytes]:
        events = [
            ("message_start", {"type": "message_start", "message": {"id": msg_id, "type": "message", "role": "assistant", "model": model, "content": [], "stop_reason": None, "usage": {"input_tokens": 24, "output_tokens": 1}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": reply_text}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 26}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        for evt_name, data in events:
            yield f"event: {evt_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
            await asyncio.sleep(0.01)

    return True, _gen()
