import {
  Alert,
  BulbOutlined,
  Button,
  Card,
  CloseOutlined,
  CodeBlock,
  CodeOutlined,
  DeleteOutlined,
  Empty,
  ImageLightbox,
  Kbd,
  LoadingOutlined,
  MessageOutlined,
  PaperClipOutlined,
  Popconfirm,
  ReloadOutlined,
  SeedControl,
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
  VideoCameraOutlined,
  resolveApiUrl,
  uploadMediaFile,
  useStudioFeedback,
  useStudioLocale,
  type StageImageEntry,
} from "@colab/shared";
import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { MarkdownBody } from "./MarkdownBody";
import { buildChatMessages, buildOpenAiPayload, parseStopWords, parseToolsJson, readChatEvents } from "./chat";
import {
  ChatAttachmentItem,
  ChatTurn,
  DEFAULT_QWEN_SAMPLING,
  QwenSamplingConfig,
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
  const { t } = useStudioLocale();
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
            <span>{t("Thinking deeply…", "深度思考中…")}</span>
          </Space>
        ) : (
          <span className="studio-tabular">
            {t("Thought process", "思考过程")}
            {thinkingSec ? ` · ${thinkingSec}s` : ""}
            {reasoning ? t(` (${reasoning.length} chars)`, `（${reasoning.length} 字）`) : ""}
          </span>
        )}
      </summary>
      <div className="studio-think-body">{reasoning || t("Building reasoning chain...", "正在构建推理链...")}</div>
    </details>
  );
}

export function QwenChatStudioApp() {
  const { t } = useStudioLocale();
  const composerInputId = useId();
  const sysPromptId = useId();
  const fileInputId = useId();

  const formRef = useRef<HTMLFormElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamingRef = useRef(false);
  const uploadingRef = useRef(false);
  const mountedRef = useRef(true);
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
  const [lightboxImages, setLightboxImages] = useState<StageImageEntry[]>([]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, []);

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

  const handleToggleThinking = (enabled: boolean) => {
    setSampling((prev) => {
      const next = { ...prev, enable_thinking: enabled };
      if (enabled && prev.temperature === 0.7 && prev.top_p === 0.8 && prev.presence_penalty === 1.5) {
        next.temperature = 1.0;
        next.top_p = 0.95;
        next.presence_penalty = 0.0;
      } else if (!enabled && prev.temperature === 1.0 && prev.top_p === 0.95 && prev.presence_penalty === 0.0) {
        next.temperature = 0.7;
        next.top_p = 0.8;
        next.presence_penalty = 1.5;
      }
      return next;
    });
  };

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
    if (!list.length || uploadingRef.current) return;
    if (list.some((file) => !/\.(png|jpe?g|webp|gif|mp4|webm|mov|mkv)$/i.test(file.name))) {
      message.warning(t("Please select supported image or video files.", "请选择支持的图片或视频文件。"));
      return;
    }
    if (list.some((file) => !file.size || file.size > 512 * 1024 * 1024)) {
      message.warning(t("Attachments cannot be empty and each file must be within 512 MB.", "附件不能为空，单个文件需在 512 MB 以内。"));
      return;
    }
    if (pendingAttachments.length + list.length > 12) {
      message.warning(t("Up to 12 image or video attachments per turn.", "单轮最多附加 12 个图片或视频文件。"));
      return;
    }

    uploadingRef.current = true;
    setUploadingCount((c) => c + list.length);
    try {
      for (const file of list) {
        try {
          const uploaded = await uploadMediaFile(file);
          if (!mountedRef.current) return;
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
          message.error(err instanceof Error ? err.message : t(`Upload failed: ${file.name}`, `上传失败：${file.name}`));
        }
      }
    } finally {
      uploadingRef.current = false;
      if (mountedRef.current) setUploadingCount((c) => Math.max(0, c - list.length));
    }
  };

  const parseToolsSafe = useCallback((): { ok: true; tools?: unknown[] } | { ok: false; error: string } => {
    try {
      return { ok: true, tools: parseToolsJson(sampling.tools_json) };
    } catch (err) {
      return { ok: false, error: err instanceof Error ? err.message : String(err) };
    }
  }, [sampling.tools_json]);

  const parsedStops = useMemo(() => parseStopWords(sampling.stop_text), [sampling.stop_text]);

  const buildApiPayloadFromHistory = useCallback(
    (historyTurns: ChatTurn[], toolsOverride?: unknown[]) => {
      const messages = buildChatMessages(historyTurns);
      return {
        model: "qwen3.8-27b",
        system_prompt: sampling.system_prompt,
        messages,
        enable_thinking: sampling.enable_thinking,
        reasoning_effort: sampling.reasoning_effort,
        preserve_thinking: sampling.preserve_thinking,
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
      if (streamingRef.current) return;
      const toolsCheck = parseToolsSafe();
      if (!toolsCheck.ok) {
        message.error(toolsCheck.error);
        return;
      }

      if (parsedStops.length > 8) {
        message.error(t("Up to 8 stop sequences are allowed.", "最多支持 8 个停止词，请删减后再发送。"));
        return;
      }
      streamingRef.current = true;
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
        const headers: Record<string, string> = {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        };

        const reqBody = buildApiPayloadFromHistory(historyWithUser, toolsCheck.tools);
        const resp = await fetch(resolveApiUrl("/api/v1/chat/stream"), {
          method: "POST",
          headers,
          body: JSON.stringify(reqBody),
          signal: controller.signal,
        });

        if (!resp.ok || !resp.body) {
          let errMsg = t(`Request failed (HTTP ${resp.status})`, `请求失败 (HTTP ${resp.status})`);
          try {
            const errJson = await resp.json();
            if (typeof errJson?.detail === "string") errMsg = errJson.detail;
          } catch {
            // ignore
          }
          throw new Error(errMsg);
        }

        let completed = false;
        for await (const evt of readChatEvents(resp.body)) {
          if (evt.type === "error") throw new Error(String(evt.error || t("Inference error", "推理出错")));
          if (evt.type === "delta") {
            const rDelta = String(evt.reasoning || "");
            const cDelta = String(evt.content || "");
            const tcDelta = Array.isArray(evt.tool_calls) ? (evt.tool_calls as ToolCallItem[]) : undefined;
            setTurns((prev) =>
              prev.map((turn) => {
                if (turn.id !== assistantId) return turn;
                const reasoningContent = (turn.reasoningContent || "") + rDelta;
                const content = turn.content + cDelta;
                return {
                  ...turn,
                  reasoningContent,
                  content,
                  toolCalls: tcDelta || turn.toolCalls,
                  thinkingActive: Boolean(reasoningContent && !content && !tcDelta),
                };
              }),
            );
          } else if (evt.type === "usage") {
            setTurns((prev) =>
              prev.map((turn) =>
                turn.id === assistantId
                  ? {
                      ...turn,
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
                  : turn,
              ),
            );
          } else if (evt.type === "done") {
            completed = true;
            setTurns((prev) =>
              prev.map((turn) =>
                turn.id === assistantId
                  ? {
                      ...turn,
                      finishReason: String(evt.finish_reason || "stop"),
                    }
                  : turn,
              ),
            );
            break;
          }
        }
        if (!completed) {
          throw new Error(
            t(
              "Stream disconnected early; response may be incomplete. Click Regenerate to retry.",
              "连接提前中断，回复可能不完整。可点击“重新生成”重试。",
            ),
          );
        }

        setTurns((prev) =>
          prev.map((item) =>
            item.id === assistantId ? { ...item, streaming: false, thinkingActive: false } : item
          )
        );
      } catch (err) {
        if ((err as Error)?.name === "AbortError") {
          setTurns((prev) =>
            prev.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    streaming: false,
                    thinkingActive: false,
                    stopped: true,
                  }
                : item
            )
          );
        } else {
          const errMsg = err instanceof Error ? err.message : t("Streaming request failed", "流式请求失败");
          setTurns((prev) =>
            prev.map((item) =>
              item.id === assistantId
                ? { ...item, error: errMsg, streaming: false, thinkingActive: false }
                : item
            )
          );
          if (mountedRef.current) message.error(errMsg);
        }
      } finally {
        abortControllerRef.current = null;
        streamingRef.current = false;
        if (mountedRef.current) setIsStreaming(false);
      }
    },
    [buildApiPayloadFromHistory, message, parseToolsSafe, parsedStops.length, sampling.enable_thinking, t]
  );

  const handleSendSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (streamingRef.current || uploadingRef.current) return;
    const toolsCheck = parseToolsSafe();
    if (!toolsCheck.ok) {
      message.error(toolsCheck.error);
      return;
    }
    if (parsedStops.length > 8) {
      message.error(t("Up to 8 stop sequences are allowed.", "最多支持 8 个停止词，请删减后再发送。"));
      return;
    }

    const trimmed = inputText.trim();
    if (!trimmed && pendingAttachments.length === 0) {
      message.warning(t("Enter a message or attach an image/video.", "请输入对话内容或上传图片/视频。"));
      return;
    }

    const userTurn: ChatTurn = {
      id: nextId("user"),
      role: "user",
      content: trimmed,
      attachments: pendingAttachments.length ? [...pendingAttachments] : undefined,
    };

    const nextHistory = [...turns.filter((item) => !item.error), userTurn];
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
    if (!baseHistory.some((item) => item.role === "user")) return;
    await streamConversation(baseHistory);
  };

  const handleStopStreaming = () => {
    abortControllerRef.current?.abort();
  };

  const handleResetSampling = () => {
    setSampling((previous) => ({
      ...DEFAULT_QWEN_SAMPLING,
      system_prompt: previous.system_prompt,
    }));
    message.success(t("Restored default generation settings", "已恢复默认生成设置"));
  };

  const copyPlainText = async (text: string, tip?: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success(tip ?? t("Copied to clipboard", "已复制到剪贴板"));
    } catch {
      message.warning(t("Copy failed; please select and copy manually", "复制失败，请手动选中复制"));
    }
  };

  const latestSpeed = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      const u = turns[i].usage;
      if (u && u.tokensPerSec > 0) return u;
    }
    return null;
  }, [turns]);

  const sampleTurns = useMemo<ChatTurn[]>(() => {
    if (inputText.trim() || pendingAttachments.length) {
      return [...turns, { id: "draft", role: "user", content: inputText.trim(), attachments: pendingAttachments }];
    }
    const requestTurns = turns.at(-1)?.role === "assistant" ? turns.slice(0, -1) : turns;
    return requestTurns.length
      ? requestTurns
      : [{ id: "sample", role: "user", content: t("Hello, please briefly introduce yourself.", "你好，请简要介绍你自己。") }];
  }, [inputText, pendingAttachments, t, turns]);

  const sampleRequestBody = useMemo(() => {
    const parsed = parseToolsSafe();
    return buildApiPayloadFromHistory(sampleTurns, parsed.ok ? parsed.tools : undefined) as unknown as Record<string, unknown>;
  }, [buildApiPayloadFromHistory, parseToolsSafe, sampleTurns]);

  const renderCustomApiTabs = useCallback(
    ({ origin, savedKey, authRequired }: StudioCustomApiTabContext) => {
      const effectiveKey = savedKey || (authRequired ? "<YOUR_APP_API_KEY>" : "EMPTY");
      const authHeaderCurl =
        savedKey || authRequired ? `  -H "Authorization: Bearer ${effectiveKey}" \\\n` : "";

      const claudeCodeSnippet = `# ${t(
        "Qwen3.8-27B natively implements the Anthropic /v1/messages API for Claude Code:",
        "Qwen3.8-27B 原生兼容 Anthropic /v1/messages 协议，可直接驱动 Claude Code：",
      )}
export ANTHROPIC_BASE_URL="${origin}"
export ANTHROPIC_AUTH_TOKEN="${effectiveKey}"
export ANTHROPIC_API_KEY="${effectiveKey}"
export ANTHROPIC_MODEL="qwen3.8-27b"
export ANTHROPIC_SMALL_FAST_MODEL="qwen3.8-27b"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

claude --model qwen3.8-27b`;

      let requestPayload: Record<string, unknown>;
      try {
        requestPayload = {
          ...buildOpenAiPayload(sampling, sampleTurns),
          stream: true,
          stream_options: { include_usage: true },
        };
      } catch (err) {
        return [
          {
            key: "validation",
            label: t("Validation", "参数检查"),
            children: <Alert type="warning" showIcon message={err instanceof Error ? err.message : String(err)} />,
          },
        ];
      }
      const payloadJson = JSON.stringify(requestPayload, null, 2);
      const openaiPySnippet = `import json
from openai import OpenAI

client = OpenAI(
    base_url=${JSON.stringify(`${origin}/v1`)},
    api_key=${JSON.stringify(effectiveKey)},
)

# ${t(
        "Includes current prompt, attachments, sampling, JSON mode, and tools.",
        "当前问题、附件、采样参数、JSON 模式和工具配置均已带入。",
      )}
# ${t(
        "upload: attachment refs are valid only on this active Colab instance.",
        "upload: 引用只在当前 Colab 实例中有效。",
      )}
payload = json.loads(${JSON.stringify(payloadJson)})
extra_keys = ("top_k", "min_p", "repetition_penalty", "chat_template_kwargs")
extra_body = {key: payload.pop(key) for key in extra_keys if key in payload}
stream = client.chat.completions.create(**payload, extra_body=extra_body)

for chunk in stream:
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
    if reasoning:
        print(reasoning, end="", flush=True)
    if delta.content:
        print(delta.content, end="", flush=True)
    if delta.tool_calls:
        print(delta.tool_calls)`;

      const curlSnippet = `# ${t(
        "Streaming request synced with your current playground settings",
        "流式调用；参数与当前工作台一致",
      )}
curl -N -X POST "${origin}/v1/chat/completions" \\
  -H "Content-Type: application/json" \\
${authHeaderCurl}  -d '${payloadJson.replace(/'/g, "'\\''")}'

# ${t("List available models", "查询在线模型")}
curl "${origin}/v1/models"${savedKey || authRequired ? ` -H "Authorization: Bearer ${effectiveKey}"` : ""}`;

      return [
        {
          key: "claude-code",
          label: t("Claude Code (/v1/messages)", "Claude Code 直连 (/v1/messages)"),
          icon: <CodeOutlined />,
          children: <CodeBlock code={claudeCodeSnippet} language="bash" />,
        },
        {
          key: "openai-sdk",
          label: "OpenAI Python SDK (/v1/chat/completions)",
          icon: <CodeOutlined />,
          children: <CodeBlock code={openaiPySnippet} language="python" />,
        },
        {
          key: "curl",
          label: t("cURL CLI", "cURL 命令行示例"),
          icon: <CodeOutlined />,
          children: <CodeBlock code={curlSnippet} language="bash" />,
        },
      ];
    },
    [sampling, sampleTurns, t]
  );

  const leftPane = (
    <div className="studio-chat-stage">
      <div className="studio-chat-header">
        <Space size={8} wrap>
          <MessageOutlined style={{ color: "var(--studio-accent)" }} />
          <Text strong style={{ fontSize: 14 }}>
            {t("Multimodal Chat & Reasoning Playground", "多模态对话与推理测试台")}
          </Text>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>
            {t("256K Context · Image / Video Vision", "256K 上下文 · 图像/视频理解")}
          </Tag>
          {latestSpeed && (
            <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
              {latestSpeed.tokensPerSec.toFixed(1)} tok/s · {t(`${latestSpeed.totalTokens} tokens`, `共 ${latestSpeed.totalTokens} tokens`)}
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
              {t("Retry Last", "重试上一轮")}
            </Button>
          )}
          <Popconfirm
            title={t("Clear conversation history?", "清空当前对话记录？")}
            okText={t("Clear", "清空")}
            cancelText={t("Cancel", "取消")}
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
              {t("Clear Chat", "清空对话")}
            </Button>
          </Popconfirm>
        </Space>
      </div>

      <div
        ref={transcriptRef}
        className="studio-chat-transcript"
        onScroll={handleTranscriptScroll}
        aria-live="polite"
      >
        <div className="studio-chat-transcript-inner">
        {turns.length === 0 ? (
          <div className="studio-chat-empty">
            <Empty
              title="Qwen3.8-27B"
              description={t(
                "Ask a question or drag/paste images & videos to start multimodal reasoning.",
                "输入问题，或拖拽/粘贴图片与视频开始多模态对话与深度思考。",
              )}
              icon={<BulbOutlined />}
              shape="softBurst"
            />
          </div>
        ) : (
          turns.map((turn, idx) => {
            const isLastAssistant = turn.role === "assistant" && idx === turns.length - 1;
            return (
              <div key={turn.id} className="studio-chat-turn" data-role={turn.role}>
                <div className="studio-chat-bubble">
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
                          <button
                            key={att.id}
                            type="button"
                            className="studio-chat-thumb-btn"
                            aria-label={t(`Inspect image ${att.filename}`, `查看图片 ${att.filename}`)}
                            onClick={() =>
                              setLightboxImages([
                                {
                                  url: att.previewUrl,
                                  filename: att.filename,
                                  width: 1024,
                                  height: 1024,
                                  sizeBytes: att.sizeBytes,
                                  format: "",
                                },
                              ])
                            }
                          >
                            <img
                              src={att.previewUrl}
                              alt={att.filename}
                              className="studio-chat-media-thumb"
                            />
                          </button>
                        )
                      )}
                    </div>
                  )}

                  {turn.role === "assistant" && (turn.reasoningContent || turn.thinkingActive) && (
                    <ThinkingDisclosure
                      reasoning={turn.reasoningContent}
                      thinkingActive={turn.thinkingActive}
                      thinkingSec={turn.usage?.thinkingSec}
                    />
                  )}

                  {turn.error && <Alert type="error" showIcon message={turn.error} />}
                  {turn.role === "assistant" ? (
                    turn.content ? (
                      <MarkdownBody text={turn.content} />
                    ) : turn.streaming && !turn.thinkingActive ? (
                      <Space size={6} style={{ color: "var(--studio-text-muted)", fontSize: 13 }}>
                        <LoadingOutlined />
                        <span>{t("Generating response…", "正在生成回复…")}</span>
                      </Space>
                    ) : null
                  ) : (
                    <div style={{ whiteSpace: "pre-wrap" }}>{turn.content}</div>
                  )}

                  {turn.toolCalls && turn.toolCalls.length > 0 && (
                    <div style={{ marginBlockStart: turn.content ? 8 : 0, display: "flex", flexDirection: "column", gap: 6 }}>
                      {turn.toolCalls.map((tc) => (
                        <CodeBlock
                          key={tc.id || tc.function.name}
                          code={tc.function.arguments}
                          language="json"
                          title={t(`Tool Call · ${tc.function.name}`, `工具调用 · ${tc.function.name}`)}
                        />
                      ))}
                    </div>
                  )}
                </div>

                <div className="studio-chat-meta-row studio-tabular">
                  {turn.stopped && <span>{t("Stopped", "已停止生成")}</span>}
                  {turn.finishReason === "length" && (
                    <span>
                      {t(
                        "Hit max output length; raise Max Tokens and regenerate if needed",
                        "已达输出长度上限，可增加 Max Tokens 后重新生成",
                      )}
                    </span>
                  )}
                  {turn.usage && (
                    <span>
                      {t(
                        `In ${turn.usage.promptTokens} · Out ${turn.usage.completionTokens} tokens · ${turn.usage.tokensPerSec.toFixed(1)} tok/s · ${turn.usage.elapsedSec}s`,
                        `输入 ${turn.usage.promptTokens} · 输出 ${turn.usage.completionTokens} tokens · ${turn.usage.tokensPerSec.toFixed(1)} tok/s · ${turn.usage.elapsedSec}s`,
                      )}
                    </span>
                  )}
                  {turn.content && !turn.streaming && (
                    <button
                      type="button"
                      className="studio-chat-action-btn"
                      onClick={() => void copyPlainText(turn.content, t("Message copied", "已复制消息内容"))}
                    >
                      {t("Copy", "复制")}
                    </button>
                  )}
                  {isLastAssistant && !turn.streaming && (
                    <button
                      type="button"
                      className="studio-chat-action-btn"
                      data-tone="primary"
                      onClick={() => void handleRegenerateLast()}
                    >
                      {t("Regenerate", "重新生成")}
                    </button>
                  )}
                  {!isStreaming && (
                    <button
                      type="button"
                      className="studio-chat-action-btn"
                      onClick={() => setTurns((prev) => prev.filter((item) => item.id !== turn.id))}
                    >
                      {t("Delete", "删除")}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
        </div>
      </div>

      <form
        ref={formRef}
        onSubmit={(e) => void handleSendSubmit(e)}
        className="studio-chat-composer"
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
        <Card
          variant="outlined"
          className={`studio-chat-composer-card${draggingMedia ? " studio-chat-ComposerDragging" : ""}`}
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
                    aria-label={t(`Remove attachment ${att.filename}`, `移除附件 ${att.filename}`)}
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
          {t("Type a message (Enter to send, Shift+Enter for new line)", "输入消息（Enter 发送，Shift + Enter 换行）")}
        </label>
        <textarea
          ref={textareaRef}
          id={composerInputId}
          className="studio-chat-textarea"
          placeholder={t(
            "Message Qwen3.8-27B (Enter to send, Shift+Enter for new line; drag & drop or paste images/videos)...",
            "输入消息（Enter 发送，Shift + Enter 换行；支持直接拖拽或 ⌘/Ctrl+V 粘贴图片与视频）...",
          )}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onCompositionEnd={(e) => {
            lastCompositionEndRef.current = e.nativeEvent.timeStamp;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              if (e.nativeEvent.isComposing || e.keyCode === 229) {
                return;
              }
              if (
                lastCompositionEndRef.current !== null &&
                Math.abs(e.nativeEvent.timeStamp - lastCompositionEndRef.current) < 50
              ) {
                return;
              }
              e.preventDefault();
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
          <Space size={10} wrap>
            <Button
              htmlType="button"
              size="small"
              icon={uploadingCount > 0 ? <LoadingOutlined /> : <PaperClipOutlined />}
              loading={uploadingCount > 0}
              onClick={() => fileInputRef.current?.click()}
            >
              {t("Attach Image / Video", "上传图片 / 视频")}
            </Button>
            <span className="studio-shortcut-hint">
              <Kbd keys={["enter"]} size="sm" />
              <span>{t("Send", "发送")}</span>
              <span aria-hidden="true">·</span>
              <Kbd keys={["shift", "enter"]} size="sm" />
              <span>{t("New line", "换行")}</span>
            </span>
          </Space>

          {isStreaming ? (
            <Button
              htmlType="button"
              danger
              type="primary"
              icon={<StopOutlined />}
              onClick={handleStopStreaming}
            >
              {t("Stop", "停止生成")}
            </Button>
          ) : (
            <Button
              htmlType="submit"
              type="primary"
              icon={<SendOutlined />}
              disabled={uploadingCount > 0}
            >
              {t("Send", "发送")}
            </Button>
          )}
        </div>
        </Card>
      </form>

      <ImageLightbox
        images={lightboxImages}
        open={lightboxImages.length > 0}
        onClose={() => setLightboxImages([])}
      />
    </div>
  );

  const rightPane = (
    <>
      <Card className="studio-card" title={t("Chat Settings", "对话设置")}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="studio-field-group">
            <label htmlFor={sysPromptId}>{t("System Prompt (optional)", "系统提示词（可选）")}</label>
            <TextArea
              id={sysPromptId}
              rows={3}
              maxLength={32000}
              value={sampling.system_prompt}
              onValueChange={(value) => updateSampling("system_prompt", value)}
              placeholder={t(
                "e.g., Answer concisely with runnable code snippets.",
                "例如：用简洁的中文回答，给出可直接运行的代码。",
              )}
            />
          </div>
          <Switch
            label={t("Deep Thinking", "深度思考")}
            description={t("Stream reasoning process before final answer", "先展示推理过程再输出最终回答")}
            checked={sampling.enable_thinking}
            onChange={handleToggleThinking}
            aria-label={t("Deep Thinking", "深度思考")}
          />
        </div>
      </Card>
      <Card
        className="studio-card"
        title={t("Generation Settings", "生成设置")}
        extra={
          <Button type="text" size="small" onClick={handleResetSampling}>
            {t("Reset", "恢复默认")}
          </Button>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="studio-field-group">
            <span>{t("Max Response Length", "回复长度上限")}</span>
            <Select
              aria-label={t("Max Response Length", "回复长度上限")}
              value={String(sampling.max_tokens)}
              onChange={(value) => updateSampling("max_tokens", Number(value))}
              options={[
                { label: t("Short (2048)", "较短（2048）"), value: "2048" },
                { label: t("Standard (8192)", "标准（8192）"), value: "8192" },
                { label: t("Long (16384)", "较长（16384）"), value: "16384" },
                { label: t("Extended (32768)", "长文（32768）"), value: "32768" },
              ]}
            />
          </div>
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>{t("Temperature", "随机程度")}</span>
              <span className="studio-tabular">{sampling.temperature.toFixed(2)}</span>
            </div>
            <Slider
              aria-label={t("Temperature", "随机程度")}
              min={0}
              max={2}
              step={0.05}
              value={sampling.temperature}
              onChange={(value) => updateSampling("temperature", value)}
            />
          </div>
          <SeedControl
            value={sampling.seed || 0}
            onChange={(value) => updateSampling("seed", value > 0 ? value : null)}
          />
        </div>
      </Card>
    </>
  );

  return (
    <StudioShell
      brandBadge="Q3"
      defaultTitle="Qwen3.8-27B"
      defaultSubtitle={t(
        "Multimodal Chat & Deep Thinking · Image & Video Understanding",
        "对话与深度思考 · 图片和视频理解",
      )}
      layoutRatio="chat"
      apiModalTitle={t(
        "Claude Code / OpenAI SDK / HTTP API Setup (live params)",
        "Claude Code / OpenAI SDK / HTTP 调用配置（实时同步参数）",
      )}
      customApiTabs={renderCustomApiTabs}
      sampleRequestBody={sampleRequestBody}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
