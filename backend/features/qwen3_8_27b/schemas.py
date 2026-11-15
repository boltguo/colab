"""Pydantic schemas for Qwen3.8-27B multimodal chat, reasoning, and full vLLM sampling controls."""
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator

ReasoningEffort = Literal["low", "medium", "xhigh"]
ResponseFormatMode = Literal["text", "json_object"]


class QwenAttachment(BaseModel):
    kind: Literal["image", "video"] = Field(
        default="image",
        description="多模态附件类型：image（图片）或 video（视频）",
    )
    file_id: str = Field(
        default="",
        max_length=512,
        description="通过 POST /api/v1/files 上传得到的 file_id（也可传 https:// 或 data: URL）",
    )
    filename: str = Field(
        default="",
        max_length=256,
        description="展示用原始文件名（可选）",
    )


class QwenChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = Field(
        default="user",
        description="消息角色：system / user / assistant / tool",
    )
    content: Union[str, List[Dict[str, Any]]] = Field(
        default="",
        description="消息文本内容或标准 OpenAI 多模态 content 数组",
    )
    attachments: List[QwenAttachment] = Field(
        default_factory=list,
        max_length=12,
        description="当前轮次附加的图片或视频列表（自动转换为 vLLM 多模态输入）",
    )
    reasoning_content: Optional[str] = Field(
        default=None,
        description="助手历史思考内容；preserve_thinking=True 时保留，False 时由官方模板裁剪旧思考。",
    )
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="助手工具调用记录（OpenAI tool_calls 格式）",
    )
    tool_call_id: Optional[str] = Field(
        default=None,
        description="tool 角色消息对应的调用 ID",
    )
    name: Optional[str] = Field(
        default=None,
        max_length=128,
        description="可选函数/角色名",
    )


class QwenChatRequest(BaseModel):
    model: str = Field(
        default="qwen3.8-27b",
        max_length=128,
        description="模型标识（默认 qwen3.8-27b 或 Qwen/Qwen3.8-27B）",
    )
    messages: List[QwenChatMessage] = Field(
        default_factory=list,
        max_length=200,
        description="多轮对话消息列表；若为空则使用顶层 prompt 字段构造单轮对话",
    )
    prompt: str = Field(
        default="",
        max_length=200000,
        description="单轮快捷提问文本（当 messages 为空时生效）",
    )
    attachments: List[QwenAttachment] = Field(
        default_factory=list,
        max_length=12,
        description="单轮快捷提问的多模态附件（当 messages 为空时生效）",
    )
    system_prompt: str = Field(
        default="",
        max_length=65536,
        description="系统提示词（若 messages 首条未含 system 消息则自动注入）",
    )

    # Reasoning / Thinking controls
    enable_thinking: bool = Field(
        default=True,
        description="是否开启 Qwen3.8 深度思考链（chat_template_kwargs.enable_thinking）",
    )
    reasoning_effort: ReasoningEffort = Field(
        default="xhigh",
        description="官方思考深度档位：low / medium / xhigh（默认 xhigh；开启深度思考时生效）",
    )
    preserve_thinking: bool = Field(
        default=True,
        description="保留历史助手思考内容，沿用 Qwen3.8 官方默认；关闭后由模板只保留最近用户问题后的思考。",
    )

    # Core vLLM & OpenAI sampling hyperparameters
    max_tokens: int = Field(
        default=8192,
        ge=1,
        le=131072,
        description="单次回复最大生成 Token 数（上下文总长最高 262144）",
    )
    temperature: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="采样温度（Qwen3.8 思考模式官方推荐 1.0，非思考模式推荐 0.7；0 为贪婪解码）",
    )
    top_p: float = Field(
        default=0.95,
        ge=0.01,
        le=1.0,
        description="核采样概率阈值 Top-P（思考模式推荐 0.95，非思考模式推荐 0.80）",
    )
    top_k: int = Field(
        default=20,
        ge=-1,
        le=500,
        description="Top-K 候选词截断（推荐 20；设为 -1 表示不限制）",
    )
    min_p: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="最小相对概率阈值 Min-P（0.0 表示关闭）",
    )
    presence_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="存在惩罚 Presence Penalty（抑制重复话题，范围 -2.0 ~ 2.0）",
    )
    frequency_penalty: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="频率惩罚 Frequency Penalty（抑制高频字词重复，范围 -2.0 ~ 2.0）",
    )
    repetition_penalty: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="vLLM 重复惩罚系数 Repetition Penalty（1.0 为不惩罚）",
    )
    seed: Optional[int] = Field(
        default=None,
        ge=0,
        le=9007199254740991,
        description="固定随机种子（None 表示每次随机采样）",
    )
    stop: List[str] = Field(
        default_factory=list,
        max_length=8,
        description="自定义停止词列表（最多 8 个）",
    )

    # Structured output & Function Calling
    response_format: ResponseFormatMode = Field(
        default="text",
        description="输出格式：text（自由文本/Markdown）或 json_object（严格 JSON 对象）",
    )
    tools: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="OpenAI 标准格式的函数工具列表（启用 qwen3_coder 工具解析）",
    )
    tool_choice: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="工具调用策略：auto / none / required 或指定函数对象",
    )

    @model_validator(mode="after")
    def validate_non_empty_conversation(self) -> "QwenChatRequest":
        if not self.messages:
            if not self.prompt.strip() and not self.attachments:
                raise ValueError("messages 与 prompt 不能同时为空，请输入提问内容或上传多模态文件。")
        else:
            has_user_or_tool = any(m.role in ("user", "tool") for m in self.messages)
            if not has_user_or_tool:
                raise ValueError("对话消息列表中至少需要包含一条 user 或 tool 消息。")
        cleaned_stops = [s for s in (s.strip() for s in self.stop) if s]
        self.stop = cleaned_stops[:8]
        return self

    def effective_messages(self) -> List[QwenChatMessage]:
        if self.messages:
            msgs = list(self.messages)
        else:
            msgs = [
                QwenChatMessage(
                    role="user",
                    content=self.prompt,
                    attachments=list(self.attachments),
                )
            ]
        sys_text = self.system_prompt.strip()
        if sys_text and (not msgs or msgs[0].role != "system"):
            msgs.insert(0, QwenChatMessage(role="system", content=sys_text))
        return msgs
