import type { IndexTTSRequestPayload, LanguageCode, TtsForm } from "./types";

export const DEFAULT_FORM: TtsForm = {
  text: "", speakerAudio: "preset:ref_audio", language: "zh", speed: 1,
  emotionMode: "clone", emotionStrength: 0.8, emotionAudio: "", emotionText: "", outputFormat: "mp3",
};

export const EXAMPLE_TEXT: Record<LanguageCode, string> = {
  zh: "你好，欢迎来到今天的故事。放慢脚步，让我们一起听听接下来会发生什么。",
  en: "Hello, and welcome to today's story. Take a moment to relax, and let's begin.",
  ja: "こんにちは。今日のお話へようこそ。少し肩の力を抜いて、一緒に楽しみましょう。",
  es: "Hola, bienvenidos a la historia de hoy. Relájate un momento y comencemos.",
  ar: "مرحباً بكم في قصة اليوم. خذوا لحظة للاسترخاء، ولنبدأ معاً.",
};

export function buildTtsRequest(form: TtsForm): IndexTTSRequestPayload {
  return {
    text: form.text.trim(), speaker_audio: form.speakerAudio, language: form.language,
    // The native control is a duration multiplier; the Studio shows speaking speed.
    duration_factor: Number((1 / form.speed).toFixed(4)), emotion_mode: form.emotionMode,
    emo_alpha: form.emotionStrength, output_format: form.outputFormat,
    ...(form.emotionMode === "reference" ? { emotion_audio: form.emotionAudio } : {}),
    ...(form.emotionMode === "text" ? {
      emotion_text: form.emotionText.trim() || null,
      auto_emotion_from_text: !form.emotionText.trim(),
    } : {}),
  };
}

export function restoreTtsForm(params: Partial<IndexTTSRequestPayload>): TtsForm {
  const duration = params.duration_factor || 1;
  return {
    ...DEFAULT_FORM,
    text: params.text || "", speakerAudio: params.speaker_audio || DEFAULT_FORM.speakerAudio,
    language: params.language || DEFAULT_FORM.language,
    speed: Number(Math.max(0.5, Math.min(2, 1 / duration)).toFixed(2)),
    emotionMode: params.emotion_mode === "text" || params.emotion_mode === "reference" ? params.emotion_mode : "clone",
    emotionStrength: params.emo_alpha ?? DEFAULT_FORM.emotionStrength,
    emotionAudio: params.emotion_audio || "",
    emotionText: params.auto_emotion_from_text ? "" : params.emotion_text || "",
    outputFormat: params.output_format || DEFAULT_FORM.outputFormat,
  };
}
