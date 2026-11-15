export type ReasoningEffort = "low" | "medium" | "xhigh";
export type ResponseFormatMode = "text" | "json_object";

export interface ChatAttachmentItem {
  id: string;
  kind: "image" | "video";
  fileId: string;
  filename: string;
  previewUrl: string;
  sizeBytes: number;
}

export interface ToolCallItem {
  id: string;
  type: string;
  function: {
    name: string;
    arguments: string;
  };
}

export interface ChatTurnUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  thinkingSec: number;
  elapsedSec: number;
  tokensPerSec: number;
  mock?: boolean;
}

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  reasoningContent?: string;
  attachments?: ChatAttachmentItem[];
  toolCalls?: ToolCallItem[];
  usage?: ChatTurnUsage;
  streaming?: boolean;
  thinkingActive?: boolean;
  error?: string;
  finishReason?: string;
  stopped?: boolean;
}

export interface QwenSamplingConfig {
  system_prompt: string;
  enable_thinking: boolean;
  reasoning_effort: ReasoningEffort;
  preserve_thinking: boolean;
  max_tokens: number;
  temperature: number;
  top_p: number;
  top_k: number;
  min_p: number;
  presence_penalty: number;
  frequency_penalty: number;
  repetition_penalty: number;
  seed: number | null;
  stop_text: string;
  response_format: ResponseFormatMode;
  tools_json: string;
  tool_choice: "auto" | "none" | "required";
}

export const DEFAULT_QWEN_SAMPLING: QwenSamplingConfig = {
  system_prompt: "",
  enable_thinking: true,
  reasoning_effort: "xhigh",
  preserve_thinking: true,
  max_tokens: 8192,
  temperature: 1.0,
  top_p: 0.95,
  top_k: 20,
  min_p: 0.0,
  presence_penalty: 0.0,
  frequency_penalty: 0.0,
  repetition_penalty: 1.0,
  seed: null,
  stop_text: "",
  response_format: "text",
  tools_json: "",
  tool_choice: "auto",
};
