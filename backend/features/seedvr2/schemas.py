"""Pydantic v2 request/response schemas & target sizing helpers for SeedVR2 Super-Resolution."""
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

SeedVR2Mode = Literal["video", "image"]
SeedVR2ModelVariant = Literal["7b_sharp", "3b_fast"]
SizingMode = Literal["multiplier", "shorter_edge", "longer_edge", "dimensions"]
UpscaleInterpolation = Literal["lanczos", "bicubic", "bilinear", "area", "nearest-exact"]
CropMode = Literal["disabled", "center"]
ColorCorrectionMethod = Literal["lab", "wavelet", "adain", "none"]
ChunkingMode = Literal["auto", "manual"]
SamplerName = Literal["euler", "euler_ancestral", "heun", "dpmpp_2m", "uni_pc"]
SchedulerName = Literal["simple", "normal", "sgm_uniform", "beta", "karras"]
UnetWeightDtype = Literal["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"]

ImageOutputFormat = Literal["png", "webp", "jpeg"]
VideoOutputFormat = Literal["mp4", "webm", "mkv"]
VideoCodecChoice = Literal["auto", "h264", "av1"]
ColorSpaceChoice = Literal["match_input", "sRGB", "HDR", "HDR PQ"]
BitDepthChoice = Literal["match_input", "auto", "8", "10"]


def align_even(value: int, minimum: int = 16) -> int:
    """Align pixel dimensions to even integers (matching SeedVR2PostProcessing output alignment)."""
    clamped = max(minimum, int(value))
    even = clamped - (clamped % 2)
    return max(minimum, even)


def align_chunk_frames(frames: int) -> int:
    """Snap manual temporal chunk pixel-frame count to 4n + 1 (1, 5, 9, 13, 17, 21, ...)."""
    if frames <= 1:
        return 1
    k = max(1, (frames + 1) // 4)
    return min(16381, 4 * k + 1)


def compute_target_dimensions(
    src_w: int,
    src_h: int,
    *,
    sizing_mode: SizingMode,
    scale_factor: float = 2.0,
    target_shorter_edge: int = 1440,
    target_longer_edge: int = 3840,
    target_width: int = 2560,
    target_height: int = 1440,
) -> Tuple[int, int]:
    """Compute exact post-processed output (width, height) given source media dimensions."""
    sw = max(2, int(src_w))
    sh = max(2, int(src_h))

    if sizing_mode == "multiplier":
        w = round(sw * float(scale_factor))
        h = round(sh * float(scale_factor))
    elif sizing_mode == "shorter_edge":
        short_target = max(64, int(target_shorter_edge))
        if sh < sw:
            h = short_target
            w = round((sw / sh) * short_target)
        elif sw < sh:
            w = short_target
            h = round((sh / sw) * short_target)
        else:
            w = short_target
            h = short_target
    elif sizing_mode == "longer_edge":
        long_target = max(64, int(target_longer_edge))
        if sh > sw:
            h = long_target
            w = round((sw / sh) * long_target)
        elif sw > sh:
            w = long_target
            h = round((sh / sw) * long_target)
        else:
            w = long_target
            h = long_target
    else:
        tw = int(target_width)
        th = int(target_height)
        if tw <= 0 and th <= 0:
            w, h = sw, sh
        elif tw <= 0:
            h = th
            w = max(2, round(sw * (th / sh)))
        elif th <= 0:
            w = tw
            h = max(2, round(sh * (tw / sw)))
        else:
            w, h = tw, th

    return align_even(w), align_even(h)


class SeedVR2GenerateRequest(BaseModel):
    mode: SeedVR2Mode = Field(
        default="video",
        description="超分模态：video（视频画质修复与超分，自动保留原声与帧率）| image（单图 4K 细节超分修复）",
    )
    input_file: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="待超分的源视频或源图片 file_id（由 POST /api/v1/files 返回，或以 output:<filename> 复用本会话输出）",
    )
    model_variant: SeedVR2ModelVariant = Field(
        default="7b_sharp",
        description="SeedVR2 模型规格：7b_sharp（15.35GB 旗舰细节锐化版）| 3b_fast（6.32GB 长视频高吞吐轻量版）",
    )

    # Target Sizing & Interpolation
    sizing_mode: SizingMode = Field(
        default="multiplier",
        description="输出尺寸计算方式：multiplier（按放大倍数）| shorter_edge（固定短边档位如 1080P/2K/4K）| longer_edge（固定长边）| dimensions（指定精确宽高）",
    )
    scale_factor: float = Field(
        default=2.0,
        ge=1.0,
        le=8.0,
        description="放大倍数（sizing_mode='multiplier' 时生效，视频推荐 2.0x，图片推荐 4.0x 真 4K）",
    )
    target_shorter_edge: int = Field(
        default=1440,
        ge=128,
        le=8192,
        description="目标短边像素（sizing_mode='shorter_edge' 时生效，如 1080=1080P、1440=2K、2160=4K）",
    )
    target_longer_edge: int = Field(
        default=3840,
        ge=128,
        le=8192,
        description="目标长边像素（sizing_mode='longer_edge' 时生效，如 1920、2560、3840）",
    )
    target_width: int = Field(
        default=2560,
        ge=0,
        le=8192,
        description="自定义目标宽度（sizing_mode='dimensions' 时生效，设为 0 则按高度等比换算）",
    )
    target_height: int = Field(
        default=1440,
        ge=0,
        le=8192,
        description="自定义目标高度（sizing_mode='dimensions' 时生效，设为 0 则按宽度等比换算）",
    )
    crop_mode: CropMode = Field(
        default="center",
        description="自定义宽高与原片比例不一致时的处理方式：center（居中裁切保持比例）| disabled（拉伸填充）",
    )
    upscale_interpolation: UpscaleInterpolation = Field(
        default="lanczos",
        description="预处理插值核：lanczos（推荐，高频保真）| bicubic | bilinear | area | nearest-exact（像素画专用）",
    )

    # Color Correction & Temporal Chunking
    color_correction: ColorCorrectionMethod = Field(
        default="lab",
        description="色彩对齐校正算法：lab（CIELAB 色彩空间精准对齐，最忠实还原原片色调）| wavelet（小波低频追色保留高频纹理）| adain（通道均值方差对齐）| none（不追色仅几何对齐）",
    )
    split_latent: bool = Field(
        default=False,
        description="长视频时间分块显存优化（Split Latent，开启后将长视频切分为时间块逐块采样并采用 Hann 窗平滑融合，仅视频模式生效）",
    )
    chunking_mode: ChunkingMode = Field(
        default="auto",
        description="时间分块策略：auto（根据当前空闲 GPU 显存自动计算最大分块帧数）| manual（手动指定每块像素帧数）",
    )
    frames_per_chunk: int = Field(
        default=21,
        ge=5,
        le=257,
        description="手动每块像素帧数（自动对齐至 4n + 1，如 9、13、17、21、25、33、49）",
    )
    temporal_overlap: int = Field(
        default=2,
        ge=0,
        le=32,
        description="相邻时间块重叠潜空间帧数（>0 时在分块边界自动执行 Hann 窗交叉淡入淡出，消除分块接缝闪烁）",
    )

    # Video Trim & Audio Preservation
    trim_video: bool = Field(
        default=False,
        description="是否先截取原视频指定片段进行超分测试（仅视频模式生效）",
    )
    start_time: float = Field(
        default=0.0,
        ge=0.0,
        le=7200.0,
        description="视频截取起始时间（秒，trim_video=True 时生效）",
    )
    duration: float = Field(
        default=0.0,
        ge=0.0,
        le=7200.0,
        description="视频截取时长（秒，0 表示从起始时间截取至片尾，trim_video=True 时生效）",
    )
    keep_audio: bool = Field(
        default=True,
        description="视频超分后是否无损保留原视频音轨（仅视频模式生效）",
    )
    fps_override: float = Field(
        default=0.0,
        ge=0.0,
        le=120.0,
        description="播放帧率（0 继承原速；1~120 改变现有帧的播放速度与时长，不进行补帧。变速时需关闭 keep_audio）",
    )

    # Diffusion Sampling Hyperparameters
    steps: int = Field(
        default=1,
        ge=1,
        le=20,
        description="扩散修复步数（SeedVR2 原生为 1 步对抗蒸馏极速修复，默认 1 步即可达到最佳锐度）",
    )
    cfg: float = Field(
        default=1.0,
        ge=1.0,
        le=8.0,
        description="CFG 条件引导强度（SeedVR2 原生推荐 1.0）",
    )
    denoise: float = Field(
        default=1.0,
        ge=0.05,
        le=1.0,
        description="重绘去噪幅度（默认 1.0 全量细节重绘）",
    )
    sampler_name: SamplerName = Field(
        default="euler",
        description="采样求解器（默认 euler）",
    )
    scheduler: SchedulerName = Field(
        default="simple",
        description="噪声调度器（默认 simple）",
    )
    seed: int = Field(
        default=0,
        ge=0,
        le=2147483647,
        description="随机种子（0 表示每次自动随机生成）",
    )

    # Low-Level Engine / Tiled VAE / Output Encoding
    unet_weight_dtype: UnetWeightDtype = Field(
        default="default",
        description="主模型加载精度：default（原生 FP16 全精度）| fp8_e4m3fn（40GB 显卡跑超高分辨率时省显存）",
    )
    vae_tile_size: int = Field(
        default=512,
        ge=256,
        le=2048,
        description="Tiled VAE 空间分块边长（像素，默认 512，防止 4K 编解码爆显存）",
    )
    vae_tile_overlap: int = Field(
        default=128,
        ge=32,
        le=512,
        description="Tiled VAE 空间分块重叠宽度（像素，默认 128）",
    )
    vae_temporal_size: int = Field(
        default=64,
        ge=8,
        le=4096,
        description="Tiled VAE 时间编码窗口帧数（视频模式默认 64）",
    )
    vae_temporal_overlap: int = Field(
        default=8,
        ge=4,
        le=256,
        description="Tiled VAE 时间解码重叠帧数（默认 8）",
    )

    # Image Mode Output Options
    preserve_alpha: bool = Field(
        default=True,
        description="图片超分时是否保留 PNG/WebP 透明通道（Alpha）",
    )
    image_output_format: ImageOutputFormat = Field(
        default="png",
        description="图片超分导出格式：png（无损真 4K）| webp | jpeg",
    )
    image_quality: int = Field(
        default=94,
        ge=60,
        le=100,
        description="WebP / JPEG 导出质量（60~100）",
    )

    # Video Mode Output Options
    video_output_format: VideoOutputFormat = Field(
        default="mp4",
        description="视频超分封装容器格式：mp4（H.264 通用兼容）| webm | mkv",
    )
    video_codec: VideoCodecChoice = Field(
        default="auto",
        description="视频编码器：auto | h264 | av1（webm 容器仅支持 auto / av1）",
    )
    crf: int = Field(
        default=18,
        ge=0,
        le=51,
        description="重编码画质 CRF（仅手动指定 h264/av1 时生效，数值越小码率越高，18 为视觉无损级）",
    )
    color_space: ColorSpaceChoice = Field(
        default="match_input",
        description="输出视频色彩空间：match_input（自动继承原视频）| sRGB | HDR | HDR PQ",
    )
    bit_depth: BitDepthChoice = Field(
        default="match_input",
        description="输出视频色深：match_input（自动继承原视频）| auto | 8 | 10",
    )
    release_vram_after: bool = Field(
        default=False,
        description="本次超分任务完成后自动从 GPU 卸载模型并回收显存",
    )

    @model_validator(mode="after")
    def _validate_and_normalize(self) -> "SeedVR2GenerateRequest":
        ref = self.input_file.strip()
        if not ref:
            raise ValueError("请先上传待超分的视频或图片文件（input_file 不能为空）。")
        self.input_file = ref

        if self.sizing_mode == "dimensions" and self.target_width <= 0 and self.target_height <= 0:
            raise ValueError("自定义尺寸模式下，目标宽度与高度不能同时为 0。")

        if self.fps_override != 0 and self.fps_override < 1:
            raise ValueError("播放帧率请设为 0（原速）或 1~120 FPS。")
        if self.mode == "video" and self.fps_override > 0 and self.keep_audio:
            raise ValueError("修改播放帧率会改变视频速度；请关闭保留原声，或将播放帧率设为 0。")

        self.frames_per_chunk = align_chunk_frames(self.frames_per_chunk)
        self.vae_tile_size = max(256, (self.vae_tile_size // 64) * 64)
        self.vae_tile_overlap = max(32, min(self.vae_tile_size // 2, (self.vae_tile_overlap // 32) * 32))
        self.vae_temporal_size = max(8, (self.vae_temporal_size // 4) * 4)
        self.vae_temporal_overlap = max(4, min(self.vae_temporal_size // 2, (self.vae_temporal_overlap // 4) * 4))

        if self.video_output_format == "webm" and self.video_codec == "h264":
            self.video_codec = "auto"

        return self


class SeedVR2Result(BaseModel):
    media_type: SeedVR2Mode
    mode: SeedVR2Mode
    model_variant: SeedVR2ModelVariant
    model_label: str
    output_url: str
    video_url: Optional[str] = None
    image_url: Optional[str] = None
    filename: str
    format: str
    size_bytes: int
    input_url: str
    input_width: int
    input_height: int
    input_fps: Optional[float] = None
    input_start_time: float = 0.0
    width: int
    height: int
    effective_scale: float
    duration_sec: Optional[float] = None
    fps: Optional[float] = None
    has_audio: bool = False
    used_seed: int
    steps: int
    cfg: float
    denoise: float
    color_correction: ColorCorrectionMethod
    split_latent: bool
    warnings: List[str] = Field(default_factory=list)
    mock: bool = False
