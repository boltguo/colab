import assert from "node:assert/strict";
import test from "node:test";
import { buildChatMessages, buildOpenAiPayload, parseToolsJson, readChatEvents } from "../frontend/apps/qwen3.8-27b/src/chat.ts";
import { DEFAULT_QWEN_SAMPLING } from "../frontend/apps/qwen3.8-27b/src/types.ts";

const user = { id: "user", role: "user", content: "解释这张图片" };
const tool = { type: "function", function: { name: "weather", parameters: { type: "object" } } };

async function collect(stream) {
  const events = [];
  for await (const event of readChatEvents(stream)) events.push(event);
  return events;
}

test("SSE supports fragmented UTF-8, CRLF, heartbeats and a final event without a blank line", async () => {
  const source = ': heartbeat\r\n\r\ndata: {"type":"delta","content":"你好，世界"}\r\n\r\ndata: {"type":"done","finish_reason":"length"}';
  const bytes = new TextEncoder().encode(source);
  const stream = new ReadableStream({
    start(controller) {
      for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
      controller.close();
    },
  });
  assert.deepEqual(await collect(stream), [
    { type: "delta", content: "你好，世界" },
    { type: "done", finish_reason: "length" },
  ]);
  assert.equal(stream.locked, false);
});

test("SSE consumer exit cancels the underlying connection", async () => {
  let cancelled = false;
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode('data: {"type":"done"}\n\n')); },
    cancel() { cancelled = true; },
  });
  for await (const event of readChatEvents(stream)) {
    assert.equal(event.type, "done");
    break;
  }
  assert.equal(cancelled, true);
  assert.equal(stream.locked, false);
});

test("SSE malformed data is an error and releases the reader", async () => {
  const stream = new ReadableStream({
    start(controller) { controller.enqueue(new TextEncoder().encode("data: invalid\n\n")); },
  });
  await assert.rejects(() => collect(stream));
  assert.equal(stream.locked, false);
});

test("SSE disconnected stream never invents a completion event", async () => {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('data: {"type":"delta","content":"partial"}\n\n'));
      controller.close();
    },
  });
  const events = await collect(stream);
  assert.equal(events.some((event) => event.type === "done"), false);
});

test("Tools JSON rejects malformed or unsupported definitions without changing the input", () => {
  for (const raw of ["{", "{}", "[null]", '[{"type":"function","function":{}}]']) {
    assert.throws(() => parseToolsJson(raw));
  }
  assert.equal(parseToolsJson(""), undefined);
  assert.equal(parseToolsJson("[]"), undefined);
  assert.deepEqual(parseToolsJson(JSON.stringify([tool])), [tool]);
});

test("API payload includes every configured sampling control and current media references", () => {
  const sampling = {
    ...DEFAULT_QWEN_SAMPLING,
    system_prompt: "包含三引号 '''、换行\n与反斜杠 \\",
    max_tokens: 512,
    temperature: 0.4,
    top_p: 0.72,
    top_k: 0,
    min_p: 0.2,
    presence_penalty: 0.3,
    frequency_penalty: 0.4,
    repetition_penalty: 1.2,
    seed: 0,
    stop_text: "END, DONE\nSTOP",
    response_format: "json_object",
    tools_json: JSON.stringify([tool]),
    tool_choice: "required",
  };
  const payload = buildOpenAiPayload(sampling, [{ ...user, attachments: [
    { kind: "image", fileId: "photo.png", filename: "photo.png" },
    { kind: "video", fileId: "clip.mp4", filename: "clip.mp4" },
  ] }]);
  for (const key of ["max_tokens", "temperature", "top_p", "top_k", "min_p", "presence_penalty", "frequency_penalty", "repetition_penalty", "seed"]) {
    assert.equal(payload[key], sampling[key], key);
  }
  assert.equal(payload.messages[0].content, sampling.system_prompt);
  assert.deepEqual(payload.messages[1].content, [
    { type: "image_url", image_url: { url: "upload:photo.png" } },
    { type: "video_url", video_url: { url: "upload:clip.mp4" } },
    { type: "text", text: user.content },
  ]);
  assert.deepEqual(payload.response_format, { type: "json_object" });
  assert.deepEqual(payload.stop, ["END", "DONE", "STOP"]);
  assert.deepEqual(payload.tools, [tool]);
  assert.equal(payload.tool_choice, "required");
});

test("Non-thinking mode omits reasoning effort, random seed and unused tool controls", () => {
  const payload = buildOpenAiPayload({ ...DEFAULT_QWEN_SAMPLING, enable_thinking: false }, [user]);
  assert.deepEqual(payload.chat_template_kwargs, { enable_thinking: false });
  for (const key of ["reasoning_effort", "seed", "tools", "tool_choice", "response_format"]) {
    assert.equal(key in payload, false, key);
  }
});

test("More than eight stop words are rejected instead of silently truncated", () => {
  assert.throws(() => buildOpenAiPayload({ ...DEFAULT_QWEN_SAMPLING, stop_text: "a,b,c,d,e,f,g,h,i" }, [user]), /8/);
});

test("History preserves tool-call previews without inventing executed tool responses", () => {
  const messages = buildChatMessages([
    user,
    { id: "tool", role: "assistant", content: "", toolCalls: [{ id: "call", type: "function", function: { name: "weather", arguments: '{"city":"上海"}' } }] },
    { id: "error", role: "assistant", content: "bad", error: "failed" },
    { id: "stopped", role: "assistant", content: "", stopped: true },
    { id: "partial", role: "assistant", content: "保留已生成内容", stopped: true },
  ]);
  assert.equal(messages.length, 3);
  assert.match(messages[1].content, /未执行/);
  assert.match(messages[1].content, /weather\(/);
  assert.equal("tool_calls" in messages[1], false);
  assert.equal(messages[2].content, "保留已生成内容");
});
