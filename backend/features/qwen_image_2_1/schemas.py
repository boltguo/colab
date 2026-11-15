"""Full-parameter Pydantic schemas for Qwen-Image 2.1 generation (T2I + Img2Img) and LoRA stacking."""
import math
from typing import Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, model_validator

WorkflowMode = Literal["t2i", "img2img", "edit_single", "edit_dual", "edit_multi"]
ResolutionTier = Literal["2K", "1K", "original", "custom"]
StandardAspectRatio = Literal["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"]
AspectRatioChoice = Literal[
    "match_input",
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "21:9",
    "custom",
]
ReferenceConditioningMode = Literal["vae_and_vision", "vision_only"]

SamplerName = Literal[
    "euler",
    "euler_ancestral",
    "heun",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "dpmpp_3m_sde",
    "uni_pc",
    "res_multistep",
    "lms",
]

SchedulerName = Literal[
    "simple",
    "normal",
    "karras",
    "exponential",
    "sgm_uniform",
    "beta",
    "ddim_uniform",
]

KvCacheDevice = Literal["smart", "auto", "cpu", "gpu", "off"]
KvCacheDtype = Literal["default", "int8", "int4"]
UnetWeightDtype = Literal["default", "fp8_e4m3fn", "fp8_e4m3fn_fast", "fp8_e5m2"]
ClipDevice = Literal["default", "cpu"]
ImageOutputFormat = Literal["png", "webp", "jpeg"]
MAX_REFERENCE_IMAGES = 10

ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "1:1": (1, 1),
    "16:9": (16, 9),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:4": (3, 4),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "21:9": (21, 9),
}


def snap32(val: float, minimum: int = 256, maximum: int = 4096) -> int:
    snapped = int(round(val / 32.0) * 32)
    return max(minimum, min(maximum, snapped))


def compute_preset_dimensions(tier: str, aspect_ratio: str) -> Tuple[int, int]:
    """Compute 32px-aligned pixel dimensions from resolution tier (1K=1MP, 2K=4MP) + aspect ratio."""
    megapixels = 1.0 if tier == "1K" else 4.0
    rw, rh = ASPECT_RATIOS.get(aspect_ratio, (1, 1))
    total_px = megapixels * 1024.0 * 1024.0
    ratio = rw / rh
    width = snap32(math.sqrt(total_px * ratio))
    height = snap32(math.sqrt(total_px / ratio))
    return width, height


class LoraSlot(BaseModel):
    lora: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description=(
            "LoRA 标识：支持已安装的 .safetensors 文件名、内置目录 ID（如 anime_consistency）、"
            "Hugging Face 仓库（owner/repo 或 owner/repo::file.safetensors）或 HTTPS 直链 URL。"
        ),
    )
    strength_model: float = Field(
        default=0.85,
        ge=-2.0,
        le=2.0,
        description="扩散主干 (UNet) LoRA 权重强度。推荐范围 0.6 ~ 1.0。",
    )
    apply_to_clip: bool = Field(
        default=False,
        description="是否同时作用于文本编码器 (Qwen3-VL)。绝大多数 Qwen-Image 2.1 LoRA 仅训练扩散主干，建议保持关闭。",
    )
    strength_clip: float = Field(
        default=1.0,
        ge=-2.0,
        le=2.0,
        description="当 apply_to_clip=True 时作用于 CLIP 的强度。",
    )
    enabled: bool = Field(
        default=True,
        description="是否启用当前 LoRA 槽位（便于一键静音对比效果）。",
    )
    token: Optional[str] = Field(
        default=None,
        max_length=512,
        description="可选：若 lora 为受限 Hugging Face 仓库或需鉴权的 Civitai 链接，可传入临时访问 Token。",
    )


class QwenImageGenerateRequest(BaseModel):
    # 1. Core Creative & Conditioning Inputs
    mode: WorkflowMode = Field(
        default="t2i",
        description="创作模式：t2i（文生图）或 img2img（图生图 / 图像编辑，官方支持最多 10 张参考图）。",
    )
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description="正向提示词或图像编辑指令。图生图模式下可通过 <image1>、<image2> 等指代对应输入图片。",
    )
    negative_prompt: str = Field(
        default="",
        max_length=4000,
        description="反向提示词（注意：需将 cfg 调高至 > 1.0 才会激活反向条件引导）。",
    )

    # Official multi-reference editing supports up to ten images.
    reference_images: List[str] = Field(
        default_factory=list,
        max_length=MAX_REFERENCE_IMAGES,
        description="按顺序排列的参考图引用列表（最多 10 张；POST /api/v1/files 返回的 file_id 或 output:<filename>），依次对应 <image1>…<image10>。",
    )
    image_1: Optional[str] = Field(default=None, description="主参考图 <image1>（可选快捷字段，等价于 reference_images[0]）。")
    image_2: Optional[str] = Field(default=None, description="可选第二参考图 <image2>（等价于 reference_images[1]）。")
    image_3: Optional[str] = Field(default=None, description="可选第三参考图 <image3>。")
    image_4: Optional[str] = Field(default=None, description="可选第四参考图 <image4>。")

    reference_conditioning_mode: ReferenceConditioningMode = Field(
        default="vae_and_vision",
        description=(
            "参考图注入机制：vae_and_vision（同时注入 Qwen3-VL 视觉语义与 VAE 潜空间特征，适合保主体精修与双图融合）；"
            "vision_only（仅注入 Qwen3-VL 视觉理解，适合提取参考图风格/元素并自由构图）。"
        ),
    )

    # 2. Independent Resolution, Aspect Ratio & Pixel Dimensions
    resolution_tier: ResolutionTier = Field(
        default="2K",
        description="独立分辨率档位：1K（~100 万像素，1024 级）、2K（~400 万像素，2048 级）、original（图生图保持参考图原始分辨率）。",
    )
    aspect_ratio: AspectRatioChoice = Field(
        default="1:1",
        description="独立宽高比：match_input（图生图跟随主参考图比例）、标准比例（1:1 / 16:9 / 9:16 / 4:3 / 3:4 / 3:2 / 2:3 / 21:9）或 custom（使用自定义 width × height）。",
    )
    width: int = Field(
        default=2048,
        ge=256,
        le=4096,
        description="目标输出像素宽度（自动对齐 32 的整数倍；当 aspect_ratio='custom' 时直接采用此值）。",
    )
    height: int = Field(
        default=2048,
        ge=256,
        le=4096,
        description="目标输出像素高度（自动对齐 32 的整数倍；当 aspect_ratio='custom' 时直接采用此值）。",
    )
    batch_size: int = Field(
        default=1,
        ge=1,
        le=4,
        description="单次并行生成张数（1~4）。",
    )

    # 3. Dynamic Multi-LoRA Stack
    loras: List[LoraSlot] = Field(
        default_factory=list,
        max_length=6,
        description="多 LoRA 叠加栈（最多同时挂载 6 个 .safetensors LoRA，支持在线自动拉取并缓存）。",
    )

    # 4. Diffusion Sampling & Guidance Hyperparameters
    steps: int = Field(
        default=40,
        ge=1,
        le=100,
        description="扩散去噪步数（官方推荐 40 步；快速构思可设为 20~28 步）。",
    )
    cfg: float = Field(
        default=1.0,
        ge=1.0,
        le=15.0,
        description="引导系数 (CFG Scale)。默认 1.0；若填写了反向提示词建议提升至 2.5 ~ 4.5。",
    )
    sampler_name: SamplerName = Field(
        default="euler",
        description="采样求解器算法（官方标准为 euler）。",
    )
    scheduler: SchedulerName = Field(
        default="simple",
        description="噪声调度策略（官方标准为 simple）。",
    )
    denoise: float = Field(
        default=1.0,
        ge=0.05,
        le=1.0,
        description="去噪重绘幅度（常规生成与指令编辑推荐 1.0）。",
    )
    seed: int = Field(
        default=0,
        ge=0,
        description="随机种子（0 表示自动随机；正整数可锁定复现）。",
    )
    auraflow_shift: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=10.0,
        description="可选采样时间步偏移覆写 (ModelSamplingAuraFlow shift)，留空使用模型内置默认。",
    )

    # 5. KV Cache, Precision & Output Format
    kv_cache_device: KvCacheDevice = Field(
        default="smart",
        description="QwenImage21Cache 前缀 KV 缓存位置：smart / auto / cpu / gpu / off。",
    )
    kv_cache_dtype: KvCacheDtype = Field(
        default="default",
        description="KV 缓存存储精度：default（BF16）、int8、int4。",
    )
    unet_weight_dtype: UnetWeightDtype = Field(
        default="default",
        description="UNet 主模型加载精度：default（BF16）或 fp8_e4m3fn 省显存模式。",
    )
    clip_device: ClipDevice = Field(
        default="default",
        description="Qwen3-VL-8B 编码器运行设备：default（GPU）或 cpu。",
    )
    output_format: ImageOutputFormat = Field(
        default="png",
        description="输出图片格式：png / webp 可保留模型输出的透明通道；jpeg 不支持透明通道。",
    )
    output_quality: int = Field(
        default=95,
        ge=60,
        le=100,
        description="WebP / JPEG 导出品质（60~100）。",
    )
    release_vram_after: bool = Field(
        default=False,
        description="本次生成完成后是否释放显存缓存。",
    )

    def effective_references(self) -> List[str]:
        refs = [r.strip() for r in self.reference_images if r and r.strip()]
        if not refs:
            for item in (self.image_1, self.image_2, self.image_3, self.image_4):
                if item and item.strip():
                    refs.append(item.strip())
        return refs

    @model_validator(mode="after")
    def validate_mode_and_references(self) -> "QwenImageGenerateRequest":
        self.prompt = self.prompt.strip()
        if not self.prompt:
            raise ValueError("请输入画面描述或图像编辑指令。")
        raw_refs = self.reference_images or [self.image_1, self.image_2, self.image_3, self.image_4]
        if self.mode != "t2i":
            empty_seen = False
            for ref in raw_refs:
                if not ref or not ref.strip():
                    empty_seen = True
                elif empty_seen:
                    raise ValueError("参考图片之间不能留空，请按 <image1>、<image2> 的顺序上传或移除空槽位。")
        refs = self.effective_references()
        if self.mode != "t2i" and len(refs) < 1:
            raise ValueError("图生图模式请至少上传 1 张参考图片 (<image1>)。")
        if self.mode == "edit_dual" and len(refs) < 2:
            raise ValueError("双图融合模式需要至少上传 2 张参考图 (<image1> 与 <image2>)。")
        if self.resolution_tier == "original" and (self.mode == "t2i" or self.aspect_ratio != "match_input"):
            raise ValueError("原图分辨率仅用于图生图，请同时选择跟随主参考图比例。")
        if self.mode == "t2i" and self.aspect_ratio == "match_input":
            self.aspect_ratio = "1:1"
        self.width = snap32(self.width)
        self.height = snap32(self.height)
        return self


class GeneratedImageItem(BaseModel):
    url: str
    filename: str
    format: ImageOutputFormat
    width: int
    height: int
    size_bytes: int


class QwenImageResult(BaseModel):
    image_url: str
    filename: str
    format: ImageOutputFormat
    width: int
    height: int
    size_bytes: int
    images: List[GeneratedImageItem]
    mode: WorkflowMode
    used_seed: int
    steps: int
    cfg: float
    sampler_name: str
    scheduler: str
    kv_cache_device_used: str
    kv_cache_dtype: str
    active_loras: List[Dict[str, object]]
    reference_urls: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    mock: bool = False
