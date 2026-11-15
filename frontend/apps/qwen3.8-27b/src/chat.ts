import type { ChatTurn, QwenSamplingConfig } from "./types";

export function parseToolsJson(raw: string): Record<string, unknown>[] | undefined {
  if (!raw.trim()) return undefined;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("工具定义不是有效的 JSON，请检查引号和逗号；输入内容已保留。");
  }
  if (!Array.isArray(parsed)) throw new Error("工具定义必须是 JSON 数组 [...]。");
  if (parsed.some((tool) => !tool || tool.type !== "function" || !tool.function ||
    typeof tool.function.name !== "string" || !tool.function.name.trim())) {
    throw new Error("每个工具需包含 type: function 和非空的 function.name。");
  }
  return parsed.length ? parsed : undefined;
}

export function parseStopWords(raw: string): string[] {
  return raw.split(/[,\n]/).map((word) => word.trim()).filter(Boolean);
}

export function buildChatMessages(turns: ChatTurn[]) {
  return turns.filter((turn) => !turn.error && (
    turn.role === "user" || turn.content || turn.toolCalls?.length
  )).map((turn) => ({
    role: turn.role,
    ...(turn.role === "assistant" && turn.reasoningContent
      ? { reasoning_content: turn.reasoningContent } : {}),
    // The workbench previews tool calls; it does not execute functions or
    // fabricate tool results. Preserve this information as ordinary context.
    content: turn.content + (turn.toolCalls?.length
      ? `\n\n工具调用预览（未执行）：\n${turn.toolCalls.map((call) =>
        `${call.function.name}(${call.function.arguments})`).join("\n")}`
      : ""),
    attachments: (turn.attachments || []).map((attachment) => ({
      kind: attachment.kind,
      file_id: attachment.fileId,
      filename: attachment.filename,
    })),
  }));
}

export function buildOpenAiPayload(sampling: QwenSamplingConfig, turns: ChatTurn[]) {
  const tools = parseToolsJson(sampling.tools_json);
  const stops = parseStopWords(sampling.stop_text);
  if (stops.length > 8) throw new Error("最多支持 8 个停止词，请删减后再发送。");
  const messages: Record<string, unknown>[] = buildChatMessages(turns).map((turn) => ({
    role: turn.role,
    ...(turn.reasoning_content ? { reasoning_content: turn.reasoning_content } : {}),
    content: turn.attachments.length ? [
      ...turn.attachments.map((attachment) => attachment.kind === "video"
        ? { type: "video_url", video_url: { url: `upload:${attachment.file_id}` } }
        : { type: "image_url", image_url: { url: `upload:${attachment.file_id}` } }),
      ...(turn.content ? [{ type: "text", text: turn.content }] : []),
    ] : turn.content,
  }));
  if (sampling.system_prompt.trim()) messages.unshift({ role: "system", content: sampling.system_prompt.trim() });
  return {
    model: "qwen3.8-27b",
    messages,
    max_tokens: sampling.max_tokens,
    temperature: sampling.temperature,
    top_p: sampling.top_p,
    top_k: sampling.top_k,
    min_p: sampling.min_p,
    presence_penalty: sampling.presence_penalty,
    frequency_penalty: sampling.frequency_penalty,
    repetition_penalty: sampling.repetition_penalty,
    chat_template_kwargs: {
      enable_thinking: sampling.enable_thinking,
      preserve_thinking: sampling.preserve_thinking,
    },
    ...(sampling.enable_thinking ? { reasoning_effort: sampling.reasoning_effort } : {}),
    ...(sampling.seed !== null ? { seed: sampling.seed } : {}),
    ...(stops.length ? { stop: stops } : {}),
    ...(sampling.response_format === "json_object" ? { response_format: { type: "json_object" } } : {}),
    ...(tools ? { tools, tool_choice: sampling.tool_choice } : {}),
  };
}

/** Decode SSE across arbitrary network chunks, including CRLF and UTF-8 splits. */
export async function* readChatEvents(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const parseEvent = (raw: string): Record<string, unknown> | null => {
    const data = raw.split(/\r?\n/).filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart()).join("\n");
    if (!data) return null;
    if (data.trim() === "[DONE]") return { type: "done" };
    const value: unknown = JSON.parse(data);
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("服务返回了无效的流式数据，请重试。");
    }
    return value as Record<string, unknown>;
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let boundary = /\r?\n\r?\n/.exec(buffer);
      while (boundary) {
        const event = parseEvent(buffer.slice(0, boundary.index));
        buffer = buffer.slice(boundary.index + boundary[0].length);
        if (event) yield event;
        boundary = /\r?\n\r?\n/.exec(buffer);
      }
      if (done) {
        const event = parseEvent(buffer);
        if (event) yield event;
        return;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
