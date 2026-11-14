export type LanguageCode = "zh" | "en" | "ja" | "es" | "ar";
export type EmotionMode = "clone" | "vector" | "reference" | "text";
export type OutputFormat = "mp3" | "wav" | "flac";

export interface EmotionVector {
  happy: number;
  angry: number;
  sad: number;
  afraid: number;
  disgusted: number;
  melancholic: number;
  surprised: number;
  calm: number;
}

export interface IndexTTSRequestPayload {
  text: string;
  speaker_audio: string;
  language: LanguageCode;
  duration_factor: number;
  max_ref_seconds: number;

  emotion_mode: EmotionMode;
  emo_alpha: number;
  emotion_vector?: EmotionVector | null;
  normalize_emo_vector: boolean;
  apply_emo_bias: boolean;
  emotion_audio?: string | null;
  emotion_text?: string | null;
  auto_emotion_from_text: boolean;
  use_random: boolean;

  text_normalization: boolean;
  max_text_tokens_per_segment: number;
  interval_silence_ms: number;

  seed: number;
  do_sample: boolean;
  temperature: number;
  top_p: number;
  top_k: number;
  num_beams: number;
  repetition_penalty: number;
  length_penalty: number;
  max_mel_tokens: number;
  diffusion_steps: number;
  inference_cfg_rate: number;

  output_format: OutputFormat;
  loudness_norm: boolean;
  trim_silence: boolean;
  tail_fade_ms: number;
  use_bf16: boolean;
  use_cuda_kernel: boolean;
  use_torch_compile: boolean;
  auto_free_memory: boolean;
}

export interface SubtitleTimelineItem {
  index: number;
  start_sec: number;
  end_sec: number;
  text: string;
}

export interface IndexTTSResult {
  audio_url: string;
  download_url: string;
  filename: string;
  format: string;
  sample_rate: number;
  duration_sec: number;
  size_bytes: number;
  seed: number;
  language: LanguageCode;
  emotion_mode: EmotionMode;
  effective_emo_vector?: number[] | null;
  segments_count?: number;
  rtf?: number;
  speaker_audio_ref?: string;
  subtitle: string;
  srt: string;
  vtt?: string;
  timeline?: SubtitleTimelineItem[];
  subtitle_timing?: "estimated";
  mock?: boolean;
}
