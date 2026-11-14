import type { LoraSlotConfig } from "@colab/shared";

export type WorkflowMode = "t2i" | "img2img" | "edit_single" | "edit_dual" | "edit_multi";
export type ResolutionTier = "2K" | "1K" | "original";
export type StandardAspectRatio = "1:1" | "16:9" | "9:16" | "4:3" | "3:4" | "3:2" | "2:3" | "21:9";
export type AspectRatioChoice = "match_input" | StandardAspectRatio | "custom";
export type ReferenceConditioningMode = "vae_and_vision" | "vision_only";

export type SamplerName =
  | "euler"
  | "euler_ancestral"
  | "heun"
  | "dpmpp_2m"
  | "dpmpp_2m_sde"
  | "dpmpp_3m_sde"
  | "uni_pc"
  | "res_multistep"
  | "lms";

export type SchedulerName =
  | "simple"
  | "normal"
  | "karras"
  | "exponential"
  | "sgm_uniform"
  | "beta"
  | "ddim_uniform";

export type KvCacheDevice = "smart" | "auto" | "cpu" | "gpu" | "off";
export type KvCacheDtype = "default" | "int8" | "int4";
export type UnetWeightDtype = "default" | "fp8_e4m3fn" | "fp8_e4m3fn_fast" | "fp8_e5m2";
export type ClipDevice = "default" | "cpu";
export type ImageOutputFormat = "png" | "webp" | "jpeg";

export interface QwenImageParams {
  mode: WorkflowMode;
  prompt: string;
  negative_prompt: string;
  reference_images: string[];
  reference_conditioning_mode: ReferenceConditioningMode;
  resolution_tier: ResolutionTier;
  aspect_ratio: AspectRatioChoice;
  width: number;
  height: number;
  batch_size: number;
  loras: LoraSlotConfig[];
  steps: number;
  cfg: number;
  sampler_name: SamplerName;
  scheduler: SchedulerName;
  denoise: number;
  seed: number;
  auraflow_shift: number | null;
  kv_cache_device: KvCacheDevice;
  kv_cache_dtype: KvCacheDtype;
  unet_weight_dtype: UnetWeightDtype;
  clip_device: ClipDevice;
  output_format: ImageOutputFormat;
  output_quality: number;
  release_vram_after: boolean;
}

export interface GeneratedImageItem {
  url: string;
  filename: string;
  format: ImageOutputFormat;
  width: number;
  height: number;
  size_bytes: number;
}

export interface QwenImageResult {
  image_url: string;
  filename: string;
  format: ImageOutputFormat;
  width: number;
  height: number;
  size_bytes: number;
  images: GeneratedImageItem[];
  mode: WorkflowMode;
  used_seed: number;
  steps: number;
  cfg: number;
  sampler_name: string;
  scheduler: string;
  kv_cache_device_used: string;
  kv_cache_dtype: string;
  active_loras: Array<{
    filename: string;
    label: string;
    strength_model: number;
    apply_to_clip: boolean;
    strength_clip: number;
  }>;
  reference_urls: string[];
  warnings: string[];
  mock: boolean;
}

export const ASPECT_RATIO_OPTIONS: Array<{
  value: StandardAspectRatio;
  label: string;
  sub: string;
  rw: number;
  rh: number;
}> = [
  { value: "1:1", label: "1:1", sub: "方图", rw: 1, rh: 1 },
  { value: "16:9", label: "16:9", sub: "横屏", rw: 16, rh: 9 },
  { value: "9:16", label: "9:16", sub: "竖屏", rw: 9, rh: 16 },
  { value: "4:3", label: "4:3", sub: "标准", rw: 4, rh: 3 },
  { value: "3:4", label: "3:4", sub: "人像", rw: 3, rh: 4 },
  { value: "3:2", label: "3:2", sub: "摄影", rw: 3, rh: 2 },
  { value: "2:3", label: "2:3", sub: "海报", rw: 2, rh: 3 },
  { value: "21:9", label: "21:9", sub: "宽幅", rw: 21, rh: 9 },
];

export const SYMMETRIC_RATIO_SWAP: Partial<Record<StandardAspectRatio, StandardAspectRatio>> = {
  "16:9": "9:16",
  "9:16": "16:9",
  "4:3": "3:4",
  "3:4": "4:3",
  "3:2": "2:3",
  "2:3": "3:2",
};

export function snap32(val: number): number {
  const s = Math.round(val / 32) * 32;
  return Math.max(256, Math.min(4096, s));
}

export function editImageGeometry(
  params: QwenImageParams,
  width: number,
  height: number,
  aspect: AspectRatioChoice = "custom",
): QwenImageParams {
  return {
    ...params,
    resolution_tier: params.resolution_tier === "original" && aspect !== "match_input" ? "2K" : params.resolution_tier,
    aspect_ratio: aspect,
    width,
    height,
  };
}

export function calcPresetDimensions(
  tier: ResolutionTier,
  aspect: StandardAspectRatio
): { width: number; height: number } {
  const mp = tier === "1K" ? 1.0 : 4.0;
  const found = ASPECT_RATIO_OPTIONS.find((a) => a.value === aspect) || ASPECT_RATIO_OPTIONS[0];
  const ratio = found.rw / found.rh;
  const totalPx = mp * 1024 * 1024;
  return {
    width: snap32(Math.sqrt(totalPx * ratio)),
    height: snap32(Math.sqrt(totalPx / ratio)),
  };
}

export function calcRefMatchedDimensions(
  tier: ResolutionTier,
  refDims: { w: number; h: number } | null
): { width: number; height: number } {
  if (!refDims || refDims.w <= 0 || refDims.h <= 0) {
    const base = tier === "1K" ? 1024 : 2048;
    return { width: base, height: base };
  }
  if (tier === "original") {
    return { width: snap32(refDims.w), height: snap32(refDims.h) };
  }
  const baseSide = tier === "1K" ? 1024 : 2048;
  const ratio = refDims.w / refDims.h;
  return {
    width: snap32(Math.sqrt(baseSide * baseSide * ratio)),
    height: snap32(Math.sqrt(baseSide * baseSide / ratio)),
  };
}

export const DEFAULT_QWEN_IMAGE_PARAMS: QwenImageParams = {
  mode: "t2i",
  prompt: "",
  negative_prompt: "",
  reference_images: [],
  reference_conditioning_mode: "vae_and_vision",
  resolution_tier: "2K",
  aspect_ratio: "1:1",
  width: 2048,
  height: 2048,
  batch_size: 1,
  loras: [],
  steps: 40,
  cfg: 1.0,
  sampler_name: "euler",
  scheduler: "simple",
  denoise: 1.0,
  seed: 0,
  auraflow_shift: null,
  kv_cache_device: "smart",
  kv_cache_dtype: "default",
  unet_weight_dtype: "default",
  clip_device: "default",
  output_format: "png",
  output_quality: 95,
  release_vram_after: false,
};
