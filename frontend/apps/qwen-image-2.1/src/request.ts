import { snap32, type QwenImageParams } from "./types.ts";

export type QwenImageStudioRequest = Pick<QwenImageParams, "mode" | "prompt" | "negative_prompt" | "reference_images"
  | "resolution_tier" | "aspect_ratio" | "width" | "height" | "batch_size" | "loras" | "steps" | "cfg" | "denoise" | "seed" | "output_format">;

/** Ignore legacy professional controls when a take is restored in the everyday Studio. */
export function buildStudioImageRequest(params: QwenImageParams, references: string[]): QwenImageStudioRequest {
  const isEdit = params.mode !== "t2i";
  return {
    mode: isEdit ? "img2img" : "t2i", prompt: params.prompt, negative_prompt: params.negative_prompt,
    reference_images: isEdit ? references : [], resolution_tier: params.resolution_tier,
    aspect_ratio: params.aspect_ratio, width: snap32(params.width), height: snap32(params.height),
    batch_size: params.batch_size, loras: params.loras.map((slot) => ({ ...slot, apply_to_clip: false, strength_clip: 1 })), steps: params.steps, cfg: params.cfg,
    denoise: isEdit ? params.denoise : 1, seed: params.seed, output_format: params.output_format,
  };
}
