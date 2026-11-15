"""Qwen gateway regressions using synthetic SSE and local sockets, without model weights."""
import asyncio
import http.client
import json
from pathlib import Path
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException, Request
from pydantic import ValidationError

from backend.core.storage import MediaStorage
from backend.features.qwen3_8_27b import runner
from backend.features.qwen3_8_27b.plugin import _build_router
from backend.features.qwen3_8_27b.schemas import QwenAttachment, QwenChatRequest


def sse_chunk(value):
    return f"data: {json.dumps(value)}\n\n".encode()


def event_value(raw):
    return json.loads(raw.decode().removeprefix("data: "))


class QwenChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.storage = MediaStorage(Path(self.tmp.name))
        self.cfg = SimpleNamespace(mock_inference=False)
        self.request = QwenChatRequest(prompt="你好")

    def test_sampling_tools_and_history_are_forwarded_without_changing_values(self):
        req = QwenChatRequest(
            messages=[
                {"role": "user", "content": "第一轮"},
                {"role": "assistant", "content": "回答", "reasoning_content": "旧思考"},
                {"role": "user", "content": "第二轮"},
            ],
            system_prompt="简洁回答", enable_thinking=True, reasoning_effort="medium",
            max_tokens=1234, temperature=0, top_p=0.81, top_k=0, min_p=0.1,
            presence_penalty=-0.2, frequency_penalty=0.3, repetition_penalty=1.1,
            seed=0, stop=[" END ", ""], response_format="json_object",
            tools=[{"type": "function", "function": {"name": "lookup"}}],
            tool_choice="required",
        )
        payload = runner.build_vllm_chat_payload(req, self.storage, stream=True)
        for key in ("max_tokens", "temperature", "top_p", "top_k", "min_p", "presence_penalty",
                    "frequency_penalty", "repetition_penalty", "seed", "tools", "tool_choice"):
            self.assertEqual(payload[key], getattr(req, key), key)
        self.assertEqual(payload["stop"], ["END"])
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["stream_options"], {"include_usage": True})
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": True, "preserve_thinking": True})
        self.assertEqual(payload["reasoning_effort"], "medium")
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "简洁回答"})
        self.assertEqual(payload["messages"][2]["reasoning_content"], "旧思考")

        req.enable_thinking = False
        payload = runner.build_vllm_chat_payload(req, self.storage, stream=False)
        self.assertNotIn("reasoning_effort", payload)
        self.assertNotIn("stream_options", payload)
        self.assertEqual(payload["top_k"], 0)

    def test_official_thinking_levels_defaults_and_preservation_option(self):
        req = QwenChatRequest(prompt="解释")
        self.assertEqual(req.reasoning_effort, "xhigh")
        self.assertEqual(req.temperature, 1.0)
        self.assertTrue(req.preserve_thinking)
        with self.assertRaises(ValidationError):
            QwenChatRequest(prompt="解释", reasoning_effort="high")
        for effort in ("low", "medium", "xhigh"):
            req = QwenChatRequest(prompt="解释", reasoning_effort=effort, preserve_thinking=False)
            payload = runner.build_vllm_chat_payload(req, self.storage, stream=False)
            self.assertEqual(payload["reasoning_effort"], effort)
            self.assertFalse(payload["chat_template_kwargs"]["preserve_thinking"])

    def test_local_and_inline_media_types_match_the_attachment_kind(self):
        for name in ("voice.wav", "photo.png", "clip.mp4"):
            (self.storage.uploads_dir / name).write_bytes(b"fixture")
        for allow_local in ("", "1"):
            with self.subTest(allow_local=allow_local), patch.dict("os.environ", {"VLLM_ALLOW_LOCAL_MEDIA": allow_local}):
                for kind, file_id in (("image", "voice.wav"), ("video", "photo.png"), ("image", "clip.mp4")):
                    with self.assertRaisesRegex(ValueError, "类型不匹配"):
                        runner.resolve_attachment_to_part(QwenAttachment(kind=kind, file_id=file_id), self.storage)
                result = runner.resolve_attachment_to_part(QwenAttachment(file_id="photo.png"), self.storage)
                prefix = "file:///" if allow_local else "data:image/png;base64,"
                self.assertTrue(result["image_url"]["url"].startswith(prefix))

        with self.assertRaisesRegex(ValueError, "类型不匹配"):
            runner.resolve_attachment_to_part(QwenAttachment(file_id="data:audio/wav;base64,AA=="), self.storage)
        remote = "https://example.com/media?id=123"
        self.assertEqual(
            runner.resolve_attachment_to_part(QwenAttachment(file_id=remote), self.storage)["image_url"]["url"],
            remote,
        )

    def test_external_file_urls_remain_blocked_in_all_supported_media_shapes(self):
        with patch.dict("os.environ", {"VLLM_ALLOW_LOCAL_MEDIA": "1"}):
            for url in ("file:///etc/passwd", "FILE:///etc/passwd", "file:/etc/passwd"):
                with self.subTest(url=url):
                    with self.assertRaisesRegex(ValueError, "file://"):
                        runner.resolve_attachment_to_part(QwenAttachment(file_id=url), self.storage)
                    for value in (url, {"url": url}):
                        raw = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": value}]}]}
                        with self.assertRaisesRegex(ValueError, "file://"):
                            runner.rewrite_openai_payload_uploads(raw, self.storage)

    async def test_non_object_openai_json_returns_400(self):
        router = _build_router(Mock(), self.storage, self.cfg, lambda: None)
        endpoint = next(route.endpoint for route in router.routes if route.path == "/v1/chat/completions")
        for value in ([], None, "text", 1):
            async def receive():
                return {"type": "http.request", "body": json.dumps(value).encode(), "more_body": False}

            req = Request({"type": "http", "method": "POST", "path": "/v1/chat/completions", "headers": []}, receive)
            with self.subTest(value=value), self.assertRaises(HTTPException) as caught:
                await endpoint(req)
            self.assertEqual(caught.exception.status_code, 400)

    async def collect_stream(self, raw_lines):
        closed = []

        async def source():
            try:
                for line in raw_lines:
                    yield line
            finally:
                closed.append(True)

        with patch.object(runner, "forward_vllm_json_or_stream", AsyncMock(return_value=(200, "text/event-stream", None, source()))):
            events = [event_value(line) async for line in runner.stream_playground_sse(self.request, self.storage, self.cfg)]
        self.assertTrue(closed, "The upstream iterator must be closed")
        return events

    async def test_completed_stream_preserves_tool_fragments_and_usage(self):
        events = await self.collect_stream([
            sse_chunk({"choices": [{"delta": {"reasoning_content": "分析"}}]}),
            sse_chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "lookup", "arguments": '{"q":'}}]}}]}),
            sse_chunk({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"test"}'}}]}, "finish_reason": "tool_calls"}]}),
            sse_chunk({"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 5}}),
            b"data: [DONE]\n\n",
        ])
        self.assertEqual(events[0]["reasoning"], "分析")
        call = next(e["tool_calls"][0] for e in events if e.get("tool_calls"))
        self.assertEqual(call, {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": '{"q":"test"}'}})
        usage = next(e for e in events if e["type"] == "usage")
        self.assertEqual(usage["total_tokens"], 25)
        self.assertEqual(events[-1], {"type": "done", "finish_reason": "tool_calls"})

    async def test_finish_reason_is_sufficient_when_done_marker_is_omitted(self):
        events = await self.collect_stream([sse_chunk({"choices": [{"delta": {"content": "完整回复"}, "finish_reason": "length"}]})])
        self.assertEqual(events[-1], {"type": "done", "finish_reason": "length"})

    async def test_unexpected_eof_reports_error_instead_of_success(self):
        for lines in ([], [sse_chunk({"choices": [{"delta": {"content": "未完"}}]})]):
            with self.subTest(lines=lines):
                events = await self.collect_stream(lines)
                self.assertEqual(events[-1]["type"], "error")
                self.assertIn("中断", events[-1]["error"])
                self.assertFalse(any(e["type"] == "done" for e in events))

    async def test_upstream_error_closes_stream_without_done(self):
        events = await self.collect_stream([sse_chunk({"error": {"message": "context too long"}})])
        self.assertEqual(events, [{"type": "error", "error": "context too long"}])

    async def test_missing_attachment_becomes_sse_error_before_engine_request(self):
        req = QwenChatRequest(prompt="识别图片", attachments=[{"file_id": "missing.png"}])
        with patch.object(runner, "forward_vllm_json_or_stream", AsyncMock()) as forward:
            events = [event_value(line) async for line in runner.stream_playground_sse(req, self.storage, self.cfg)]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("重新上传", events[0]["error"])
        forward.assert_not_called()

    async def test_stopping_or_cancelling_playground_closes_upstream(self):
        for cancel_while_waiting in (False, True):
            closed = asyncio.Event()
            waiting = asyncio.Event()

            async def source():
                try:
                    yield sse_chunk({"choices": [{"delta": {"content": "第一段"}}]})
                    waiting.set()
                    await asyncio.Event().wait()
                finally:
                    closed.set()

            with self.subTest(cancel=cancel_while_waiting), patch.object(runner, "forward_vllm_json_or_stream", AsyncMock(return_value=(200, "text/event-stream", None, source()))):
                stream = runner.stream_playground_sse(self.request, self.storage, self.cfg)
                self.assertEqual(event_value(await anext(stream))["content"], "第一段")
                if cancel_while_waiting:
                    pending = asyncio.create_task(anext(stream))
                    await asyncio.wait_for(waiting.wait(), 2)
                    pending.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await pending
                await stream.aclose()
                self.assertTrue(closed.is_set())

    async def test_proxy_closes_socket_when_cancelled_before_headers_or_during_stream(self):
        for cancel_before_headers in (True, False):
            client, peer = socket.socketpair()
            client.settimeout(2)
            peer.settimeout(2)
            self.addCleanup(client.close)
            self.addCleanup(peer.close)
            conn = http.client.HTTPConnection("vllm.invalid", timeout=2)
            conn.sock = client
            with self.subTest(before_headers=cancel_before_headers), patch.object(runner, "_open_vllm_connection", return_value=(conn, "")):
                request = asyncio.create_task(runner.forward_vllm_json_or_stream("GET", "/v1/models", None, {}))
                sent = await asyncio.to_thread(peer.recv, 4096)
                self.assertIn(b"GET /v1/models", sent)
                if cancel_before_headers:
                    request.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await request
                else:
                    peer.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n\r\ndata: partial\n\n")
                    _, _, body, raw_iter = await asyncio.wait_for(request, 2)
                    self.assertIsNone(body)
                    self.assertEqual(await anext(raw_iter), b"data: partial\n")
                    await raw_iter.aclose()
                self.assertEqual(await asyncio.to_thread(peer.recv, 1), b"", "Cancelling must close the actual upstream socket")


if __name__ == "__main__":
    unittest.main()
