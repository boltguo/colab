import type {
  CharacterSlot,
  ClipRangeMode,
  H3CharacterSwapParams,
  H3CharacterSwapRequest,
  ResolutionTier,
} from "./types";
import { createEmptyCharacterSlot } from "./types.ts";

export const DEFAULT_WINDOW_FRAMES = 226;
export const HISTORY_OVERLAP_FRAMES = 5;
export const NATIVE_FPS = 24;

export function snap32(value: number, minimum = 32): number {
  const snapped = Math.round(value / 32) * 32;
  return Math.max(minimum, snapped);
}

export function computeSwapPreviewDimensions(
  srcW: number,
  srcH: number,
  tier: ResolutionTier,
  preserveAspect = true
): { width: number; height: number } {
  const sw = Math.max(2, Math.round(srcW || 16));
  const sh = Math.max(2, Math.round(srcH || 9));
  const shortEdge = tier === "736p" ? 736 : 480;
  const landscape = sw >= sh;

  if (!preserveAspect) {
    const longEdge = tier === "736p" ? 1280 : 832;
    return landscape
      ? { width: longEdge, height: shortEdge }
      : { width: shortEdge, height: longEdge };
  }

  const rawRatio = Math.max(sw, sh) / Math.max(1, Math.min(sw, sh));
  const clampedRatio = Math.max(1.0, Math.min(1.85, rawRatio));
  const longEdge = snap32(shortEdge * clampedRatio, shortEdge);
  return landscape
    ? { width: longEdge, height: shortEdge }
    : { width: shortEdge, height: longEdge };
}

export function estimateWindowCount(durationSec: number, windowFrames = DEFAULT_WINDOW_FRAMES): number {
  if (!Number.isFinite(durationSec) || durationSec <= 0) return 1;
  const frames = Math.max(1, Math.round(durationSec * NATIVE_FPS));
  if (frames <= windowFrames) return 1;
  const step = Math.max(1, windowFrames - HISTORY_OVERLAP_FRAMES);
  return 1 + Math.ceil((frames - windowFrames) / step);
}

export function buildCharacterSwapRequest(
  params: H3CharacterSwapParams,
  options: { fallbackSource?: string; fallbackCharImage?: string } = {}
): H3CharacterSwapRequest {
  const scopedSlots = params.mode === "single" ? params.characters.slice(0, 1) : params.characters;
  const activeCharacters: CharacterSlot[] = scopedSlots
    .map((slot) => {
      const image = slot.image.trim();
      const name = (slot.name || "").trim();
      const target = (slot.target_description || "").trim();
      const appearance = (slot.appearance_description || "").trim();
      return {
        image,
        ...(name ? { name } : {}),
        ...(target ? { target_description: target } : {}),
        ...(appearance ? { appearance_description: appearance } : {}),
      };
    })
    .filter((slot) => slot.image.length > 0);

  const characters: CharacterSlot[] =
    activeCharacters.length > 0
      ? activeCharacters
      : options.fallbackCharImage
      ? [{ image: options.fallbackCharImage }]
      : [];

  const guide_frames = params.guide_frames
    .map((g) => ({
      image: g.image.trim(),
      frame_index: Math.max(0, Math.round(Number(g.frame_index) || 0)),
    }))
    .filter((g) => g.image.length > 0);

  let start_time_sec = 0;
  let duration_sec = 0;
  if (params.clip_range_mode === "preview5s") {
    duration_sec = 5;
  } else if (params.clip_range_mode === "custom") {
    start_time_sec = Math.max(0, Number(params.start_time_sec) || 0);
    duration_sec = Math.max(1, Math.min(60, Number(params.duration_sec) || 5));
  }

  return {
    mode: params.mode,
    source_video: params.source_video.trim() || options.fallbackSource || "",
    characters,
    prompt: params.prompt.trim(),
    guide_frames,
    resolution_tier: params.resolution_tier,
    preserve_aspect: params.preserve_aspect,
    start_time_sec,
    duration_sec,
    keep_audio: params.keep_audio,
    seed: Math.max(0, Math.round(Number(params.seed) || 0)),
    output_format: params.output_format,
  };
}

export function restoreCharacterSwapState(
  raw: Partial<H3CharacterSwapRequest>
): H3CharacterSwapParams {
  const start = Math.max(0, Number(raw.start_time_sec) || 0);
  const dur = Math.max(0, Number(raw.duration_sec) || 0);
  let clip_range_mode: ClipRangeMode = "full";
  if (start === 0 && dur === 5) {
    clip_range_mode = "preview5s";
  } else if (start > 0 || dur > 0) {
    clip_range_mode = "custom";
  }

  const mode = raw.mode === "multi" ? "multi" : "single";
  const mappedChars: CharacterSlot[] =
    Array.isArray(raw.characters) && raw.characters.length > 0
      ? raw.characters.map((slot) => ({
          image: String(slot.image || ""),
          target_description: String(slot.target_description || ""),
          ...(slot.name ? { name: String(slot.name) } : {}),
        }))
      : [createEmptyCharacterSlot()];

  const characters =
    mode === "single"
      ? mappedChars.slice(0, 1)
      : mappedChars.length >= 2
      ? mappedChars
      : [...mappedChars, createEmptyCharacterSlot()];

  return {
    mode,
    source_video: String(raw.source_video || ""),
    characters,
    prompt: String(raw.prompt || ""),
    guide_frames: Array.isArray(raw.guide_frames)
      ? raw.guide_frames.map((g) => ({
          image: String(g.image || ""),
          frame_index: Math.max(0, Math.round(Number(g.frame_index) || 0)),
        }))
      : [],
    resolution_tier: raw.resolution_tier === "736p" ? "736p" : "480p",
    preserve_aspect: raw.preserve_aspect !== false,
    clip_range_mode,
    start_time_sec: start,
    duration_sec: dur > 0 ? dur : 5,
    keep_audio: raw.keep_audio !== false,
    seed: Math.max(0, Math.round(Number(raw.seed) || 0)),
    output_format: raw.output_format === "webm" || raw.output_format === "mkv" ? raw.output_format : "mp4",
  };
}
