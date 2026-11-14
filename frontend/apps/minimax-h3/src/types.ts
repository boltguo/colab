import type { LoraSlotConfig } from "@colab/shared";

export type H3Mode = "t2v" | "fl2v" | "r2v";
export type H3ResolutionTier = "768p" | "540p" | "1080p" | "custom";
export type StandardAspectRatio =
  | "16:9"
  | "9:16"
  | "1:1"
  | "4:3"
  | "3:4"
  | "3:2"
  | "2:3"
  | "21:9";
export type H3AspectRatio = "match_input" | StandardAspectRatio | "custom";

export type RefImageSizeMode = "match" | "max";
export type RefConditioningMode = "vae_and_vision" | "vision_only";

export type SamplerName =
  | "res_multistep"
  | "euler"
  | "euler_ancestral"
  | "heun"
  | "dpmpp_2m"
  | "dpmpp_2m_sde"
  | "uni_pc"
  | "lms";

export type SchedulerName =
  | "simple"
  | "normal"
  | "beta"
  | "sgm_uniform"
  | "karras"
  | "exponential"
  | "ddim_uniform";

export type VideoOutputFormat = "mp4" | "webm" | "mkv";
export type VideoCodecChoice = "h264" | "av1" | "auto";
export type ColorSpaceChoice = "sRGB" | "HDR" | "HDR PQ";
export type BitDepthChoice = "auto" | "8" | "10";
export type UnetWeightDtype = "default" | "fp8_e4m3fn" | "fp8_e4m3fn_fast" | "fp8_e5m2";
export type ClipDevice = "default" | "cpu";

export interface ReferenceVideoSlotPayload {
  file_id: string;
  use_video_audio: boolean;
}

export interface MiniMaxH3Params {
  mode: H3Mode;
  prompt: string;
  negative_prompt: string;
  first_frame: string | null;
  last_frame: string | null;
  guide_audio: string | null;
  guide_image: string | null;
  guide_frame_idx: number;
  ref_images: string[];
  ref_videos: ReferenceVideoSlotPayload[];
  ref_audios: string[];
  ref_image_size: RefImageSizeMode;
  ref_conditioning_mode: RefConditioningMode;
  resolution_tier: H3ResolutionTier;
  aspect_ratio: H3AspectRatio;
  width: number;
  height: number;
  duration_sec: number;
  frame_count: number | null;
  fps: number;
  turbo_enabled: boolean;
  turbo_strength: number;
  loras: LoraSlotConfig[];
  steps: number;
  cfg: number;
  sampler_name: SamplerName;
  scheduler: SchedulerName;
  denoise: number;
  seed: number;
  enable_sigma_shift: boolean;
  shift_video: number;
  shift_audio: number;
  soundtrack_enabled: boolean;
  output_format: VideoOutputFormat;
  video_codec: VideoCodecChoice;
  crf: number;
  color_space: ColorSpaceChoice;
  bit_depth: BitDepthChoice;
  unet_weight_dtype: UnetWeightDtype;
  clip_device: ClipDevice;
  release_vram_after: boolean;
}

export interface MiniMaxH3Result {
  video_url: string;
  filename: string;
  format: VideoOutputFormat;
  video_codec: string;
  width: number;
  height: number;
  frame_count: number;
  duration_sec: number;
  fps: number;
  has_audio: boolean;
  size_bytes: number;
  mode: H3Mode | "i2v";
  model_variant: string;
  turbo_enabled: boolean;
  used_seed: number;
  steps: number;
  cfg: number;
  sampler_name: string;
  scheduler: string;
  active_loras: Array<{
    filename: string;
    label: string;
    strength_model: number;
    apply_to_clip?: boolean;
    builtin_turbo?: boolean;
  }>;
  reference_summary: {
    images?: number;
    videos?: number;
    video_audios?: number;
    audios?: number;
    prompt_tags?: string[];
  };
  primary_ref_image_url?: string | null;
  warnings: string[];
  mock: boolean;
}

export const NATIVE_FPS = 24;

export const ASPECT_RATIO_OPTIONS: Array<{
  value: StandardAspectRatio;
  label: string;
  sub: string;
  rw: number;
  rh: number;
}> = [
  { value: "16:9", label: "16:9", sub: "横屏标准", rw: 16, rh: 9 },
  { value: "9:16", label: "9:16", sub: "竖屏短片", rw: 9, rh: 16 },
  { value: "1:1", label: "1:1", sub: "正方构图", rw: 1, rh: 1 },
  { value: "4:3", label: "4:3", sub: "经典电视", rw: 4, rh: 3 },
  { value: "3:4", label: "3:4", sub: "竖向人像", rw: 3, rh: 4 },
  { value: "3:2", label: "3:2", sub: "摄影横幅", rw: 3, rh: 2 },
  { value: "2:3", label: "2:3", sub: "摄影竖幅", rw: 2, rh: 3 },
  { value: "21:9", label: "21:9", sub: "电影宽银幕", rw: 21, rh: 9 },
];

export const SYMMETRIC_RATIO_SWAP: Partial<Record<StandardAspectRatio, StandardAspectRatio>> = {
  "16:9": "9:16",
  "9:16": "16:9",
  "4:3": "3:4",
  "3:4": "4:3",
  "3:2": "2:3",
  "2:3": "3:2",
};

export const DURATION_PRESETS: Array<{ sec: number; label: string }> = [
  { sec: 3, label: "3 秒" },
  { sec: 5, label: "5 秒" },
  { sec: 8, label: "8 秒" },
  { sec: 10, label: "10 秒" },
  { sec: 15, label: "15 秒" },
];

export function snap32(val: number, min = 256, max = 2560): number {
  const n = Number.isFinite(val) ? val : 768;
  const snapped = Math.round(n / 32) * 32;
  return Math.max(min, Math.min(max, snapped));
}

export function alignH3Frames(rawFrames: number): number {
  let n = Math.max(5, Math.min(720, Math.round(rawFrames)));
  const rem = n % 17;
  if (rem !== 5) {
    n += ((5 - rem) % 17 + 17) % 17;
  }
  return n;
}

export function durationToH3Frames(durationSec: number): number {
  const raw = Math.max(5, Math.round(durationSec * NATIVE_FPS));
  return alignH3Frames(raw);
}

const RESOLUTION_MEGAPIXELS: Record<string, number> = {
  "540p": 0.52,
  "768p": 0.98,
  "1080p": 2.0,
};

export function calcH3Dimensions(
  tier: H3ResolutionTier,
  aspectRatio: StandardAspectRatio
): { width: number; height: number } {
  const found = ASPECT_RATIO_OPTIONS.find((a) => a.value === aspectRatio) || ASPECT_RATIO_OPTIONS[0];
  const ratio = found.rw / found.rh;

  if (tier === "768p" || tier === "custom") {
    const baseShort = 768;
    const maxPx = 768 * 1344;
    let nomW = ratio >= 1 ? baseShort * ratio : baseShort;
    let nomH = ratio >= 1 ? baseShort : baseShort / ratio;
    if (nomW * nomH > maxPx) {
      const scale = Math.sqrt(maxPx / (nomW * nomH));
      nomW *= scale;
      nomH *= scale;
    }
    return { width: snap32(nomW), height: snap32(nomH) };
  }

  const mp = RESOLUTION_MEGAPIXELS[tier] ?? 0.98;
  const totalPx = mp * 1024 * 1024;
  return {
    width: snap32(Math.sqrt(totalPx * ratio)),
    height: snap32(Math.sqrt(totalPx / ratio)),
  };
}

export function calcRefMatchedDimensions(
  tier: H3ResolutionTier,
  refDims: { w: number; h: number } | null
): { width: number; height: number } {
  if (!refDims || refDims.w <= 0 || refDims.h <= 0) {
    return calcH3Dimensions(tier === "custom" ? "768p" : tier, "16:9");
  }
  const ratio = Math.max(0.2, Math.min(5.0, refDims.w / refDims.h));
  if (tier === "768p" || tier === "custom") {
    const baseShort = 768;
    const maxPx = 768 * 1344;
    let nomW = ratio >= 1 ? baseShort * ratio : baseShort;
    let nomH = ratio >= 1 ? baseShort : baseShort / ratio;
    if (nomW * nomH > maxPx) {
      const scale = Math.sqrt(maxPx / (nomW * nomH));
      nomW *= scale;
      nomH *= scale;
    }
    return { width: snap32(nomW), height: snap32(nomH) };
  }

  const mp = RESOLUTION_MEGAPIXELS[tier] ?? 0.98;
  const totalPx = mp * 1024 * 1024;
  return {
    width: snap32(Math.sqrt(totalPx * ratio)),
    height: snap32(Math.sqrt(totalPx / ratio)),
  };
}

export const DEFAULT_MINIMAX_H3_PARAMS: MiniMaxH3Params = {
  mode: "t2v",
  prompt: "",
  negative_prompt: "",
  first_frame: null,
  last_frame: null,
  guide_audio: null,
  guide_image: null,
  guide_frame_idx: 0,
  ref_images: [],
  ref_videos: [],
  ref_audios: [],
  ref_image_size: "match",
  ref_conditioning_mode: "vae_and_vision",
  resolution_tier: "768p",
  aspect_ratio: "16:9",
  width: 1344,
  height: 768,
  duration_sec: 5.0,
  frame_count: null,
  fps: 24,
  turbo_enabled: false,
  turbo_strength: 1.0,
  loras: [],
  steps: 20,
  cfg: 1.0,
  sampler_name: "res_multistep",
  scheduler: "simple",
  denoise: 1.0,
  seed: 0,
  enable_sigma_shift: false,
  shift_video: 12.0,
  shift_audio: 3.0,
  soundtrack_enabled: true,
  output_format: "mp4",
  video_codec: "h264",
  crf: 18,
  color_space: "sRGB",
  bit_depth: "auto",
  unet_weight_dtype: "default",
  clip_device: "default",
  release_vram_after: false,
};
