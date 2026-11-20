import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_FORM, DEFAULT_SPEAKER_PRESET, JA_SPEAKER_PRESET, buildTtsRequest, restoreTtsForm, switchTtsLanguage } from "../frontend/apps/indextts-2.5/src/request.ts";

test("speaking speed increases while native duration decreases, including supported limits", () => {
  for (const [speed, duration] of [[0.5, 2], [1, 1], [1.25, 0.8], [2, 0.5]]) {
    const request = buildTtsRequest({ ...DEFAULT_FORM, text: "  你好  ", speed });
    assert.equal(request.duration_factor, duration);
    assert.equal(request.text, "你好");
    assert.equal(restoreTtsForm(request).speed, speed);
  }
});

test("legacy history restores common controls without resubmitting removed processing or sampling", () => {
  const legacy = { text: "历史台词", speaker_audio: "preset:ref_audio", language: "zh", duration_factor: 1.25,
    emotion_mode: "vector", emotion_vector: { angry: 1 }, temperature: 1.9, seed: 123,
    tail_fade_ms: 500, loudness_norm: true, trim_silence: true, output_format: "wav" };
  const request = buildTtsRequest(restoreTtsForm(legacy));
  assert.equal(request.text, legacy.text);
  assert.equal(request.duration_factor, legacy.duration_factor);
  assert.equal(request.output_format, "wav");
  assert.equal(request.emotion_mode, "clone");
  for (const key of ["emotion_vector", "temperature", "seed", "tail_fade_ms", "loudness_norm", "trim_silence"]) {
    assert.equal(key in request, false, key);
  }
});

test("emotion modes only send active conditioning and empty descriptions use automatic emotion", () => {
  const form = { ...DEFAULT_FORM, emotionText: " 温柔 ", emotionAudio: "voice.mp3" };
  const clone = buildTtsRequest(form);
  assert.equal("emotion_text" in clone, false);
  assert.equal("emotion_audio" in clone, false);
  const text = buildTtsRequest({ ...form, emotionMode: "text" });
  assert.equal(text.emotion_text, "温柔");
  assert.equal(text.auto_emotion_from_text, false);
  const auto = buildTtsRequest({ ...form, emotionMode: "text", emotionText: " " });
  assert.equal(auto.emotion_text, null);
  assert.equal(auto.auto_emotion_from_text, true);
  const reference = buildTtsRequest({ ...form, emotionMode: "reference" });
  assert.equal(reference.emotion_audio, "voice.mp3");
  assert.equal("emotion_text" in reference, false);
});

test("switching to Japanese selects the Japanese preset without overwriting custom or chosen voices", () => {
  const toJa = switchTtsLanguage(DEFAULT_FORM, "ja");
  assert.equal(toJa.language, "ja");
  assert.equal(toJa.speakerAudio, JA_SPEAKER_PRESET);

  const backToZh = switchTtsLanguage(toJa, "zh");
  assert.equal(backToZh.language, "zh");
  assert.equal(backToZh.speakerAudio, DEFAULT_SPEAKER_PRESET);

  const customVoice = { ...DEFAULT_FORM, speakerAudio: "uploaded-voice.wav" };
  assert.equal(switchTtsLanguage(customVoice, "ja").speakerAudio, "uploaded-voice.wav");

  const crossLingualSage = { ...toJa, speakerAudio: DEFAULT_SPEAKER_PRESET };
  assert.equal(switchTtsLanguage(crossLingualSage, "en").speakerAudio, DEFAULT_SPEAKER_PRESET);
});
