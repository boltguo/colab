export type LanguageCode = "zh" | "en" | "ja" | "es" | "ar";
export type EmotionMode = "clone" | "vector" | "reference" | "text";
export type OutputFormat = "mp3" | "wav" | "flac";

export interface TtsForm {
  text: string;
  speakerAudio: string;
  language: LanguageCode;
  speed: number;
  emotionMode: Exclude<EmotionMode, "vector">;
  emotionStrength: number;
  emotionAudio: string;
  emotionText: string;
  outputFormat: OutputFormat;
}

/** Only everyday controls are submitted; the server supplies inference defaults. */
export interface IndexTTSRequestPayload {
  text: string;
  speaker_audio: string;
  language: LanguageCode;
  duration_factor: number;
  emotion_mode: EmotionMode;
  emo_alpha: number;
  emotion_audio?: string | null;
  emotion_text?: string | null;
  auto_emotion_from_text?: boolean;
  output_format: OutputFormat;
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
  mock?: boolean;
}
