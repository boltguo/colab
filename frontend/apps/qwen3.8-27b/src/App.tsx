import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  Alert,
  BulbOutlined,
  Button,
  Card,
  ClearOutlined,
  CloseOutlined,
  CodeOutlined,
  CopyOutlined,
  DeleteOutlined,
  Input,
  InputNumber,
  LoadingOutlined,
  MessageOutlined,
  PaperClipOutlined,
  PictureOutlined,
  Popconfirm,
  ReloadOutlined,
  Segmented,
  Select,
  SendOutlined,
  Slider,
  Space,
  StopOutlined,
  StudioCustomApiTabContext,
  StudioShell,
  Switch,
  Tag,
  Text,
  TextArea,
  Tooltip,
  VideoCameraOutlined,
  loadApiKey,
  resolveApiUrl,
  uploadMediaFile,
  useStudioFeedback,
} from "@colab/shared";
import { MarkdownBody } from "./MarkdownBody";
import {
  ChatAttachmentItem,
  ChatTurn,
  DEFAULT_QWEN_SAMPLING,
  QwenSamplingConfig,
  ReasoningEffort,
  ResponseFormatMode,
  ToolCallItem,
} from "./types";

function splitFilename(name: string): { stem: string; ext: string } {
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return { stem: name, ext: "" };
  return { stem: name.slice(0, dot), ext: name.slice(dot) };
}

function isVideoFilenameOrMime(name: string, mime?: string): boolean {
  if (mime && mime.toLowerCase().startsWith("video/")) return true;
  return /\.(mp4|webm|mov|mkv)$/i.test(name);
}

function ThinkingDisclosure({
  reasoning,
  thinkingActive,
  thinkingSec,
}: {
  reasoning?: string;
  thinkingActive?: boolean;
  thinkingSec?: number;
}) {
  const detailsRef = useRef<HTMLDetailsElement | null>(null);
  const prevActiveRef = useRef<boolean>(Boolean(thinkingActive));

  useEffect(() => {
    const el = detailsRef.current;
    if (!el) return;
    if (thinkingActive) {
      el.open = true;
    } else if (prevActiveRef.current && !thinkingActive) {
      el.open = false;
    }
    prevActiveRef.current = Boolean(thinkingActive);
  }, [thinkingActive]);

  return (
    <details ref={detailsRef} className="studio-think-block">
      <summary>
        {thinkingActive ? (
          <Space size={6}>
            <LoadingOutlined style={{ color: "var(--studio-accent)" }} />
            <span>深度思考中…</span>
          </Space>
        ) : (
          <span className="studio-tabular">
            思考过程
            {thinkingSec ? ` · ${thinkingSec}s` : ""}
            {reasoning ? `（${reasoning.length} 字）` : ""}
          </span>
        )}
      </summary>
      <div className="studio-think-body">{reasoning || "正在构建推理链..."}</div>
    </details>
  );
}

export function QwenChatStudioApp() {
  const composerInputId = useId();
  const sysPromptId = useId();
  const fileInputId = useId();
  const lightboxTitleId = useId();

  const formRef = useRef<HTMLFormElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const lightboxRef = useRef<HTMLDialogElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastCompositionEndRef = useRef<number | null>(null);
  const shouldStickBottomRef = useRef(true);
  const turnSeqRef = useRef(1);

  const { message } = useStudioFeedback();

  const [sampling, setSampling] = useState<QwenSamplingConfig>(DEFAULT_QWEN_SAMPLING);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [inputText, setInputText] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<ChatAttachmentItem[]>([]);
  const [uploadingCount, setUploadingCount] = useState(0);
  const [draggingMedia, setDraggingMedia] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lightboxImage, setLightboxImage] = useState<{ url: string; name: string } | null>(null);

  const nextId = (prefix: string) => {
    const id = `${prefix}-${turnSeqRef.current}`;
    turnSeqRef.current += 1;
    return id;
  };

  const updateSampling = <K extends keyof QwenSamplingConfig>(
    key: K,
    val: QwenSamplingConfig[K]
  ) => {
    setSampling((prev) => ({ ...prev, [key]: val }));
  };

  // Toggle Thinking mode with smart Qwen official temperature/top_p recommendation
  const handleToggleThinking = (enabled: boolean) => {
    setSampling((prev) => {
      const next = { ...prev, enable_thinking: enabled };
      if (enabled && prev.temperature === 0.7 && prev.top_p === 0.8) {
        next.temperature = 0.6;
        next.top_p = 0.95;
      } else if (!enabled && prev.temperature === 0.6 && prev.top_p === 0.95) {
        next.temperature = 0.7;
        next.top_p = 0.8;
      }
      return next;
    });
  };

  // Light-dismiss backdrop click fallback for Safari <dialog>
  useEffect(() => {
    const dialog = lightboxRef.current;
    if (!dialog) return;
    if ("closedBy" in HTMLDialogElement.prototype) return;

    const onBackdropClick = (ev: MouseEvent) => {
      if (ev.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      const inside =
        rect.top <= ev.clientY &&
        ev.clientY <= rect.top + rect.height &&
        rect.left <= ev.clientX &&
        ev.clientX <= rect.left + rect.width;
      if (!inside) dialog.close();
    };
    dialog.addEventListener("click", onBackdropClick);
    return () => dialog.removeEventListener("click", onBackdropClick);
  }, [lightboxImage]);

  // Auto-scroll transcript only when user hasn't scrolled up to read earlier history
  useEffect(() => {
    const el = transcriptRef.current;
    if (!el || !shouldStickBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [turns]);

  const handleTranscriptScroll = () => {
    const el = transcriptRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    shouldStickBottomRef.current = distFromBottom < 110;
  };

  const handleUploadFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    if (pendingAttachments.length + list.length > 12) {
      message.warning("单轮最多附加 12 个图片或视频文件。");
      return;
    }

    setUploadingCount((c) => c + list.length);
    try {
      for (const file of list) {
        try {
          const uploaded = await uploadMediaFile(file);
          const kind: "image" | "video" = isVideoFilenameOrMime(uploaded.filename, uploaded.content_type)
            ? "video"
            : "image";
          setPendingAttachments((prev) => [
            ...prev,
            {
              id: nextId("att"),
              kind,
              fileId: uploaded.file_id,
              filename: uploaded.filename,
              previewUrl: resolveApiUrl(uploaded.url, true),
              sizeBytes: uploaded.size_bytes,
            },
          ]);
        } catch (err) {
          message.error(err instanceof Error ? err.message : `上传失败：${file.name}`);
        }
      }
    } finally {
      setUploadingCount((c) => Math.max(0, c - list.length));
    }
  };

  const parseToolsSafe = useCallback((): { ok: true; tools?: unknown[] } | { ok: false; error: string } => {
    const raw = sampling.tools_json.trim();
    if (!raw) return { ok: true, tools: undefined };
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return { ok: false, error: "工具定义 (Tools JSON) 必须是 JSON 数组格式 `[...]`。" };
      }
      return { ok: true, tools: parsed };
    } catch (err) {
      return {
        ok: false,
        error: `Tools JSON 解析失败：${err instanceof Error ? err.message : String(err)}`,
      };
    }
  }, [sampling.tools_json]);

  const parsedStops = useMemo(
    () =>
      sampling.stop_text
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 8),
    [sampling.stop_text]
  );

  const buildApiPayloadFromHistory = useCallback(
    (historyTurns: ChatTurn[], toolsOverride?: unknown[]) => {
      const messages = historyTurns.map((t) => ({
        role: t.role,
        content: t.content,
        attachments: (t.attachments || []).map((a) => ({
          kind: a.kind,
          file_id: a.fileId,
          filename: a.filename,
        })),
      }));
      return {
        model: "qwen3.8-27b",
        system_prompt: sampling.system_prompt,
        messages,
        enable_thinking: sampling.enable_thinking,
        reasoning_effort: sampling.reasoning_effort,
        max_tokens: sampling.max_tokens,
        temperature: sampling.temperature,
        top_p: sampling.top_p,
        top_k: sampling.top_k,
        min_p: sampling.min_p,
        presence_penalty: sampling.presence_penalty,
        frequency_penalty: sampling.frequency_penalty,
        repetition_penalty: sampling.repetition_penalty,
        seed: sampling.seed,
        stop: parsedStops,
        response_format: sampling.response_format,
        ...(toolsOverride && toolsOverride.length > 0
          ? { tools: toolsOverride, tool_choice: sampling.tool_choice }
          : {}),
      };
    },
    [parsedStops, sampling]
  );

  const streamConversation = useCallback(
    async (historyWithUser: ChatTurn[]) => {
      const toolsCheck = parseToolsSafe();
      if (!toolsCheck.ok) {
        message.error(toolsCheck.error);
        return;
      }

      const assistantId = nextId("asst");
      const assistantPlaceholder: ChatTurn = {
        id: assistantId,
        role: "assistant",
        content: "",
        reasoningContent: "",
        streaming: true,
        thinkingActive: sampling.enable_thinking,
      };

      shouldStickBottomRef.current = true;
      setTurns([...historyWithUser, assistantPlaceholder]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const apiKey = loadApiKey();
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        };
        if (apiKey) {
          headers["Authorization"] = `Bearer ${apiKey}`;
        }

        const reqBody = buildApiPayloadFromHistory(historyWithUser, toolsCheck.tools);
        const resp = await fetch(resolveApiUrl("/api/v1/chat/stream"), {
          method: "POST",
          headers,
          body: JSON.stringify(reqBody),
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          let errMsg = `请求失败 (HTTP ${resp.status})`;
          try {
            const errJson = await resp.json();
            if (typeof errJson?.detail === "string") errMsg = errJson.detail;
          } catch {
            // ignore
          }
          throw new Error(errMsg);
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const rawEvent = buffer.slice(0, boundary).trim();
            buffer = buffer.slice(boundary + 2);
            boundary = buffer.indexOf("\n\n");

            if (!rawEvent) continue;
            for (const line of rawEvent.split("\n")) {
              const trimmed = line.trim();
              if (!trimmed.startsWith("data:")) continue;
              const jsonStr = trimmed.slice(5).trim();
              if (!jsonStr || jsonStr === "[DONE]") continue;

              let evt: Record<string, unknown>;
              try {
                evt = JSON.parse(jsonStr) as Record<string, unknown>;
              } catch {
                continue;
              }

              if (evt.type === "error") {
                const errText = String(evt.error || "推理出错");
                setTurns((prev) =>
                  prev.map((t) =>
                    t.id === assistantId
                      ? { ...t, error: errText, streaming: false, thinkingActive: false }
                      : t
                  )
                );
                break;
              }

              if (evt.type === "delta") {
                const rDelta = String(evt.reasoning || "");
                const cDelta = String(evt.content || "");
                const tcDelta = Array.isArray(evt.tool_calls)
                  ? (evt.tool_calls as ToolCallItem[])
                  : undefined;

                setTurns((prev) =>
                  prev.map((t) => {
                    if (t.id !== assistantId) return t;
                    const nextReason = (t.reasoningContent || "") + rDelta;
                    const nextContent = t.content + cDelta;
                    return {
                      ...t,
                      reasoningContent: nextReason,
                      content: nextContent,
                      toolCalls: tcDelta || t.toolCalls,
                      thinkingActive: Boolean(nextReason && !nextContent && !tcDelta),
                    };
                  })
                );
              } else if (evt.type === "usage") {
                setTurns((prev) =>
                  prev.map((t) =>
                    t.id === assistantId
                      ? {
                          ...t,
                          usage: {
                            promptTokens: Number(evt.prompt_tokens || 0),
                            completionTokens: Number(evt.completion_tokens || 0),
                            totalTokens: Number(evt.total_tokens || 0),
                            thinkingSec: Number(evt.thinking_sec || 0),
                            elapsedSec: Number(evt.elapsed_sec || 0),
                            tokensPerSec: Number(evt.tokens_per_sec || 0),
                            mock: Boolean(evt.mock),
                          },
                        }
                      : t
                  )
                );
              } else if (evt.type === "done") {
                setTurns((prev) =>
                  prev.map((t) =>
                    t.id === assistantId
                      ? { ...t, streaming: false, thinkingActive: false }
                      : t
                  )
                );
              }
            }
          }
        }

        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantId ? { ...t, streaming: false, thinkingActive: false } : t
          )
        );
      } catch (err) {
        if ((err as Error)?.name === "AbortError") {
          setTurns((prev) =>
            prev.map((t) =>
              t.id === assistantId
                ? {
                    ...t,
                    streaming: false,
                    thinkingActive: false,
                    content: t.content || "（已手动停止生成）",
                  }
                : t
            )
          );
        } else {
          const errMsg = err instanceof Error ? err.message : "流式请求失败";
          setTurns((prev) =>
            prev.map((t) =>
              t.id === assistantId
                ? { ...t, error: errMsg, streaming: false, thinkingActive: false }
                : t
            )
          );
          message.error(errMsg);
        }
      } finally {
        abortControllerRef.current = null;
        setIsStreaming(false);
      }
    },
    [buildApiPayloadFromHistory, message, parseToolsSafe, sampling.enable_thinking]
  );

  const handleSendSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (isStreaming || uploadingCount > 0) return;

    const trimmed = inputText.trim();
    if (!trimmed && pendingAttachments.length === 0) {
      message.warning("请输入对话内容或上传图片/视频。");
      return;
    }

    const userTurn: ChatTurn = {
      id: nextId("user"),
      role: "user",
      content: trimmed,
      attachments: pendingAttachments.length ? [...pendingAttachments] : undefined,
    };

    const nextHistory = [...turns.filter((t) => !t.error), userTurn];
    setInputText("");
    setPendingAttachments([]);
    await streamConversation(nextHistory);
  };

  const handleRegenerateLast = async () => {
    if (isStreaming || turns.length === 0) return;
    let cutIdx = turns.length;
    if (turns[turns.length - 1].role === "assistant") {
      cutIdx = turns.length - 1;
    }
    const baseHistory = turns.slice(0, cutIdx);
    if (!baseHistory.some((t) => t.role === "user")) return;
    await streamConversation(baseHistory);
  };

  const handleStopStreaming = () => {
    abortControllerRef.current?.abort();
  };

  const handleResetSampling = () => {
    setSampling(DEFAULT_QWEN_SAMPLING);
    message.success("已恢复推荐采样参数");
  };

  const copyPlainText = async (text: string, tip = "已复制到剪贴板") => {
    try {
      await navigator.clipboard.writeText(text);
      message.success(tip);
    } catch {
      message.warning("复制失败，请手动选中复制");
    }
  };

  const latestSpeed = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      const u = turns[i].usage;
      if (u && u.tokensPerSec > 0) return u;
    }
    return null;
  }, [turns]);

  const sampleRequestBody = useMemo(() => {
    const sampleTurns: ChatTurn[] = turns.length
      ? turns
      : [{ id: "sample", role: "user", content: inputText.trim() || "请简要介绍 Qwen3.8-27B 的核心多模态与长上下文特性。" }];
    return buildApiPayloadFromHistory(sampleTurns) as unknown as Record<string, unknown>;
  }, [buildApiPayloadFromHistory, inputText, turns]);

  const renderCustomApiTabs = useCallback(
    ({ origin, savedKey, authRequired, copyText }: StudioCustomApiTabContext) => {
      const effectiveKey = savedKey || (authRequired ? "<YOUR_APP_API_KEY>" : "EMPTY");
      const authHeaderCurl =
        savedKey || authRequired ? `  -H "Authorization: Bearer ${effectiveKey}" \\\n` : "";

      const claudeCodeSnippet = `# Qwen3.8-27B 原生兼容 Anthropic /v1/messages 协议，可直接驱动 Claude Code：
export ANTHROPIC_BASE_URL="${origin}"
export ANTHROPIC_AUTH_TOKEN="${effectiveKey}"
export ANTHROPIC_API_KEY="${effectiveKey}"
export ANTHROPIC_MODEL="qwen3.8-27b"
export ANTHROPIC_SMALL_FAST_MODEL="qwen3.8-27b"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

claude --model qwen3.8-27b`;

      const sysLine = sampling.system_prompt.trim()
        ? `        {"role": "system", "content": ${JSON.stringify(sampling.system_prompt.trim())}},\n`
        : "";
      const effortLine = sampling.enable_thinking
        ? `        "reasoning_effort": "${sampling.reasoning_effort}",\n`
        : "";

      const openaiPySnippet = `from openai import OpenAI

client = OpenAI(
    base_url="${origin}/v1",
    api_key="${effectiveKey}",
)

stream = client.chat.completions.create(
    model="qwen3.8-27b",
    messages=[
${sysLine}        {"role": "user", "content": "请分析这段代码的时间复杂度并给出优化方案"},
    ],
    max_tokens=${sampling.max_tokens},
    temperature=${sampling.temperature},
    top_p=${sampling.top_p},
    presence_penalty=${sampling.presence_penalty},
    frequency_penalty=${sampling.frequency_penalty},
    stream=True,
    extra_body={
        "top_k": ${sampling.top_k},
        "min_p": ${sampling.min_p},
        "repetition_penalty": ${sampling.repetition_penalty},
${effortLine}        "chat_template_kwargs": {"enable_thinking": ${sampling.enable_thinking ? "True" : "False"}},
    },
)

for chunk in stream:
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    reasoning = getattr(delta, "reasoning_content", None)
    if reasoning:
        print(reasoning, end="", flush=True)
    if delta.content:
        print(delta.content, end="", flush=True)`;

      const curlPayload = JSON.stringify(
        {
          model: "qwen3.8-27b",
          messages: [
            ...(sampling.system_prompt.trim()
              ? [{ role: "system", content: sampling.system_prompt.trim() }]
              : []),
            { role: "user", content: "你好，请用一句话介绍你自己。" },
          ],
          max_tokens: sampling.max_tokens,
          temperature: sampling.temperature,
          top_p: sampling.top_p,
          top_k: sampling.top_k,
          chat_template_kwargs: { enable_thinking: sampling.enable_thinking },
          ...(sampling.enable_thinking ? { reasoning_effort: sampling.reasoning_effort } : {}),
        },
        null,
        2
      );

      const curlSnippet = `# 1. OpenAI 兼容接口 (/v1/chat/completions)
curl -X POST "${origin}/v1/chat/completions" \\
  -H "Content-Type: application/json" \\
${authHeaderCurl}  -d '${curlPayload.replace(/'/g, "'\\''")}'

# 2. 查询在线模型与最大上下文 (/v1/models)
curl "${origin}/v1/models"${savedKey || authRequired ? ` -H "Authorization: Bearer ${effectiveKey}"` : ""}`;

      return [
        {
          key: "claude-code",
          label: (
            <span>
              <CodeOutlined /> Claude Code 直连 (/v1/messages)
            </span>
          ),
          children: (
            <Space direction="vertical" size={8} style={{ inlineSize: "100%" }}>
              <Button
                htmlType="button"
                size="small"
                type="primary"
                ghost
                icon={<CopyOutlined />}
                onClick={() => void copyText(claudeCodeSnippet, "已复制 Claude Code 配置命令")}
              >
                一键复制 Claude Code 环境变量
              </Button>
              <pre className="studio-code-block">{claudeCodeSnippet}</pre>
            </Space>
          ),
        },
        {
          key: "openai-sdk",
          label: (
            <span>
              <CodeOutlined /> OpenAI Python SDK (/v1/chat/completions)
            </span>
          ),
          children: (
            <Space direction="vertical" size={8} style={{ inlineSize: "100%" }}>
              <Button
                htmlType="button"
                size="small"
                type="primary"
                ghost
                icon={<CopyOutlined />}
                onClick={() => void copyText(openaiPySnippet, "已复制 OpenAI Python 流式代码")}
              >
                一键复制 Python 代码（已同步右侧参数）
              </Button>
              <pre className="studio-code-block">{openaiPySnippet}</pre>
            </Space>
          ),
        },
        {
          key: "curl",
          label: (
            <span>
              <CodeOutlined /> cURL 命令行示例
            </span>
          ),
          children: (
            <Space direction="vertical" size={8} style={{ inlineSize: "100%" }}>
              <Button
                htmlType="button"
                size="small"
                type="primary"
                ghost
                icon={<CopyOutlined />}
                onClick={() => void copyText(curlSnippet, "已复制 cURL 命令")}
              >
                一键复制 cURL 命令
              </Button>
              <pre className="studio-code-block">{curlSnippet}</pre>
            </Space>
          ),
        },
      ];
    },
    [sampling]
  );

  // ---------------------------------------------------------------------------
  // Left Main Column: Multimodal Chat & Reasoning Transcript + Composer
  // ---------------------------------------------------------------------------
  const leftPane = (
    <div className="studio-chat-stage">
      {/* Stage Top Bar */}
      <div className="studio-chat-header">
        <Space size={8} wrap>
          <MessageOutlined style={{ color: "var(--studio-accent)" }} />
          <Text strong style={{ fontSize: 14 }}>
            多模态对话与推理测试台
          </Text>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>
            256K 上下文 · 图像/视频理解
          </Tag>
          {latestSpeed && (
            <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
              {latestSpeed.tokensPerSec.toFixed(1)} tok/s · 共 {latestSpeed.totalTokens} tokens
            </Tag>
          )}
        </Space>

        <Space size={6}>
          {turns.length > 0 && !isStreaming && (
            <Button
              htmlType="button"
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => void handleRegenerateLast()}
            >
              重试上一轮
            </Button>
          )}
          <Popconfirm
            title="清空当前对话记录？"
            okText="清空"
            cancelText="取消"
            disabled={turns.length === 0 || isStreaming}
            onConfirm={() => setTurns([])}
          >
            <Button
              htmlType="button"
              size="small"
              type="text"
              danger
              disabled={turns.length === 0 || isStreaming}
              icon={<DeleteOutlined />}
            >
              清空对话
            </Button>
          </Popconfirm>
        </Space>
      </div>

      {/* Scrollable Transcript */}
      <div
        ref={transcriptRef}
        className="studio-chat-transcript"
        onScroll={handleTranscriptScroll}
        aria-live="polite"
      >
        {turns.length === 0 ? (
          <div className="studio-chat-empty">
            <div
              style={{
                inlineSize: 44,
                blockSize: 44,
                borderRadius: 12,
                background: "var(--studio-accent-soft)",
                border: "1px solid var(--studio-accent-border)",
                display: "grid",
                placeContent: "center",
                color: "var(--studio-accent)",
                fontSize: 20,
              }}
            >
              <BulbOutlined />
            </div>
            <div style={{ fontWeight: 700, fontSize: 15.5, color: "var(--studio-text)" }}>
              Qwen3.8-27B 多模态深度思考工作台
            </div>
            <Text type="secondary" style={{ fontSize: 13, lineHeight: 1.6 }}>
              直接输入问题开始对话，或拖拽 / <code>⌘+V</code> 粘贴你自己的图片与视频进行视觉理解。
              同时对外开放标准 <code>/v1/chat/completions</code> 与 Claude Code <code>/v1/messages</code> 接口（点击右上角「API 调用代码」即可复制）。
            </Text>
          </div>
        ) : (
          turns.map((turn, idx) => {
            const isLastAssistant = turn.role === "assistant" && idx === turns.length - 1;
            return (
              <div key={turn.id} className="studio-chat-turn" data-role={turn.role}>
                <div className="studio-chat-bubble">
                  {/* User Attached Images & Videos */}
                  {turn.attachments && turn.attachments.length > 0 && (
                    <div className="studio-chat-media-row">
                      {turn.attachments.map((att) =>
                        att.kind === "video" ? (
                          <video
                            key={att.id}
                            src={att.previewUrl}
                            controls
                            preload="metadata"
                            className="studio-chat-media-video"
                          />
                        ) : (
                          <img
                            key={att.id}
                            src={att.previewUrl}
                            alt={att.filename}
                            className="studio-chat-media-thumb"
                            onClick={() => {
                              setLightboxImage({ url: att.previewUrl, name: att.filename });
                              requestAnimationFrame(() => lightboxRef.current?.showModal());
                            }}
                          />
                        )
                      )}
                    </div>
                  )}

                  {/* Assistant Collapsible Reasoning (<think>) */}
                  {turn.role === "assistant" && (turn.reasoningContent || turn.thinkingActive) && (
                    <ThinkingDisclosure
                      reasoning={turn.reasoningContent}
                      thinkingActive={turn.thinkingActive}
                      thinkingSec={turn.usage?.thinkingSec}
                    />
                  )}

                  {/* Error or Content */}
                  {turn.error ? (
                    <Alert type="error" showIcon message={turn.error} />
                  ) : turn.role === "assistant" ? (
                    turn.content ? (
                      <MarkdownBody text={turn.content} />
                    ) : turn.streaming && !turn.thinkingActive ? (
                      <Space size={6} style={{ color: "var(--studio-text-muted)", fontSize: 13 }}>
                        <LoadingOutlined />
                        <span>正在生成回复…</span>
                      </Space>
                    ) : null
                  ) : (
                    <div style={{ whiteSpace: "pre-wrap" }}>{turn.content}</div>
                  )}

                  {/* Assistant Tool Calls */}
                  {turn.toolCalls && turn.toolCalls.length > 0 && (
                    <div style={{ marginBlockStart: turn.content ? 8 : 0, display: "flex", flexDirection: "column", gap: 6 }}>
                      {turn.toolCalls.map((tc) => (
                        <div key={tc.id || tc.function.name} className="studio-md-codeblock">
                          <div className="studio-md-codeheader">
                            <span>工具调用 · {tc.function.name}</span>
                            <Tag color="processing" style={{ marginInlineEnd: 0, fontSize: 11 }}>
                              tool_calls
                            </Tag>
                          </div>
                          <pre className="studio-md-codepre">{tc.function.arguments}</pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Subtle Per-Message Metadata & Actions */}
                <div className="studio-chat-meta-row studio-tabular">
                  {turn.usage && (
                    <span>
                      输入 {turn.usage.promptTokens} · 输出 {turn.usage.completionTokens} tokens ·{" "}
                      {turn.usage.tokensPerSec.toFixed(1)} tok/s · {turn.usage.elapsedSec}s
                    </span>
                  )}
                  {turn.content && !turn.streaming && (
                    <button
                      type="button"
                      onClick={() => void copyPlainText(turn.content, "已复制消息内容")}
                      style={{
                        border: 0,
                        background: "none",
                        padding: 0,
                        color: "var(--studio-text-muted)",
                        cursor: "pointer",
                        fontSize: "0.75rem",
                      }}
                    >
                      复制
                    </button>
                  )}
                  {isLastAssistant && !turn.streaming && (
                    <button
                      type="button"
                      onClick={() => void handleRegenerateLast()}
                      style={{
                        border: 0,
                        background: "none",
                        padding: 0,
                        color: "var(--studio-accent)",
                        cursor: "pointer",
                        fontSize: "0.75rem",
                      }}
                    >
                      重新生成
                    </button>
                  )}
                  {!isStreaming && (
                    <button
                      type="button"
                      onClick={() => setTurns((prev) => prev.filter((item) => item.id !== turn.id))}
                      style={{
                        border: 0,
                        background: "none",
                        padding: 0,
                        color: "var(--studio-text-muted)",
                        cursor: "pointer",
                        fontSize: "0.75rem",
                      }}
                    >
                      删除
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Composer Dock */}
      <form
        ref={formRef}
        onSubmit={(e) => void handleSendSubmit(e)}
        className={`studio-chat-composer${draggingMedia ? " studio-chat-ComposerDragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDraggingMedia(true);
        }}
        onDragLeave={() => setDraggingMedia(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDraggingMedia(false);
          if (e.dataTransfer.files?.length) {
            void handleUploadFiles(e.dataTransfer.files);
          }
        }}
      >
        <input
          ref={fileInputRef}
          id={fileInputId}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.webp,.gif,.mp4,.webm,.mov,.mkv,image/*,video/*"
          className="studio-visually-hidden"
          onChange={(e) => {
            if (e.target.files?.length) {
              void handleUploadFiles(e.target.files);
            }
            e.target.value = "";
          }}
        />

        {/* Pending Multimodal Attachment Chips */}
        {pendingAttachments.length > 0 && (
          <div className="studio-chat-attachments">
            {pendingAttachments.map((att) => {
              const { stem, ext } = splitFilename(att.filename);
              return (
                <div key={att.id} className="studio-chat-attachment-chip">
                  {att.kind === "video" ? (
                    <VideoCameraOutlined style={{ color: "var(--studio-accent)", fontSize: 15, flexShrink: 0 }} />
                  ) : (
                    <img src={att.previewUrl} alt={att.filename} className="studio-chat-attachment-thumb" />
                  )}
                  <span className="studio-filename" style={{ fontSize: 12 }}>
                    <span>{stem}</span>
                    {ext}
                  </span>
                  <button
                    type="button"
                    aria-label={`移除附件 ${att.filename}`}
                    onClick={() =>
                      setPendingAttachments((prev) => prev.filter((item) => item.id !== att.id))
                    }
                    style={{
                      border: 0,
                      background: "none",
                      padding: 2,
                      cursor: "pointer",
                      color: "var(--studio-text-muted)",
                      display: "inline-flex",
                      flexShrink: 0,
                    }}
                  >
                    <CloseOutlined style={{ fontSize: 11 }} />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        <label htmlFor={composerInputId} className="studio-visually-hidden">
          输入消息（Enter 发送，Shift + Enter 换行）
        </label>
        <textarea
          ref={textareaRef}
          id={composerInputId}
          className="studio-chat-textarea"
          placeholder="输入消息（Enter 发送，Shift + Enter 换行；支持直接拖拽或 ⌘/Ctrl+V 粘贴图片与视频）..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onCompositionEnd={(e) => {
            lastCompositionEndRef.current = e.nativeEvent.timeStamp;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (e.nativeEvent.isComposing || e.keyCode === 229) {
                return;
              }
              if (
                lastCompositionEndRef.current !== null &&
                Math.abs(e.nativeEvent.timeStamp - lastCompositionEndRef.current) < 50
              ) {
                return;
              }
              formRef.current?.requestSubmit();
            }
          }}
          onPaste={(e) => {
            const items = e.clipboardData?.items;
            if (!items) return;
            const mediaFiles: File[] = [];
            for (let i = 0; i < items.length; i += 1) {
              const it = items[i];
              if (it.type.startsWith("image/") || it.type.startsWith("video/")) {
                const f = it.getAsFile();
                if (f) mediaFiles.push(f);
              }
            }
            if (mediaFiles.length > 0) {
              e.preventDefault();
              void handleUploadFiles(mediaFiles);
            }
          }}
        />

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <Button
            htmlType="button"
            size="small"
            icon={uploadingCount > 0 ? <LoadingOutlined /> : <PaperClipOutlined />}
            loading={uploadingCount > 0}
            onClick={() => fileInputRef.current?.click()}
          >
            上传图片 / 视频
          </Button>

          {isStreaming ? (
            <Button
              htmlType="button"
              danger
              type="primary"
              icon={<StopOutlined />}
              onClick={handleStopStreaming}
            >
              停止生成
            </Button>
          ) : (
            <Button
              htmlType="submit"
              type="primary"
              icon={<SendOutlined />}
              disabled={uploadingCount > 0}
            >
              发送 (Enter)
            </Button>
          )}
        </div>
      </form>

      {/* Native Light-Dismiss Image Zoom Dialog */}
      <dialog
        ref={lightboxRef}
        className="studio-lightbox-dialog"
        aria-labelledby={lightboxTitleId}
        {...({ closedby: "any" } as Record<string, string>)}
      >
        {lightboxImage && (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBlockEnd: 10 }}>
              <Space size={6}>
                <PictureOutlined style={{ color: "var(--studio-accent)" }} />
                <Text id={lightboxTitleId} strong style={{ fontSize: 14 }}>
                  {lightboxImage.name}
                </Text>
              </Space>
              <Button
                htmlType="button"
                size="small"
                icon={<CloseOutlined />}
                onClick={() => lightboxRef.current?.close()}
              >
                关闭 (Esc)
              </Button>
            </div>
            <div style={{ maxBlockSize: "80dvh", overflow: "auto" }}>
              <img
                src={lightboxImage.url}
                alt={lightboxImage.name}
                style={{ maxInlineSize: "100%", blockSize: "auto", marginInline: "auto", borderRadius: 8 }}
              />
            </div>
          </>
        )}
      </dialog>
    </div>
  );

  // ---------------------------------------------------------------------------
  // Right Sticky Column: Flat System Prompt, Thinking & Sampling Controls
  // ---------------------------------------------------------------------------
  const rightPane = (
    <>
      {/* 1. System Prompt & Thinking Control */}
      <Card className="studio-card" title="系统指令与思考模式">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <div className="studio-field-group">
            <div className="studio-field-label">
              <label htmlFor={sysPromptId}>系统提示词 (System Prompt)</label>
            </div>
            <TextArea
              id={sysPromptId}
              rows={3}
              maxLength={32000}
              placeholder="可选：设定角色身份、输出语言、代码风格或格式规范（留空使用模型默认）..."
              value={sampling.system_prompt}
              onChange={(e) => updateSampling("system_prompt", e.target.value)}
            />
          </div>

          <div
            style={{
              padding: "0.65rem 0.75rem",
              borderRadius: "0.6rem",
              background: "var(--studio-surface-subtle)",
              border: "1px solid var(--studio-border)",
              display: "flex",
              flexDirection: "column",
              gap: "0.55rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <Space size={6}>
                <BulbOutlined style={{ color: "var(--studio-accent)" }} />
                <Text strong style={{ fontSize: 13 }}>
                  深度思考链 (&lt;think&gt;)
                </Text>
              </Space>
              <Switch
                size="small"
                checked={sampling.enable_thinking}
                onChange={handleToggleThinking}
              />
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <Text type="secondary" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>
                思考强度
              </Text>
              <Segmented
                size="small"
                disabled={!sampling.enable_thinking}
                value={sampling.reasoning_effort}
                onChange={(val) => updateSampling("reasoning_effort", val as ReasoningEffort)}
                options={[
                  { label: "低 Low", value: "low" },
                  { label: "中 Med", value: "medium" },
                  { label: "高 High", value: "high" },
                ]}
              />
            </div>
          </div>
        </div>
      </Card>

      {/* 2. Flat Core Sampling Hyperparameters */}
      <Card
        className="studio-card"
        title="核心采样参数"
        extra={
          <Button
            htmlType="button"
            size="small"
            type="text"
            icon={<ClearOutlined />}
            onClick={handleResetSampling}
          >
            恢复默认
          </Button>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
          {/* Max Tokens */}
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>最大输出长度 (Max Tokens)</span>
              <span className="studio-tabular" style={{ color: "var(--studio-accent)" }}>
                {sampling.max_tokens}
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 98px", gap: 10, alignItems: "center" }}>
              <Slider
                min={256}
                max={65536}
                step={256}
                value={sampling.max_tokens}
                onChange={(v) => updateSampling("max_tokens", v)}
              />
              <InputNumber
                size="small"
                min={1}
                max={131072}
                step={256}
                className="studio-tabular"
                style={{ inlineSize: "100%" }}
                value={sampling.max_tokens}
                onChange={(v) => updateSampling("max_tokens", Number(v || 2048))}
              />
            </div>
          </div>

          {/* Temperature */}
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>
                采样温度 (Temperature){" "}
                <Tooltip title="思考模式官方推荐 0.60；非思考直出模式推荐 0.70。设为 0 为确定性贪婪解码。">
                  <span style={{ color: "var(--studio-text-muted)", cursor: "help" }}>ⓘ</span>
                </Tooltip>
              </span>
              <span className="studio-tabular">{sampling.temperature.toFixed(2)}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 84px", gap: 10, alignItems: "center" }}>
              <Slider
                min={0}
                max={2}
                step={0.05}
                value={sampling.temperature}
                onChange={(v) => updateSampling("temperature", v)}
              />
              <InputNumber
                size="small"
                min={0}
                max={2}
                step={0.05}
                className="studio-tabular"
                style={{ inlineSize: "100%" }}
                value={sampling.temperature}
                onChange={(v) => updateSampling("temperature", Number(v ?? 0.6))}
              />
            </div>
          </div>

          {/* Top-P */}
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>核采样阈值 (Top-P)</span>
              <span className="studio-tabular">{sampling.top_p.toFixed(2)}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 84px", gap: 10, alignItems: "center" }}>
              <Slider
                min={0.05}
                max={1}
                step={0.05}
                value={sampling.top_p}
                onChange={(v) => updateSampling("top_p", v)}
              />
              <InputNumber
                size="small"
                min={0.01}
                max={1}
                step={0.05}
                className="studio-tabular"
                style={{ inlineSize: "100%" }}
                value={sampling.top_p}
                onChange={(v) => updateSampling("top_p", Number(v ?? 0.95))}
              />
            </div>
          </div>

          {/* Top-K */}
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>候选词截断 (Top-K，-1 为不限)</span>
              <span className="studio-tabular">{sampling.top_k}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 84px", gap: 10, alignItems: "center" }}>
              <Slider
                min={-1}
                max={200}
                step={1}
                value={sampling.top_k}
                onChange={(v) => updateSampling("top_k", v)}
              />
              <InputNumber
                size="small"
                min={-1}
                max={500}
                step={1}
                className="studio-tabular"
                style={{ inlineSize: "100%" }}
                value={sampling.top_k}
                onChange={(v) => updateSampling("top_k", Number(v ?? 20))}
              />
            </div>
          </div>

          {/* Presence & Repetition Penalty */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
            <div className="studio-field-group">
              <div className="studio-field-label">
                <span style={{ fontSize: 12 }}>存在惩罚 (Presence)</span>
              </div>
              <InputNumber
                size="small"
                min={-2}
                max={2}
                step={0.1}
                className="studio-tabular"
                style={{ inlineSize: "100%" }}
                value={sampling.presence_penalty}
                onChange={(v) => updateSampling("presence_penalty", Number(v ?? 0))}
              />
            </div>

            <div className="studio-field-group">
              <div className="studio-field-label">
                <span style={{ fontSize: 12 }}>重复惩罚 (Repetition)</span>
              </div>
              <InputNumber
                size="small"
                min={0.5}
                max={2}
                step={0.05}
                className="studio-tabular"
                style={{ inlineSize: "100%" }}
                value={sampling.repetition_penalty}
                onChange={(v) => updateSampling("repetition_penalty", Number(v ?? 1.0))}
              />
            </div>
          </div>

          {/* 3. Progressive Disclosure: Low-Level Sampling, JSON Mode & Tool Calling */}
          <details className="studio-native-details">
            <summary>高级控制、JSON 模式与工具调用（可选）</summary>
            <div className="studio-details-body" style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                <div className="studio-field-group">
                  <div className="studio-field-label">
                    <span style={{ fontSize: 12 }}>Min-P 阈值</span>
                  </div>
                  <InputNumber
                    size="small"
                    min={0}
                    max={1}
                    step={0.02}
                    className="studio-tabular"
                    style={{ inlineSize: "100%" }}
                    value={sampling.min_p}
                    onChange={(v) => updateSampling("min_p", Number(v ?? 0))}
                  />
                </div>

                <div className="studio-field-group">
                  <div className="studio-field-label">
                    <span style={{ fontSize: 12 }}>频率惩罚 (Frequency)</span>
                  </div>
                  <InputNumber
                    size="small"
                    min={-2}
                    max={2}
                    step={0.1}
                    className="studio-tabular"
                    style={{ inlineSize: "100%" }}
                    value={sampling.frequency_penalty}
                    onChange={(v) => updateSampling("frequency_penalty", Number(v ?? 0))}
                  />
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                <div className="studio-field-group">
                  <div className="studio-field-label">
                    <span style={{ fontSize: 12 }}>随机种子 (空 = 随机)</span>
                  </div>
                  <InputNumber
                    size="small"
                    min={0}
                    max={9007199254740991}
                    placeholder="随机"
                    className="studio-tabular"
                    style={{ inlineSize: "100%" }}
                    value={sampling.seed}
                    onChange={(v) => updateSampling("seed", v === null || v === undefined ? null : Number(v))}
                  />
                </div>

                <div className="studio-field-group">
                  <div className="studio-field-label">
                    <span style={{ fontSize: 12 }}>输出格式</span>
                  </div>
                  <Select
                    size="small"
                    style={{ inlineSize: "100%" }}
                    value={sampling.response_format}
                    onChange={(v) => updateSampling("response_format", v as ResponseFormatMode)}
                    options={[
                      { label: "自由文本 / Markdown", value: "text" },
                      { label: "严格 JSON 对象", value: "json_object" },
                    ]}
                  />
                </div>
              </div>

              <div className="studio-field-group">
                <div className="studio-field-label">
                  <span style={{ fontSize: 12 }}>停止词 (Stop，逗号分隔)</span>
                </div>
                <Input
                  size="small"
                  placeholder="例如：<|endoftext|>, ###"
                  value={sampling.stop_text}
                  onChange={(e) => updateSampling("stop_text", e.target.value)}
                />
              </div>

              <div className="studio-field-group">
                <div className="studio-field-label">
                  <span style={{ fontSize: 12 }}>工具定义 (Tools JSON，OpenAI 数组格式)</span>
                  <Select
                    size="small"
                    style={{ inlineSize: 92 }}
                    value={sampling.tool_choice}
                    onChange={(v) => updateSampling("tool_choice", v as "auto" | "none" | "required")}
                    options={[
                      { label: "auto", value: "auto" },
                      { label: "required", value: "required" },
                      { label: "none", value: "none" },
                    ]}
                  />
                </div>
                <TextArea
                  rows={3}
                  style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 11.5 }}
                  placeholder='[{"type":"function","function":{"name":"get_weather","parameters":{"type":"object","properties":{"city":{"type":"string"}}}}}]'
                  value={sampling.tools_json}
                  onChange={(e) => updateSampling("tools_json", e.target.value)}
                />
              </div>
            </div>
          </details>
        </div>
      </Card>
    </>
  );

  return (
    <StudioShell
      brandBadge="Q3"
      defaultTitle="Qwen3.8-27B 多模态推理工作台"
      defaultSubtitle="256K 上下文 · 图像/视频理解 · 深度思考流 · OpenAI & Claude Code 原生协议"
      layoutRatio="chat"
      apiModalTitle="Claude Code / OpenAI SDK / HTTP 调用配置（实时同步参数）"
      customApiTabs={renderCustomApiTabs}
      sampleRequestBody={sampleRequestBody}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
