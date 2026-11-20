export type SwapMode = "single" | "multi";
export type ResolutionTier = "480p" | "736p";
export type ClipRangeMode = "full" | "preview5s" | "custom";
export type VideoOutputFormat = "mp4" | "webm" | "mkv";

export interface CharacterSlot {
  image: string;
  target_description?: string;
  name?: string;
  appearance_description?: string;
}

export interface GuideFrameSlot {
  image: string;
  frame_index: number;
}

export interface H3CharacterSwapParams {
  mode: SwapMode;
  source_video: string;
  characters: CharacterSlot[];
  prompt: string;
  guide_frames: GuideFrameSlot[];
  resolution_tier: ResolutionTier;
  preserve_aspect: boolean;
  clip_range_mode: ClipRangeMode;
  start_time_sec: number;
  duration_sec: number;
  keep_audio: boolean;
  seed: number;
  output_format: VideoOutputFormat;
}

export interface H3CharacterSwapRequest {
  mode: SwapMode;
  source_video: string;
  characters: CharacterSlot[];
  prompt: string;
  guide_frames: GuideFrameSlot[];
  resolution_tier: ResolutionTier;
  preserve_aspect: boolean;
  start_time_sec: number;
  duration_sec: number;
  keep_audio: boolean;
  seed: number;
  output_format: VideoOutputFormat;
}

export interface H3CharacterSwapResult {
  video_url: string;
  filename: string;
  format: VideoOutputFormat;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  duration_sec: number;
  has_audio: boolean;
  size_bytes: number;
  seed: number;
  mode: SwapMode;
  character_count: number;
  window_count: number;
  resolution_tier: ResolutionTier;
  source_video_ref: string;
  input_width: number;
  input_height: number;
  input_fps: number;
  input_start_time: number;
  effective_prompt: string;
  elapsed_sec: number;
  mock: boolean;
}

export function createEmptyCharacterSlot(): CharacterSlot {
  return {
    image: "",
    target_description: "",
  };
}

export const DEFAULT_SWAP_PARAMS: H3CharacterSwapParams = {
  mode: "single",
  source_video: "",
  characters: [createEmptyCharacterSlot()],
  prompt: "",
  guide_frames: [],
  resolution_tier: "480p",
  preserve_aspect: true,
  clip_range_mode: "full",
  start_time_sec: 0,
  duration_sec: 5,
  keep_audio: true,
  seed: 0,
  output_format: "mp4",
};
