import { NATIVE_FPS, snap32, type MiniMaxH3Params } from "./types.ts";

export type MiniMaxStudioRequest = Pick<MiniMaxH3Params, "mode" | "prompt" | "negative_prompt" | "first_frame" | "last_frame"
  | "ref_images" | "ref_videos" | "ref_audios" | "resolution_tier" | "aspect_ratio" | "width" | "height"
  | "duration_sec" | "fps" | "turbo_enabled" | "loras" | "steps" | "cfg" | "seed" | "soundtrack_enabled" | "output_format" | "video_codec">;

export function buildVideoStudioRequest(params: MiniMaxH3Params): MiniMaxStudioRequest {
  return {
    mode: params.mode, prompt: params.prompt, negative_prompt: params.negative_prompt,
    first_frame: params.mode === "fl2v" ? params.first_frame : null,
    last_frame: params.mode === "fl2v" ? params.last_frame : null,
    ref_images: params.mode === "r2v" ? params.ref_images : [],
    ref_videos: params.mode === "r2v" ? params.ref_videos : [],
    ref_audios: params.mode === "r2v" ? params.ref_audios : [],
    resolution_tier: params.resolution_tier, aspect_ratio: params.aspect_ratio,
    width: snap32(params.width), height: snap32(params.height), duration_sec: params.duration_sec,
    fps: params.soundtrack_enabled ? NATIVE_FPS : params.fps, soundtrack_enabled: params.soundtrack_enabled,
    turbo_enabled: params.turbo_enabled, loras: params.loras.map((slot) => ({ ...slot, apply_to_clip: false, strength_clip: 1 })), steps: params.steps, cfg: params.cfg,
    seed: params.seed, output_format: params.output_format,
    video_codec: params.output_format === "webm" ? "av1" : "h264",
  };
}
