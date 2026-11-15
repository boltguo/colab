"""Pydantic request & response schemas for IndexTTS 2.5 (full model control)."""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

EMO_ORDER = [
    "happy",
    "angry",
    "sad",
    "afraid",
    "disgusted",
    "melancholic",
    "surprised",
    "calm",
]

# Official IndexTTS 2.5 perceptual emotion bias weights from infer_v2_5.py
OFFICIAL_EMO_BIAS = [0.9375, 0.875, 1.0, 1.0, 0.9375, 0.9375, 0.6875, 0.5625]

LanguageCode = Literal["zh", "en", "ja", "es", "ar"]
EmotionMode = Literal["clone", "vector", "reference", "text"]
OutputFormat = Literal["mp3", "wav", "flac"]


class EmotionVector(BaseModel):
    happy: float = Field(default=0.0, ge=0.0, le=1.0, description="高兴 Happy (0~1)")
    angry: float = Field(default=0.0, ge=0.0, le=1.0, description="愤怒 Angry (0~1)")
    sad: float = Field(default=0.0, ge=0.0, le=1.0, description="悲伤 Sad (0~1)")
    afraid: float = Field(default=0.0, ge=0.0, le=1.0, description="恐惧 Afraid (0~1)")
    disgusted: float = Field(default=0.0, ge=0.0, le=1.0, description="反感 Disgusted (0~1)")
    melancholic: float = Field(default=0.0, ge=0.0, le=1.0, description="低落 Melancholic (0~1)")
    surprised: float = Field(default=0.0, ge=0.0, le=1.0, description="惊讶 Surprised (0~1)")
    calm: float = Field(default=0.0, ge=0.0, le=1.0, description="平静/自然 Calm (0~1)")

    def to_ordered_list(self) -> List[float]:
        return [round(float(getattr(self, name)), 4) for name in EMO_ORDER]


def compute_effective_emo_vector(
    raw_vec: List[float],
    apply_bias: bool = True,
    cap_sum: bool = True,
) -> List[float]:
    vec = [max(0.0, float(v)) for v in raw_vec[:8]]
    if len(vec) < 8:
        vec.extend([0.0] * (8 - len(vec)))
    if apply_bias:
        vec = [v * b for v, b in zip(vec, OFFICIAL_EMO_BIAS)]
    if cap_sum:
        total = sum(vec)
        if total > 0.8:
            scale = 0.8 / total
            vec = [v * scale for v in vec]
    return [round(v, 4) for v in vec]


class IndexTTSGenerateRequest(BaseModel):
    # 1. Core Script & Voice Inputs
    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description=(
            "待合成文本。支持自定义读音标注 <文字|读音>："
            "中文多音字如 银<行|HANG2>；英文音标如 <going|G OW1 . IH0 NG>；日文假名如 <明日|あした>"
        ),
        examples=["你好，欢迎使用 IndexTTS 2.5 现代语音合成工作台！"],
    )
    speaker_audio: str = Field(
        default="preset:ref_audio",
        description="说话人参考音频：传 POST /api/v1/files 返回的 file_id，或内置示例 'preset:ref_audio'",
    )
    language: LanguageCode = Field(
        default="zh",
        description="目标语种（zh / en / ja / es / ar），支持跨语种零样本音色克隆",
    )
    duration_factor: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="语速与时长倍率：1.0 标准语速，<1.0 加快语速，>1.0 放慢语速",
    )
    max_ref_seconds: float = Field(
        default=15.0,
        ge=3.0,
        le=30.0,
        description="说话人与情感参考音频最大截取时长（秒，官方默认 15s）",
    )

    # 2. Emotion & Expressiveness Controls
    emotion_mode: EmotionMode = Field(
        default="clone",
        description=(
            "情感控制模式：clone(继承音色情绪) | vector(8维情绪向量) | "
            "reference(第二段情绪参考音频) | text(QwenEmotion 自然语言语义情绪)"
        ),
    )
    emo_alpha: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="情感融合强度权重（0.0~1.0）：控制情绪对原音色语气的覆盖比例",
    )
    emotion_vector: Optional[EmotionVector] = Field(
        default=None,
        description="8 维情绪向量（当 emotion_mode='vector' 时生效）",
    )
    normalize_emo_vector: bool = Field(
        default=True,
        description="启用官方情绪总和防破音保护（自动约束向量总和 <= 0.8，保护说话人音色不失真）",
    )
    apply_emo_bias: bool = Field(
        default=True,
        description="启用官方 8 维听感偏置权重校正（抑制过激情绪伪影）",
    )
    emotion_audio: Optional[str] = Field(
        default=None,
        description="第二段情感参考音频 file_id 或 'preset:ref_audio'（当 emotion_mode='reference' 时生效）",
    )
    emotion_text: Optional[str] = Field(
        default=None,
        max_length=500,
        description="自然语言情感描述词；当 auto_emotion_from_text=True 或留空时自动从合成台词推理情绪",
    )
    auto_emotion_from_text: bool = Field(
        default=False,
        description="在 text 情感模式下，直接根据待合成台词文本自动分析情绪向量",
    )
    use_random: bool = Field(
        default=False,
        description="启用情感特征矩阵随机采样（增加同一情绪下的语气多样性，否则按音色余弦相似度匹配最优特征）",
    )

    # 3. Text Normalization & Segmentation Controls
    text_normalization: bool = Field(
        default=True,
        description="启用文本正则化（自动转换数字、日期、货币与符号读法；若已手写纯文字剧本可关闭）",
    )
    max_text_tokens_per_segment: int = Field(
        default=120,
        ge=20,
        le=200,
        description="长文本自动分句单段最大 Token 数（官方建议 80~200，越小切分越细，越大连贯性越强）",
    )
    interval_silence_ms: int = Field(
        default=200,
        ge=0,
        le=2000,
        description="多段分句合成时的句间停顿静音时长（毫秒，默认 200ms）",
    )

    # 4. GPT2 Autoregressive & S2Mel CFM Flow-Matching Controls
    seed: int = Field(
        default=0,
        ge=0,
        le=2147483647,
        description="随机种子：0 表示随机生成并返回实际种子，>0 锁定复现",
    )
    do_sample: bool = Field(default=True, description="GPT2 是否开启随机核采样（关闭则退化为确定性束搜索）")
    temperature: float = Field(default=0.8, ge=0.1, le=2.0, description="GPT2 采样温度（越高抑扬顿挫越丰富，越低越平稳）")
    top_p: float = Field(default=0.8, ge=0.0, le=1.0, description="Top-P 核采样累积概率阈值")
    top_k: int = Field(default=30, ge=0, le=100, description="Top-K 候选词数（0 表示不限制 Top-K）")
    num_beams: int = Field(default=3, ge=1, le=10, description="Beam Search 束搜索宽度")
    repetition_penalty: float = Field(default=10.0, ge=0.1, le=20.0, description="重复 Token 惩罚系数（防止卡壳或拖音）")
    length_penalty: float = Field(default=0.0, ge=-2.0, le=2.0, description="序列长度惩罚系数")
    max_mel_tokens: int = Field(default=1500, ge=50, le=1815, description="单分句最大生成 Mel Token 数量上限")
    diffusion_steps: int = Field(
        default=25,
        ge=10,
        le=50,
        description="S2Mel 流匹配（CFM）扩散步数（默认 25；步数越高音质细节越细腻，步数越低速度越快）",
    )
    inference_cfg_rate: float = Field(
        default=0.7,
        ge=0.0,
        le=1.5,
        description="S2Mel 流匹配音色引导强度 CFG Rate（默认 0.7；调高增强目标音色相似度，调低更松弛自然）",
    )

    # 5. Audio Mastering, Format & Engine Acceleration
    output_format: OutputFormat = Field(
        default="mp3",
        description="输出音频格式：mp3 (高音质 V0) | wav (16-bit PCM 无损) | flac (无损压缩)",
    )
    loudness_norm: bool = Field(
        default=False,
        description="启用广播级响度标准化（EBU R128 -16 LUFS，适合播客与视频配音后期直出）",
    )
    trim_silence: bool = Field(
        default=False,
        description="自动修剪合成音频首尾多余静音留白",
    )
    tail_fade_ms: int = Field(
        default=0,
        ge=0,
        le=500,
        description="额外句尾平滑淡出时长（毫秒，0 表示仅使用模型内置防截断保护）",
    )
    use_bf16: bool = Field(default=True, description="在支持 CUDA 的显卡上启用 BF16 混合精度推理")
    use_cuda_kernel: bool = Field(default=False, description="尝试启用 BigVGAN 自定义融合激活 CUDA 算子")
    use_torch_compile: bool = Field(default=False, description="启用 s2mel torch.compile 图编译加速（首次编译较慢，后续推理更快）")
    auto_free_memory: bool = Field(
        default=False,
        description="本次生成完成后立即卸载模型清空 GPU 显存（连续调参建议关闭）",
    )

    @model_validator(mode="after")
    def check_mode_fields(self) -> "IndexTTSGenerateRequest":
        cleaned = self.text.strip()
        if not cleaned:
            raise ValueError("合成文本 text 不能为空。")
        self.text = cleaned

        if self.emotion_mode == "reference" and not (self.emotion_audio or "").strip():
            raise ValueError("当情感模式为 'reference'（情感参考音频）时，必须提供 emotion_audio。")
        if self.emotion_mode == "vector" and self.emotion_vector is None:
            self.emotion_vector = EmotionVector(calm=1.0)
        return self
