import type { SeedVR2Params } from "./types";

export type SeedVR2StudioRequest = Pick<SeedVR2Params, "mode" | "input_file" | "model_variant" | "sizing_mode" | "scale_factor"
  | "target_shorter_edge" | "target_longer_edge" | "target_width" | "target_height" | "crop_mode"
  | "split_latent" | "keep_audio" | "steps" | "seed" | "image_output_format" | "video_output_format">;

export function buildUpscaleStudioRequest(params: SeedVR2Params, inputFile = params.input_file): SeedVR2StudioRequest {
  return {
    mode: params.mode, input_file: inputFile.trim(), model_variant: params.model_variant,
    sizing_mode: params.sizing_mode, scale_factor: params.scale_factor,
    target_shorter_edge: params.target_shorter_edge, target_longer_edge: params.target_longer_edge,
    target_width: params.target_width, target_height: params.target_height, crop_mode: params.crop_mode,
    split_latent: params.mode === "video" && params.model_variant === "3b_fast",
    keep_audio: params.keep_audio, steps: params.steps, seed: params.seed,
    image_output_format: params.image_output_format, video_output_format: params.video_output_format,
  };
}
