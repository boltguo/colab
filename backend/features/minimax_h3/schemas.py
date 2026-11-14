"""Full-parameter Pydantic schemas for MiniMax-H3 unified video + audio generation."""
import math
from typing import Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, model_validator

H3Mode = Literal["t2v", "i2v", "fl2v", "r2v"]
H3ResolutionTier = Literal["768p", "540p", "1080p", "custom"]
H3AspectRatio = Literal[
    "match_input",
    "16:9",
    "9:16",
    "1:1",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "21:9",
    "custom",
]
RefImageSizeMode = Literal["match", "max"]
RefConditioningMode = Literal["vae_and_vision", "vision_only"]

SamplerName = Literal[
    "res_multistep",
    "euler",
    "euler_ancestral",
    "heun",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "uni_pc",
    "lms",
]

SchedulerName = Literal[
    "simple",
    "normal",
    "beta",
    "sgm_uniform",
    "karras",
    "exponential",
    "ddim_uniform",
]

VideoOutputFormat = Literal["mp4", "webm", "mkv"]
VideoCodecChoice = Literal["h264", "av1", "auto"]
ColorSpaceChoice = Literal["sRGB", "HDR", "HDR PQ"]
BitDepthChoice = Literal["auto", "8", "10"]
UnetWeightDtype = Literal["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"]
ClipDevice = Literal["default", "cpu"]

ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "1:1": (1, 1),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "21:9": (21, 9),
}

RESOLUTION_MEGAPIXELS: Dict[str, float] = {
    "540p": 0.52,
    "768p": 0.98,
    "1080p": 2.00,
}

NATIVE_FPS = 24


def snap32(val: float, minimum: int = 256, maximum: int = 2560) -> int:
    snapped = int(round(val / 32.0) * 32)
    return max(minimum, min(maximum, snapped))


def align_h3_frames(raw_frames: int) -> int:
    """Align frame count up to MiniMax-H3's native 17k + 5 temporal latent grid (at 24 fps)."""
    n = max(5, min(720, int(raw_frames)))
    rem = n % 17
    if rem != 5:
        n += (5 - rem) % 17
    return n


def duration_to_h3_frames(duration_sec: float) -> int:
    """Convert target duration in seconds (at 24 fps) to the nearest upward 17k + 5 frame count."""
    raw = max(5, int(round(float(duration_sec) * NATIVE_FPS)))
    return align_h3_frames(raw)


def compute_h3_dimensions(tier: str, aspect_ratio: str) -> Tuple[int, int]:
    """Compute 32px-aligned pixel dimensions matching MiniMax-H3's canvas rules."""
    rw, rh = ASPECT_RATIOS.get(aspect_ratio, (16, 9))
    ratio = rw / rh

    if tier == "768p":
        # Exact match to ComfyUI's adapt_canvas (768 short edge, 768*1344=1,032,192 cap, round to 32)
        base_short = 768.0
        max_px = 768.0 * 1344.0
        if ratio >= 1.0:
            nom_w, nom_h = base_short * ratio, base_short
        else:
            nom_w, nom_h = base_short, base_short / ratio
        if nom_w * nom_h > max_px:
            scale = math.sqrt(max_px / (nom_w * nom_h))
            nom_w, nom_h = nom_w * scale, nom_h * scale
        return snap32(nom_w), snap32(nom_h)

    mp = RESOLUTION_MEGAPIXELS.get(tier, 0.98)
    total_px = mp * 1024.0 * 1024.0
    width = snap32(math.sqrt(total_px * ratio))
    height = snap32(math.sqrt(total_px / ratio))
    return width, height


def compute_matched_dimensions(tier: str, ref_w: int, ref_h: int) -> Tuple[int, int]:
    """Compute 32px-aligned dimensions preserving a reference image's natural aspect ratio."""
    ratio = max(0.2, min(5.0, float(ref_w) / max(1.0, float(ref_h))))
    if tier == "768p":
        base_short = 768.0
        max_px = 768.0 * 1344.0
        if ratio >= 1.0:
            nom_w, nom_h = base_short * ratio, base_short
        else:
            nom_w, nom_h = base_short, base_short / ratio
        if nom_w * nom_h > max_px:
            scale = math.sqrt(max_px / (nom_w * nom_h))
            nom_w, nom_h = nom_w * scale, nom_h * scale
        return snap32(nom_w), snap32(nom_h)

    mp = RESOLUTION_MEGAPIXELS.get(tier, 0.98)
    total_px = mp * 1024.0 * 1024.0
    return snap32(math.sqrt(total_px * ratio)), snap32(math.sqrt(total_px / ratio))


class ReferenceVideoSlot(BaseModel):
    file_id: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="已上传或历史生成的参考视频引用（file_id 或 output:<filename>，建议 2~15 秒）。",
    )
    use_video_audio: bool = Field(
        default=True,
        description="是否同时提取该参考视频的原声轨注入模型（开启后对应独立的 <Audio N> 标签，排在 <Video K> 之前）。",
    )


class LoraSlot(BaseModel):
    lora: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="LoRA 标识：支持已安装的 .safetensors 文件名、内置精选 ID、Hugging Face 仓库或 HTTPS 直链。",
    )
    strength_model: float = Field(
        default=1.0,
        ge=-2.0,
        le=2.0,
        description="扩散主干 (DiT) LoRA 权重强度。",
    )
    apply_to_clip: bool = Field(
        default=False,
        description="是否同时作用于 Qwen3-VL 文本编码器（常规 H3 LoRA 建议保持关闭）。",
    )
    strength_clip: float = Field(
        default=1.0,
        ge=-2.0,
        le=2.0,
        description="当 apply_to_clip=True 时作用于 CLIP 的强度。",
    )
    enabled: bool = Field(
        default=True,
        description="是否启用当前 LoRA 槽位。",
    )
    token: Optional[str] = Field(
        default=None,
        max_length=512,
        description="可选：受限 Hugging Face 仓库或 Civitai 下载所需的访问 Token。",
    )


class MiniMaxH3GenerateRequest(BaseModel):
    # 1. Unified Generation Mode & Prompt
    mode: H3Mode = Field(
        default="t2v",
        description=(
            "生成模式：t2v（文生音画视频）、fl2v / i2v（首帧或首尾帧图生视频）、"
            "r2v（多模态参考生视频，支持 <Picture N> / <Video K> / <Audio J> 组合）。"
        ),
    )
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description=(
            "场景、镜头运动、人物动作与声音（对白/环境音/配乐）描述。"
            "在 r2v 模式下可用 <Picture 1>、<Video 1>、<Audio 1> 指代对应参考素材。"
        ),
    )
    negative_prompt: str = Field(
        default="",
        max_length=4000,
        description="可选反向提示词（仅在 cfg > 1.0 时激活反向引导）。",
    )

    # 2. Keyframe Inputs (for fl2v / i2v mode) & Optional Frame/Audio Guide Anchor
    first_frame: Optional[str] = Field(
        default=None,
        max_length=256,
        description="首帧图片引用（fl2v / i2v 模式的起始画面，传 POST /api/v1/files 返回的 file_id）。",
    )
    last_frame: Optional[str] = Field(
        default=None,
        max_length=256,
        description="可选尾帧图片引用（fl2v 模式的结束画面；留空则为单首帧图生视频）。",
    )
    guide_audio: Optional[str] = Field(
        default=None,
        max_length=256,
        description="可选锚定音轨引用（t2v / fl2v 模式下通过 MiniMaxH3AddGuide 在指定帧锚定外部配音/音乐驱动画面口型与节奏）。",
    )
    guide_image: Optional[str] = Field(
        default=None,
        max_length=256,
        description="可选中间关键帧图片引用（通过 MiniMaxH3AddGuide 锚定在 guide_frame_idx 帧）。",
    )
    guide_frame_idx: int = Field(
        default=0,
        ge=-9999,
        le=9999,
        description="MiniMaxH3AddGuide 锚定起始帧索引（0 表示从第 1 帧开始，负数表示从末尾倒数）。",
    )

    # 3. Multimodal Reference Inputs (for r2v mode)
    ref_images: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="r2v 模式参考图片列表（最多 5 张，依次对应 <Picture 1>..<Picture 5>）。",
    )
    ref_videos: List[ReferenceVideoSlot] = Field(
        default_factory=list,
        max_length=2,
        description="r2v 模式可选参考视频列表（最多 2 段，依次对应 <Video 1>..<Video 2>）。",
    )
    ref_audios: List[str] = Field(
        default_factory=list,
        max_length=2,
        description="r2v 模式可选独立参考音频列表（最多 2 段，排在参考视频原声之后依次编号为 <Audio J>）。",
    )
    ref_image_size: RefImageSizeMode = Field(
        default="match",
        description="r2v 参考图编码尺寸策略：match（匹配输出像素面积，推理快）或 max（2048 短边高精度保身份细节）。",
    )
    ref_conditioning_mode: RefConditioningMode = Field(
        default="vae_and_vision",
        description="r2v 参考注入深度：vae_and_vision（视觉编码器 + VAE 潜空间双重注入）或 vision_only（仅语义参考）。",
    )

    # 4. Independent Resolution Tier, Aspect Ratio, Dimensions & Duration / FPS
    resolution_tier: H3ResolutionTier = Field(
        default="768p",
        description="独立分辨率档位：768p（0.98 MP 原生甜点，如 1344×768）、540p（0.52 MP 快速预览）、1080p（2.0 MP 高清）或 custom。",
    )
    aspect_ratio: H3AspectRatio = Field(
        default="16:9",
        description="独立画面比例：match_input（跟随首帧/主参考图比例）、16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 3:2 / 2:3 / 21:9 或 custom。",
    )
    width: int = Field(
        default=1344,
        ge=256,
        le=2560,
        description="输出画面宽度（自动对齐 32 的倍数；当 aspect_ratio='custom' 时直接采用此值）。",
    )
    height: int = Field(
        default=768,
        ge=256,
        le=2560,
        description="输出画面高度（自动对齐 32 的倍数；当 aspect_ratio='custom' 时直接采用此值）。",
    )
    duration_sec: float = Field(
        default=5.0,
        ge=1.0,
        le=15.0,
        description="目标视频时长（秒，模型原生 24fps 下自动对齐至 17k+5 帧网格，默认 5 秒 = 124 帧 ≈ 5.17 秒）。",
    )
    frame_count: Optional[int] = Field(
        default=None,
        ge=5,
        le=362,
        description="可选精确帧数覆写（若传入则优先于 duration_sec，同样自动对齐至 17k+5 网格，训练甜点范围 124~362 帧）。",
    )
    fps: float = Field(
        default=24.0,
        ge=12.0,
        le=60.0,
        description="封装导出视频帧率（MiniMax-H3 原生训练帧率为 24 fps）。",
    )

    # 5. Official Turbo Acceleration + Dynamic Custom LoRA Stack
    turbo_enabled: bool = Field(
        default=False,
        description=(
            "是否启用官方 Turbo 极速加速 LoRA（t2v/fl2v 自动挂载 8 步 Turbo，r2v 自动挂载 4 步 Turbo；"
            "关闭则为 20 步全质量基础模式）。"
        ),
    )
    turbo_strength: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="官方 Turbo LoRA 强度（默认 1.0）。",
    )
    loras: List[LoraSlot] = Field(
        default_factory=list,
        max_length=4,
        description="附加自定义 LoRA 叠加栈（最多 4 层，支持 Hugging Face / 直链在线热挂载）。",
    )

    # 6. Sampling & Guidance Hyperparameters
    steps: int = Field(
        default=20,
        ge=1,
        le=60,
        description="采样步数（基础模式推荐 20 步；t2v/fl2v Turbo 推荐 8 步；r2v Turbo 推荐 4 步）。",
    )
    cfg: float = Field(
        default=1.0,
        ge=1.0,
        le=10.0,
        description="引导系数 (CFG Scale)。默认 1.0（单路高速引导）；大于 1.0 时启用双路 CFGGuider 与反向提示词。",
    )
    sampler_name: SamplerName = Field(
        default="res_multistep",
        description="采样求解器（MiniMax-H3 官方工作流标准为 res_multistep）。",
    )
    scheduler: SchedulerName = Field(
        default="simple",
        description="噪声调度策略（官方标准为 simple）。",
    )
    denoise: float = Field(
        default=1.0,
        ge=0.05,
        le=1.0,
        description="去噪幅度（常规生成保持 1.0）。",
    )
    seed: int = Field(
        default=0,
        ge=0,
        description="随机种子（0 表示自动随机；正整数锁定复现）。",
    )

    # 7. AV Flow Shift, Audio Track & Video Mastering / Engine Flags
    enable_sigma_shift: bool = Field(
        default=False,
        description="是否手动覆写音视频流时间步偏移 (MiniMaxH3SigmaShift)。默认关闭使用模型内置调度。",
    )
    shift_video: float = Field(
        default=12.0,
        ge=0.1,
        le=50.0,
        description="当 enable_sigma_shift=True 时的视频流 Sigma Shift（官方基准 12.0）。",
    )
    shift_audio: float = Field(
        default=3.0,
        ge=0.1,
        le=50.0,
        description="当 enable_sigma_shift=True 时的音频流 Sigma Shift（官方基准 3.0）。",
    )
    soundtrack_enabled: bool = Field(
        default=True,
        description="是否解码并合成同步立体声音轨（VAEDecodeAudio -> CreateVideo）。关闭则仅输出无声画面。",
    )
    output_format: VideoOutputFormat = Field(
        default="mp4",
        description="输出视频封装容器：mp4（默认兼容性最佳）、webm、mkv。",
    )
    video_codec: VideoCodecChoice = Field(
        default="h264",
        description="视频编码器：h264（推荐）、av1 或 auto。",
    )
    crf: int = Field(
        default=18,
        ge=0,
        le=51,
        description="视频重编码画质 CRF（数值越小画质越高、体积越大；H.264 推荐 16~20，默认 18）。",
    )
    color_space: ColorSpaceChoice = Field(
        default="sRGB",
        description="色彩空间元数据：sRGB（默认 8-bit 标准动态范围）、HDR (HLG) 或 HDR PQ。",
    )
    bit_depth: BitDepthChoice = Field(
        default="auto",
        description="像素位深：auto（sRGB 自动 8-bit，HDR 自动 10-bit）、8 或 10。",
    )
    unet_weight_dtype: UnetWeightDtype = Field(
        default="default",
        description="主模型加载精度覆写（H3 已采用 INT8 ConvRot 量化，建议保持 default）。",
    )
    clip_device: ClipDevice = Field(
        default="default",
        description="Qwen3-VL-32B 编码器运行设备：default（GPU 自动卸载）或 cpu。",
    )
    release_vram_after: bool = Field(
        default=False,
        description="本次生成完成后是否主动通知推理引擎卸载模型并释放显存。",
    )

    def effective_ref_images(self) -> List[str]:
        return [r.strip() for r in self.ref_images if r and r.strip()]

    def effective_ref_videos(self) -> List[ReferenceVideoSlot]:
        return [
            ReferenceVideoSlot(file_id=v.file_id.strip(), use_video_audio=v.use_video_audio)
            for v in self.ref_videos
            if v.file_id and v.file_id.strip()
        ]

    def effective_ref_audios(self) -> List[str]:
        return [a.strip() for a in self.ref_audios if a and a.strip()]

    def resolved_frame_count(self) -> int:
        if self.frame_count is not None:
            return align_h3_frames(self.frame_count)
        return duration_to_h3_frames(self.duration_sec)

    @model_validator(mode="after")
    def validate_inputs_by_mode(self) -> "MiniMaxH3GenerateRequest":
        first = (self.first_frame or "").strip() or None
        last = (self.last_frame or "").strip() or None
        self.first_frame = first
        self.last_frame = last
        self.guide_audio = (self.guide_audio or "").strip() or None
        self.guide_image = (self.guide_image or "").strip() or None

        if self.mode in ("fl2v", "i2v"):
            if not first and not last:
                raise ValueError("首尾帧图生视频模式请至少上传首帧图片（或尾帧图片）。")
        elif self.mode == "r2v":
            if (
                not self.effective_ref_images()
                and not self.effective_ref_videos()
                and not self.effective_ref_audios()
            ):
                raise ValueError("多模态参考生视频模式请至少添加 1 项参考素材（参考图 / 参考视频 / 参考音频）。")
        elif self.mode == "t2v":
            if self.aspect_ratio == "match_input":
                self.aspect_ratio = "16:9"

        if self.output_format == "webm" and self.video_codec == "h264":
            # WebM container only supports AV1/VP9 in SaveVideo; coerce cleanly to av1
            self.video_codec = "av1"

        self.width = snap32(self.width)
        self.height = snap32(self.height)
        return self


class MiniMaxH3Result(BaseModel):
    video_url: str
    filename: str
    format: VideoOutputFormat
    video_codec: str
    width: int
    height: int
    frame_count: int
    duration_sec: float
    fps: float
    has_audio: bool
    size_bytes: int
    mode: H3Mode
    model_variant: str
    turbo_enabled: bool
    used_seed: int
    steps: int
    cfg: float
    sampler_name: str
    scheduler: str
    active_loras: List[Dict[str, object]] = Field(default_factory=list)
    reference_summary: Dict[str, object] = Field(default_factory=dict)
    primary_ref_image_url: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    mock: bool = False
