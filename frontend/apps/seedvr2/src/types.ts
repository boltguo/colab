export type SeedVR2Mode = "video" | "image";
export type SeedVR2ModelVariant = "7b_sharp" | "3b_fast";
export type SizingMode = "multiplier" | "shorter_edge" | "longer_edge" | "dimensions";
export type UpscaleInterpolation = "lanczos" | "bicubic" | "bilinear" | "area" | "nearest-exact";
export type CropMode = "disabled" | "center";
export type ColorCorrectionMethod = "lab" | "wavelet" | "adain" | "none";
export type ChunkingMode = "auto" | "manual";
export type SamplerName = "euler" | "euler_ancestral" | "heun" | "dpmpp_2m" | "uni_pc";
export type SchedulerName = "simple" | "normal" | "sgm_uniform" | "beta" | "karras";
export type UnetWeightDtype = "default" | "fp8_e4m3fn" | "fp8_e4m3fn_fast" | "fp8_e5m2";

export type ImageOutputFormat = "png" | "webp" | "jpeg";
export type VideoOutputFormat = "mp4" | "webm" | "mkv";
export type VideoCodecChoice = "auto" | "h264" | "av1";
export type ColorSpaceChoice = "match_input" | "sRGB" | "HDR" | "HDR PQ";
export type BitDepthChoice = "match_input" | "auto" | "8" | "10";

export interface SeedVR2Params {
  mode: SeedVR2Mode;
  input_file: string;
  model_variant: SeedVR2ModelVariant;

  sizing_mode: SizingMode;
  scale_factor: number;
  target_shorter_edge: number;
  target_longer_edge: number;
  target_width: number;
  target_height: number;
  crop_mode: CropMode;
  upscale_interpolation: UpscaleInterpolation;

  color_correction: ColorCorrectionMethod;
  split_latent: boolean;
  chunking_mode: ChunkingMode;
  frames_per_chunk: number;
  temporal_overlap: number;

  trim_video: boolean;
  start_time: number;
  duration: number;
  keep_audio: boolean;
  fps_override: number;

  steps: number;
  cfg: number;
  denoise: number;
  sampler_name: SamplerName;
  scheduler: SchedulerName;
  seed: number;

  unet_weight_dtype: UnetWeightDtype;
  vae_tile_size: number;
  vae_tile_overlap: number;
  vae_temporal_size: number;
  vae_temporal_overlap: number;

  preserve_alpha: boolean;
  image_output_format: ImageOutputFormat;
  image_quality: number;

  video_output_format: VideoOutputFormat;
  video_codec: VideoCodecChoice;
  crf: number;
  color_space: ColorSpaceChoice;
  bit_depth: BitDepthChoice;
  release_vram_after: boolean;
}

export interface SeedVR2Result {
  media_type: SeedVR2Mode;
  mode: SeedVR2Mode;
  model_variant: SeedVR2ModelVariant;
  model_label: string;
  output_url: string;
  video_url?: string | null;
  image_url?: string | null;
  filename: string;
  format: string;
  size_bytes: number;
  input_url: string;
  input_width: number;
  input_height: number;
  width: number;
  height: number;
  effective_scale: number;
  duration_sec?: number | null;
  fps?: number | null;
  has_audio: boolean;
  used_seed: number;
  steps: number;
  cfg: number;
  denoise: number;
  color_correction: ColorCorrectionMethod;
  split_latent: boolean;
  warnings: string[];
  mock: boolean;
}

export const DEFAULT_SEEDVR2_PARAMS: SeedVR2Params = {
  mode: "video",
  input_file: "",
  model_variant: "7b_sharp",

  sizing_mode: "multiplier",
  scale_factor: 2.0,
  target_shorter_edge: 1440,
  target_longer_edge: 3840,
  target_width: 2560,
  target_height: 1440,
  crop_mode: "center",
  upscale_interpolation: "lanczos",

  color_correction: "lab",
  split_latent: false,
  chunking_mode: "auto",
  frames_per_chunk: 21,
  temporal_overlap: 2,

  trim_video: false,
  start_time: 0,
  duration: 0,
  keep_audio: true,
  fps_override: 0,

  steps: 1,
  cfg: 1.0,
  denoise: 1.0,
  sampler_name: "euler",
  scheduler: "simple",
  seed: 0,

  unet_weight_dtype: "default",
  vae_tile_size: 512,
  vae_tile_overlap: 128,
  vae_temporal_size: 64,
  vae_temporal_overlap: 8,

  preserve_alpha: true,
  image_output_format: "png",
  image_quality: 94,

  video_output_format: "mp4",
  video_codec: "auto",
  crf: 18,
  color_space: "match_input",
  bit_depth: "match_input",
  release_vram_after: false,
};

export function alignEven(value: number, minimum = 16, maximum = 16384): number {
  const clamped = Math.max(minimum, Math.min(maximum, Math.round(value)));
  const even = clamped - (clamped % 2);
  return Math.max(minimum, even);
}

export function alignChunkFrames(frames: number): number {
  if (!Number.isFinite(frames) || frames <= 1) return 1;
  const k = Math.max(1, Math.round((frames - 1) / 4));
  return Math.min(16381, 4 * k + 1);
}

export function computeTargetDimensions(
  srcW: number,
  srcH: number,
  params: Pick<
    SeedVR2Params,
    | "sizing_mode"
    | "scale_factor"
    | "target_shorter_edge"
    | "target_longer_edge"
    | "target_width"
    | "target_height"
  >
): { width: number; height: number; effectiveScale: number } {
  const sw = Math.max(2, Math.round(srcW));
  const sh = Math.max(2, Math.round(srcH));
  let w = sw;
  let h = sh;

  if (params.sizing_mode === "multiplier") {
    w = Math.round(sw * params.scale_factor);
    h = Math.round(sh * params.scale_factor);
  } else if (params.sizing_mode === "shorter_edge") {
    const shortTarget = Math.max(64, Math.round(params.target_shorter_edge));
    if (sh < sw) {
      h = shortTarget;
      w = Math.round((sw / sh) * shortTarget);
    } else if (sw < sh) {
      w = shortTarget;
      h = Math.round((sh / sw) * shortTarget);
    } else {
      w = shortTarget;
      h = shortTarget;
    }
  } else if (params.sizing_mode === "longer_edge") {
    const longTarget = Math.max(64, Math.round(params.target_longer_edge));
    if (sh > sw) {
      h = longTarget;
      w = Math.round((sw / sh) * longTarget);
    } else if (sw > sh) {
      w = longTarget;
      h = Math.round((sh / sw) * longTarget);
    } else {
      w = longTarget;
      h = longTarget;
    }
  } else {
    const tw = Math.round(params.target_width);
    const th = Math.round(params.target_height);
    if (tw <= 0 && th <= 0) {
      w = sw;
      h = sh;
    } else if (tw <= 0) {
      h = th;
      w = Math.max(2, Math.round(sw * (th / sh)));
    } else if (th <= 0) {
      w = tw;
      h = Math.max(2, Math.round(sh * (tw / sw)));
    } else {
      w = tw;
      h = th;
    }
  }

  const outW = alignEven(w);
  const outH = alignEven(h);
  const effectiveScale = Math.round(Math.max(outW / sw, outH / sh) * 100) / 100;
  return { width: outW, height: outH, effectiveScale };
}
