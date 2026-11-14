import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  Alert,
  AudioSourceField,
  Button,
  Card,
  ClearOutlined,
  ControlOutlined,
  CopyOutlined,
  DeleteOutlined,
  Divider,
  DownloadOutlined,
  Empty,
  ExperimentOutlined,
  FontColorsOutlined,
  HistoryOutlined,
  Input,
  InputNumber,
  LockOutlined,
  PlayCircleOutlined,
  Popconfirm,
  Popover,
  Progress,
  QuestionCircleOutlined,
  ReloadOutlined,
  RocketOutlined,
  ScissorOutlined,
  SearchOutlined,
  Segmented,
  Select,
  Slider,
  SlidersOutlined,
  SoundOutlined,
  Space,
  StudioShell,
  SwapOutlined,
  Switch,
  Tag,
  Text,
  TextArea,
  ThunderboltOutlined,
  Tooltip,
  UnlockOutlined,
  fetchPresets,
  resolveApiUrl,
  triggerModelRelease,
  useHistoryStore,
  useStudioFeedback,
  useTaskRunner,
  type HistoryEntry,
  type PresetItem,
} from "@colab/shared";
import type {
  EmotionMode,
  EmotionVector,
  IndexTTSRequestPayload,
  IndexTTSResult,
  LanguageCode,
  OutputFormat,
} from "./types";

const ZERO_EMO_VECTOR: EmotionVector = {
  happy: 0.0,
  angry: 0.0,
  sad: 0.0,
  afraid: 0.0,
  disgusted: 0.0,
  melancholic: 0.0,
  surprised: 0.0,
  calm: 0.0,
};

const OFFICIAL_EMO_BIAS: Record<keyof EmotionVector, number> = {
  happy: 0.9375,
  angry: 0.875,
  sad: 1.0,
  afraid: 1.0,
  disgusted: 0.9375,
  melancholic: 0.9375,
  surprised: 0.6875,
  calm: 0.5625,
};

const EMO_DIMENSIONS: Array<{
  key: keyof EmotionVector;
  label: string;
  en: string;
  tip: string;
}> = [
  { key: "happy", label: "高兴", en: "Happy", tip: "明快笑意与愉悦上扬语调" },
  { key: "angry", label: "愤怒", en: "Angry", tip: "强烈重音与紧绷情绪张力" },
  { key: "sad", label: "悲伤", en: "Sad", tip: "哭腔与哀婉语调表现" },
  { key: "afraid", label: "恐惧", en: "Afraid", tip: "紧张急促与微颤呼吸感" },
  { key: "disgusted", label: "反感", en: "Disgusted", tip: "嫌弃与冷淡疏离语气" },
  { key: "melancholic", label: "低落", en: "Melancholic", tip: "内敛低沉、忧郁舒缓语调" },
  { key: "surprised", label: "惊讶", en: "Surprised", tip: "感叹与高音调转折" },
  { key: "calm", label: "平静", en: "Calm", tip: "克制平稳的播报与叙述感" },
];

const QUICK_TEXT_SAMPLES: Array<{ label: string; lang: LanguageCode; text: string }> = [
  {
    label: "中文通用克隆",
    lang: "zh",
    text: "你好，欢迎使用 IndexTTS 2.5。这里可以调整语速、停顿与情绪，试听不同的表达方式。",
  },
  {
    label: "中文多音字精准控音",
    lang: "zh",
    text: "他在银<行|HANG2>旁边的步行街散步，看着门前整齐的一<行|HANG2>白杨树，觉<得|DE5>心情格外舒畅。",
  },
  {
    label: "English Cross-Lingual",
    lang: "en",
    text: "Welcome to IndexTTS 2.5 Studio. Zero-shot voice cloning, flow-matching CFG tuning, and mastering loudness are all at your fingertips.",
  },
  {
    label: "日本語クロスリンガル",
    lang: "ja",
    text: "こんにちは、IndexTTS 2.5 スタジオへようこそ。<明日|あした>のプレゼンに向けて、自然で感情豊かな音声を合成しましょう。",
  },
  {
    label: "Español",
    lang: "es",
    text: "Hola, bienvenido al estudio profesional de síntesis de voz IndexTTS 2.5 con control acústico completo.",
  },
  {
    label: "العربية",
    lang: "ar",
    text: "مرحباً بكم في استوديو IndexTTS 2.5 لتحويل النص إلى كلام طبيعي متعدد اللغات.",
  },
];

const POLYPHONE_QUICK_CHIPS: Array<{ word: string; pron: string; note: string }> = [
  { word: "行", pron: "XING2", note: "行走 / 行动" },
  { word: "行", pron: "HANG2", note: "行业 / 一行" },
  { word: "重", pron: "CHONG2", note: "重新 / 重复" },
  { word: "重", pron: "ZHONG4", note: "重要 / 重量" },
  { word: "长", pron: "CHANG2", note: "长短 / 漫长" },
  { word: "长", pron: "ZHANG3", note: "生长 / 院长" },
  { word: "乐", pron: "YUE4", note: "音乐 / 乐器" },
  { word: "乐", pron: "LE4", note: "快乐 / 乐观" },
  { word: "going", pron: "G OW1 . IH0 NG", note: "英文 ARPAbet 音标" },
  { word: "明日", pron: "あした", note: "日文假名指定读法" },
];

const EMO_TEXT_EXAMPLES = [
  "开心激动地宣布一个期盼已久的好消息",
  "温柔轻声地讲述睡前故事",
  "严肃冷静地播报突发深度新闻",
  "带着一丝委屈与失落地低声倾诉",
];

interface SceneRecipe {
  id: string;
  label: string;
  desc: string;
  apply: () => Partial<IndexTTSRequestPayload>;
}

const SCENE_RECIPES: SceneRecipe[] = [
  {
    id: "natural_clone",
    label: "原声自然复刻",
    desc: "沿用参考音频的音色和语气，适合通用配音",
    apply: () => ({
      emotion_mode: "clone",
      duration_factor: 1.0,
      max_text_tokens_per_segment: 120,
      interval_silence_ms: 200,
      temperature: 0.8,
      top_p: 0.8,
      top_k: 30,
      num_beams: 3,
      diffusion_steps: 25,
      inference_cfg_rate: 0.7,
      loudness_norm: false,
    }),
  },
  {
    id: "audiobook",
    label: "有声书长文旁白",
    desc: "适当放缓节奏、加长句间呼吸停顿，启用 -16 LUFS 响度标准化，久听不累",
    apply: () => ({
      emotion_mode: "vector",
      emo_alpha: 0.75,
      emotion_vector: { ...ZERO_EMO_VECTOR, calm: 0.85, melancholic: 0.1 },
      duration_factor: 1.06,
      max_text_tokens_per_segment: 100,
      interval_silence_ms: 340,
      temperature: 0.72,
      top_p: 0.8,
      num_beams: 4,
      diffusion_steps: 28,
      inference_cfg_rate: 0.75,
      loudness_norm: true,
    }),
  },
  {
    id: "short_video",
    label: "短视频高感染口播",
    desc: "语速轻快紧凑、缩短停顿间隙，注入愉悦与惊喜情绪张力，抓耳吸睛",
    apply: () => ({
      emotion_mode: "vector",
      emo_alpha: 0.85,
      emotion_vector: { ...ZERO_EMO_VECTOR, happy: 0.65, surprised: 0.25 },
      duration_factor: 0.92,
      max_text_tokens_per_segment: 90,
      interval_silence_ms: 130,
      temperature: 0.85,
      top_p: 0.85,
      diffusion_steps: 25,
      inference_cfg_rate: 0.72,
      loudness_norm: true,
      trim_silence: true,
    }),
  },
  {
    id: "news_anchor",
    label: "新闻/纪录片播报",
    desc: "降低采样随机性、提高束搜索稳定度与音色 CFG，吐字稳健权威",
    apply: () => ({
      emotion_mode: "vector",
      emo_alpha: 0.8,
      emotion_vector: { ...ZERO_EMO_VECTOR, calm: 1.0 },
      duration_factor: 0.98,
      max_text_tokens_per_segment: 130,
      interval_silence_ms: 240,
      temperature: 0.65,
      top_p: 0.75,
      top_k: 25,
      num_beams: 4,
      diffusion_steps: 30,
      inference_cfg_rate: 0.8,
      loudness_norm: true,
    }),
  },
  {
    id: "auto_drama",
    label: "剧本自动情绪 (Qwen)",
    desc: "由内置 QwenEmotion 大模型直接阅读台词语义，自动匹配最契合的 8 维情绪",
    apply: () => ({
      emotion_mode: "text",
      auto_emotion_from_text: true,
      emo_alpha: 0.85,
      duration_factor: 1.0,
      temperature: 0.82,
      diffusion_steps: 25,
      inference_cfg_rate: 0.7,
    }),
  },
];

const EMO_MODE_LABELS: Record<EmotionMode, string> = {
  clone: "继承音色情绪",
  vector: "8 维情绪向量",
  reference: "情感参考音频",
  text: "自然语言情绪",
};

function LabelWithTip({ label, tip, htmlFor }: { label: string; tip?: string; htmlFor?: string }) {
  const content = htmlFor ? <label htmlFor={htmlFor}>{label}</label> : <span>{label}</span>;
  if (!tip) return content;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      {content}
      <Tooltip title={tip}>
        <QuestionCircleOutlined style={{ color: "var(--studio-text-muted)", fontSize: 13, cursor: "help" }} />
      </Tooltip>
    </span>
  );
}

function estimateSegmentsClient(text: string, maxTokens: number): Array<{ text: string; estTokens: number }> {
  const cleaned = text.trim();
  if (!cleaned) return [];
  const budgetChars = Math.max(16, Math.round(maxTokens * 0.9));
  const rawParts = cleaned.split(/(?<=[，。！？、；：,.!?;:\n])/);
  const segs: string[] = [];
  let current = "";
  for (const raw of rawParts) {
    const piece = raw.trim();
    if (!piece) continue;
    if (current && current.length + piece.length > budgetChars) {
      segs.push(current);
      current = piece;
    } else {
      current = current ? `${current}${piece}` : piece;
    }
  }
  if (current) segs.push(current);
  return segs.map((s) => ({
    text: s,
    estTokens: Math.max(2, Math.round(s.length * 1.12)),
  }));
}

export function IndexTTSStudioApp() {
  const textInputId = useId();
  const emoTextInputId = useId();
  const polyWordId = useId();
  const polyPronId = useId();
  const settingsSectionId = useId();

  const textAreaWrapRef = useRef<HTMLDivElement | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const pendingSeekRef = useRef<number | null>(null);
  const { message } = useStudioFeedback();

  // Built-in backend audio presets & active stateless scene recipe
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [activeRecipeId, setActiveRecipeId] = useState<string>("natural_clone");

  // 1. Core Script & Voice State
  const [speakerAudio, setSpeakerAudio] = useState<string>("preset:ref_audio");
  const [text, setText] = useState<string>(QUICK_TEXT_SAMPLES[0].text);
  const [language, setLanguage] = useState<LanguageCode>("zh");
  const [durationFactor, setDurationFactor] = useState<number>(1.0);
  const [maxRefSeconds, setMaxRefSeconds] = useState<number>(15.0);

  // 2. Emotion State
  const [emotionMode, setEmotionMode] = useState<EmotionMode>("clone");
  const [emoAlpha, setEmoAlpha] = useState<number>(0.8);
  const [emotionVector, setEmotionVector] = useState<EmotionVector>({
    ...ZERO_EMO_VECTOR,
    happy: 0.75,
  });
  const [normalizeEmoVector, setNormalizeEmoVector] = useState<boolean>(true);
  const [applyEmoBias, setApplyEmoBias] = useState<boolean>(true);
  const [emotionAudio, setEmotionAudio] = useState<string>("");
  const [emotionText, setEmotionText] = useState<string>(EMO_TEXT_EXAMPLES[0]);
  const [autoEmotionFromText, setAutoEmotionFromText] = useState<boolean>(false);
  const [useRandom, setUseRandom] = useState<boolean>(false);

  // 3. Text Normalization & Segmentation State
  const [textNormalization, setTextNormalization] = useState<boolean>(true);
  const [maxTextTokensPerSegment, setMaxTextTokensPerSegment] = useState<number>(120);
  const [intervalSilenceMs, setIntervalSilenceMs] = useState<number>(200);
  const [showSegmentPreview, setShowSegmentPreview] = useState<boolean>(false);

  // 4. GPT2 & S2Mel CFM State
  const [seed, setSeed] = useState<number>(0);
  const [doSample, setDoSample] = useState<boolean>(true);
  const [temperature, setTemperature] = useState<number>(0.8);
  const [topP, setTopP] = useState<number>(0.8);
  const [topK, setTopK] = useState<number>(30);
  const [numBeams, setNumBeams] = useState<number>(3);
  const [repetitionPenalty, setRepetitionPenalty] = useState<number>(10.0);
  const [lengthPenalty, setLengthPenalty] = useState<number>(0.0);
  const [maxMelTokens, setMaxMelTokens] = useState<number>(1500);
  const [diffusionSteps, setDiffusionSteps] = useState<number>(25);
  const [inferenceCfgRate, setInferenceCfgRate] = useState<number>(0.7);

  // 5. Mastering & Engine State
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("mp3");
  const [loudnessNorm, setLoudnessNorm] = useState<boolean>(false);
  const [trimSilence, setTrimSilence] = useState<boolean>(false);
  const [tailFadeMs, setTailFadeMs] = useState<number>(0);
  const [useBf16, setUseBf16] = useState<boolean>(true);
  const [useCudaKernel, setUseCudaKernel] = useState<boolean>(false);
  const [useTorchCompile, setUseTorchCompile] = useState<boolean>(false);
  const [autoFreeMemory, setAutoFreeMemory] = useState<boolean>(false);
  const [releasingVram, setReleasingVram] = useState<boolean>(false);

  // Authoring Micro-Tools & Audition UI State
  const [polyOpen, setPolyOpen] = useState<boolean>(false);
  const [polyWord, setPolyWord] = useState<string>("");
  const [polyPron, setPolyPron] = useState<string>("");
  const [auditionSource, setAuditionSource] = useState<"synth" | "ref">("synth");
  const [subtitleViewMode, setSubtitleViewMode] = useState<"timeline" | "srt" | "vtt">("timeline");
  const [historyFilter, setHistoryFilter] = useState<string>("");

  const { items: historyItems, addEntry, removeEntry, clearAll } = useHistoryStore<
    IndexTTSResult,
    IndexTTSRequestPayload
  >("indextts-2.5", 50);

  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);

  const refreshPresets = useCallback(() => {
    fetchPresets()
      .then((list) => {
        setPresets(list);
        if (list.length > 0) {
          setSpeakerAudio((prev) => prev || list[0].id);
        }
      })
      .catch(() => {
        setPresets([]);
      });
  }, []);

  useEffect(() => {
    refreshPresets();
  }, [refreshPresets]);

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<
    IndexTTSResult,
    IndexTTSRequestPayload
  >({
    endpointPath: "/api/v1/generate",
    onSuccess: (task) => {
      if (task.result) {
        const entry: HistoryEntry<IndexTTSResult, IndexTTSRequestPayload> = {
          id: task.task_id,
          feature: "indextts-2.5",
          createdAt: task.finished_at || task.created_at,
          elapsedSec: task.elapsed_sec,
          params: task.params,
          result: task.result,
        };
        addEntry(entry);
        setSelectedHistoryId(entry.id);
        setAuditionSource("synth");
        message.success(`语音合成完成（${task.result.duration_sec}s · ${task.result.format.toUpperCase()}）`);
      }
    },
    onError: (errMsg) => {
      message.error(errMsg);
    },
  });

  const currentPayload = useMemo<IndexTTSRequestPayload>(() => {
    return {
      text: text.trim() || QUICK_TEXT_SAMPLES[0].text,
      speaker_audio: speakerAudio || "preset:ref_audio",
      language,
      duration_factor: durationFactor,
      max_ref_seconds: maxRefSeconds,
      emotion_mode: emotionMode,
      emo_alpha: emoAlpha,
      emotion_vector: emotionMode === "vector" ? emotionVector : null,
      normalize_emo_vector: normalizeEmoVector,
      apply_emo_bias: applyEmoBias,
      emotion_audio: emotionMode === "reference" ? emotionAudio || null : null,
      emotion_text:
        emotionMode === "text" && !autoEmotionFromText ? emotionText.trim() || null : null,
      auto_emotion_from_text: emotionMode === "text" ? autoEmotionFromText : false,
      use_random: useRandom,
      text_normalization: textNormalization,
      max_text_tokens_per_segment: maxTextTokensPerSegment,
      interval_silence_ms: intervalSilenceMs,
      seed,
      do_sample: doSample,
      temperature,
      top_p: topP,
      top_k: topK,
      num_beams: numBeams,
      repetition_penalty: repetitionPenalty,
      length_penalty: lengthPenalty,
      max_mel_tokens: maxMelTokens,
      diffusion_steps: diffusionSteps,
      inference_cfg_rate: inferenceCfgRate,
      output_format: outputFormat,
      loudness_norm: loudnessNorm,
      trim_silence: trimSilence,
      tail_fade_ms: tailFadeMs,
      use_bf16: useBf16,
      use_cuda_kernel: useCudaKernel,
      use_torch_compile: useTorchCompile,
      auto_free_memory: autoFreeMemory,
    };
  }, [
    text,
    speakerAudio,
    language,
    durationFactor,
    maxRefSeconds,
    emotionMode,
    emoAlpha,
    emotionVector,
    normalizeEmoVector,
    applyEmoBias,
    emotionAudio,
    emotionText,
    autoEmotionFromText,
    useRandom,
    textNormalization,
    maxTextTokensPerSegment,
    intervalSilenceMs,
    seed,
    doSample,
    temperature,
    topP,
    topK,
    numBeams,
    repetitionPenalty,
    lengthPenalty,
    maxMelTokens,
    diffusionSteps,
    inferenceCfgRate,
    outputFormat,
    loudnessNorm,
    trimSilence,
    tailFadeMs,
    useBf16,
    useCudaKernel,
    useTorchCompile,
    autoFreeMemory,
  ]);

  const estimatedSegments = useMemo(
    () => estimateSegmentsClient(text, maxTextTokensPerSegment),
    [text, maxTextTokensPerSegment]
  );

  // Live 8-dim emotion sum calculation
  const emoStats = useMemo(() => {
    const keys = Object.keys(ZERO_EMO_VECTOR) as Array<keyof EmotionVector>;
    const rawSum = keys.reduce((acc, k) => acc + (emotionVector[k] || 0), 0);
    let biasedSum = keys.reduce(
      (acc, k) => acc + (emotionVector[k] || 0) * (applyEmoBias ? OFFICIAL_EMO_BIAS[k] : 1),
      0
    );
    const capped = normalizeEmoVector && biasedSum > 0.8;
    if (capped) biasedSum = 0.8;
    return { rawSum, effectiveSum: biasedSum * emoAlpha, capped };
  }, [emotionVector, applyEmoBias, normalizeEmoVector, emoAlpha]);

  const applyPartialSettings = (patch: Partial<IndexTTSRequestPayload>) => {
    if (patch.speaker_audio !== undefined) setSpeakerAudio(patch.speaker_audio);
    if (patch.language !== undefined) setLanguage(patch.language);
    if (patch.duration_factor !== undefined) setDurationFactor(patch.duration_factor);
    if (patch.max_ref_seconds !== undefined) setMaxRefSeconds(patch.max_ref_seconds);
    if (patch.emotion_mode !== undefined) setEmotionMode(patch.emotion_mode);
    if (patch.emo_alpha !== undefined) setEmoAlpha(patch.emo_alpha);
    if (patch.emotion_vector) setEmotionVector(patch.emotion_vector);
    if (patch.normalize_emo_vector !== undefined) setNormalizeEmoVector(patch.normalize_emo_vector);
    if (patch.apply_emo_bias !== undefined) setApplyEmoBias(patch.apply_emo_bias);
    if (patch.emotion_audio !== undefined) {
      setEmotionAudio(patch.emotion_audio || "");
    }
    if (patch.emotion_text !== undefined) {
      setEmotionText(patch.emotion_text || "");
    }
    if (patch.auto_emotion_from_text !== undefined) {
      setAutoEmotionFromText(patch.auto_emotion_from_text);
    }
    if (patch.use_random !== undefined) setUseRandom(patch.use_random);
    if (patch.text_normalization !== undefined) setTextNormalization(patch.text_normalization);
    if (patch.max_text_tokens_per_segment !== undefined) {
      setMaxTextTokensPerSegment(patch.max_text_tokens_per_segment);
    }
    if (patch.interval_silence_ms !== undefined) setIntervalSilenceMs(patch.interval_silence_ms);
    if (patch.seed !== undefined) setSeed(patch.seed);
    if (patch.do_sample !== undefined) setDoSample(patch.do_sample);
    if (patch.temperature !== undefined) setTemperature(patch.temperature);
    if (patch.top_p !== undefined) setTopP(patch.top_p);
    if (patch.top_k !== undefined) setTopK(patch.top_k);
    if (patch.num_beams !== undefined) setNumBeams(patch.num_beams);
    if (patch.repetition_penalty !== undefined) setRepetitionPenalty(patch.repetition_penalty);
    if (patch.length_penalty !== undefined) setLengthPenalty(patch.length_penalty);
    if (patch.max_mel_tokens !== undefined) setMaxMelTokens(patch.max_mel_tokens);
    if (patch.diffusion_steps !== undefined) setDiffusionSteps(patch.diffusion_steps);
    if (patch.inference_cfg_rate !== undefined) setInferenceCfgRate(patch.inference_cfg_rate);
    if (patch.output_format !== undefined) setOutputFormat(patch.output_format);
    if (patch.loudness_norm !== undefined) setLoudnessNorm(patch.loudness_norm);
    if (patch.trim_silence !== undefined) setTrimSilence(patch.trim_silence);
    if (patch.tail_fade_ms !== undefined) setTailFadeMs(patch.tail_fade_ms);
    if (patch.use_bf16 !== undefined) setUseBf16(patch.use_bf16);
    if (patch.use_cuda_kernel !== undefined) setUseCudaKernel(patch.use_cuda_kernel);
    if (patch.use_torch_compile !== undefined) setUseTorchCompile(patch.use_torch_compile);
    if (patch.auto_free_memory !== undefined) setAutoFreeMemory(patch.auto_free_memory);
  };

  const applyParamsFromHistory = (entry: HistoryEntry<IndexTTSResult, IndexTTSRequestPayload>) => {
    setText(entry.params.text);
    applyPartialSettings({ ...entry.params, seed: entry.result.seed });
    setActiveRecipeId("");
    message.info("已回填参数并锁定该次生成的实际种子");
  };

  const scrollToSettings = (section: string) => {
    document.getElementById(`${settingsSectionId}-${section}`)?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  const seekSynthAudio = (seconds: number) => {
    pendingSeekRef.current = seconds;
    if (auditionSource !== "synth") {
      setAuditionSource("synth");
      return;
    }
    const player = audioPlayerRef.current;
    if (!player || player.readyState < 1) return;
    pendingSeekRef.current = null;
    player.currentTime = seconds;
    void player.play().catch(() => {});
  };

  const resetSamplingDefaults = () => {
    setDoSample(true);
    setTemperature(0.8);
    setTopP(0.8);
    setTopK(30);
    setNumBeams(3);
    setRepetitionPenalty(10.0);
    setLengthPenalty(0.0);
    setMaxMelTokens(1500);
    setDiffusionSteps(25);
    setInferenceCfgRate(0.7);
    message.success("已恢复官方推荐 GPT2 与 S2Mel 采样默认值");
  };

  const insertAnnotationAtCursor = (wordRaw: string, pronRaw: string) => {
    const w = wordRaw.trim();
    const p = pronRaw.trim();
    if (!w || !p) {
      message.warning("请同时填写「目标字词」与「指定读音/音标」");
      return;
    }
    const tag = `<${w}|${p}>`;
    const textareaEl = textAreaWrapRef.current?.querySelector("textarea");
    if (textareaEl && typeof textareaEl.selectionStart === "number") {
      const start = textareaEl.selectionStart;
      const end = textareaEl.selectionEnd ?? start;
      const nextText = text.slice(0, start) + tag + text.slice(end);
      setText(nextText);
      setPolyOpen(false);
      setPolyWord("");
      setPolyPron("");
      requestAnimationFrame(() => {
        textareaEl.focus();
        const cursor = start + tag.length;
        textareaEl.setSelectionRange(cursor, cursor);
      });
    } else {
      setText((prev) => `${prev}${tag}`);
      setPolyOpen(false);
    }
    message.success(`已插入发音标注 ${tag}`);
  };

  const handleGenerate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isBusy) return;
    if (!text.trim()) {
      message.warning("请输入要合成的台词文本");
      return;
    }
    if (!speakerAudio) {
      message.warning("请选择或上传说话人参考音频");
      return;
    }
    if (emotionMode === "reference" && !emotionAudio) {
      scrollToSettings("emotion");
      message.warning("当前为「情感参考音频」模式，请上传或选择第二段情绪参考音频");
      return;
    }
    if (emotionMode === "text" && !autoEmotionFromText && !emotionText.trim()) {
      scrollToSettings("emotion");
      message.warning("请填写自然语言情绪描述，或开启「自动根据台词分析情绪」");
      return;
    }
    await runTask(currentPayload);
  };

  const displayedEntry: HistoryEntry<IndexTTSResult, IndexTTSRequestPayload> | null = useMemo(() => {
    if (selectedHistoryId) {
      const match = historyItems.find((x) => x.id === selectedHistoryId);
      if (match) return match;
    }
    if (activeTask?.status === "succeeded" && activeTask.result) {
      return {
        id: activeTask.task_id,
        feature: "indextts-2.5",
        createdAt: activeTask.finished_at || activeTask.created_at,
        elapsedSec: activeTask.elapsed_sec,
        params: activeTask.params,
        result: activeTask.result,
      };
    }
    return historyItems[0] || null;
  }, [selectedHistoryId, historyItems, activeTask]);

  const referenceCompareUrl = useMemo(() => {
    const refId = displayedEntry?.result.speaker_audio_ref || displayedEntry?.params.speaker_audio || speakerAudio;
    if (!refId) return "";
    if (refId.startsWith("preset:")) {
      const p = presets.find((x) => x.id === refId);
      return p ? resolveApiUrl(p.url, true) : resolveApiUrl(`/api/v1/presets/${refId.split(":")[1]}`, true);
    }
    return resolveApiUrl(`/api/v1/files/${encodeURIComponent(refId)}`, true);
  }, [displayedEntry, speakerAudio, presets]);

  const filteredHistory = useMemo(() => {
    const q = historyFilter.trim().toLowerCase();
    if (!q) return historyItems;
    return historyItems.filter(
      (item) =>
        item.params.text.toLowerCase().includes(q) ||
        String(item.result.seed).includes(q) ||
        item.result.language.toLowerCase().includes(q)
    );
  }, [historyItems, historyFilter]);

  const downloadTextFile = (content: string, filenameBase: string, ext: string) => {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${filenameBase.replace(/\.[^.]+$/, "")}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Stateless Built-in Scene Recipe Bar
  const topBanner = (
    <div className="studio-recipe-bar">
      <Space wrap size={[6, 6]}>
        <Text strong style={{ fontSize: 13, marginInlineEnd: 4 }}>
          <ThunderboltOutlined style={{ color: "var(--studio-accent)", marginInlineEnd: 4 }} />
          场景配方一键调优：
        </Text>
        {SCENE_RECIPES.map((recipe) => (
          <Tooltip key={recipe.id} title={recipe.desc}>
            <button
              type="button"
              className="studio-recipe-pill"
              data-active={activeRecipeId === recipe.id ? "true" : "false"}
              onClick={() => {
                applyPartialSettings(recipe.apply());
                setActiveRecipeId(recipe.id);
                if (recipe.id === "auto_drama" || recipe.id !== "natural_clone") {
                  scrollToSettings("emotion");
                }
                message.success(`已应用「${recipe.label}」推荐参数组合`);
              }}
            >
              {recipe.label}
            </button>
          </Tooltip>
        ))}
      </Space>
    </div>
  );

  // Polyphone / Pronunciation Annotator Popover Content
  const polyphonePopoverContent = (
    <div style={{ inlineSize: 330 }}>
      <Space direction="vertical" size={10} style={{ inlineSize: "100%" }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          在光标处插入 <Text code>&lt;字词|读音&gt;</Text> 精确控制多音字或外语音标：
        </Text>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: 8 }}>
          <div className="studio-field-group">
            <label htmlFor={polyWordId} style={{ fontSize: 12, fontWeight: 600 }}>
              目标字词
            </label>
            <Input
              id={polyWordId}
              size="small"
              placeholder="如：行 / 明日"
              value={polyWord}
              onChange={(e) => setPolyWord(e.target.value)}
            />
          </div>
          <div className="studio-field-group">
            <label htmlFor={polyPronId} style={{ fontSize: 12, fontWeight: 600 }}>
              拼音 / 音标 / 假名
            </label>
            <Input
              id={polyPronId}
              size="small"
              placeholder="如：XING2 / あした"
              value={polyPron}
              onChange={(e) => setPolyPron(e.target.value)}
              autoCorrect="off"
              autoCapitalize="characters"
              spellCheck={false}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  e.preventDefault();
                  insertAnnotationAtCursor(polyWord, polyPron);
                }
              }}
            />
          </div>
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11, display: "block", marginBlockEnd: 4 }}>
            常用多音字一键插入：
          </Text>
          <Space wrap size={[4, 4]}>
            {POLYPHONE_QUICK_CHIPS.map((chip) => (
              <Tooltip key={`${chip.word}-${chip.pron}`} title={chip.note}>
                <Button
                  htmlType="button"
                  size="small"
                  style={{ fontSize: 12, paddingInline: 7, blockSize: 24 }}
                  onClick={() => insertAnnotationAtCursor(chip.word, chip.pron)}
                >
                  {chip.word}·{chip.pron}
                </Button>
              </Tooltip>
            ))}
          </Space>
        </div>
        <Button
          htmlType="button"
          type="primary"
          size="small"
          block
          onClick={() => insertAnnotationAtCursor(polyWord, polyPron)}
        >
          插入到台词光标处
        </Button>
      </Space>
    </div>
  );

  const leftPane = (
    <form onSubmit={(e) => void handleGenerate(e)} style={{ display: "contents" }}>
      {/* Zone A: Speaker Voice Persona */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <SoundOutlined style={{ color: "var(--studio-accent)" }} />
            <span>1. 参考音色</span>
          </Space>
        }
        extra={
          <Space size={6} className="studio-tabular">
            <LabelWithTip
              label="参考截取上限"
              tip="IndexTTS-2.5 提取音色特征时读取的参考音频最大秒数（官方默认 15s，长参考音频可调高至 30s）"
            />
            <InputNumber
              size="small"
              min={3}
              max={30}
              step={1}
              value={maxRefSeconds}
              addonAfter="s"
              style={{ inlineSize: 88 }}
              onChange={(v) => setMaxRefSeconds(typeof v === "number" ? v : 15)}
            />
          </Space>
        }
      >
        <AudioSourceField
          label="目标说话人干声样本"
          hint="支持单段 3~15 秒清晰人声跨语种克隆中文、英语、日语、西语、阿语"
          value={speakerAudio}
          onChange={setSpeakerAudio}
          presets={presets}
          allowPreset
        />
      </Card>

      {/* Zone B: Script Studio & Primary Prosody */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <FontColorsOutlined style={{ color: "var(--studio-accent)" }} />
            <span>2. 台词与语速</span>
          </Space>
        }
        extra={
          <Space size={6} wrap>
            <Popover
              open={polyOpen}
              onOpenChange={(open) => {
                setPolyOpen(open);
                if (open) {
                  const textareaEl = textAreaWrapRef.current?.querySelector("textarea");
                  if (textareaEl && textareaEl.selectionStart !== textareaEl.selectionEnd) {
                    const selected = text.slice(textareaEl.selectionStart, textareaEl.selectionEnd).trim();
                    if (selected && selected.length <= 16) {
                      setPolyWord(selected);
                    }
                  }
                }
              }}
              trigger="click"
              placement="bottomRight"
              content={polyphonePopoverContent}
            >
              <Button htmlType="button" size="small" type="primary" ghost>
                + 插入多音字 / 音标标注
              </Button>
            </Popover>

            <Button
              htmlType="button"
              size="small"
              onClick={() => setShowSegmentPreview((v) => !v)}
            >
              <ScissorOutlined /> 预计分句 ({estimatedSegments.length} 段)
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
          <div className="studio-field-group" ref={textAreaWrapRef}>
            <div className="studio-field-label">
              <LabelWithTip
                htmlFor={textInputId}
                label="待合成剧本台词"
                tip="支持中文拼音如 <行|XING2>、英文 ARPAbet 音标如 <going|G OW1 . IH0 NG>、日文假名如 <明日|あした>"
              />
              <Space wrap size={[4, 4]}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  示例台词：
                </Text>
                {QUICK_TEXT_SAMPLES.map((sample) => (
                  <Button
                    key={sample.label}
                    htmlType="button"
                    size="small"
                    style={{ fontSize: 12, paddingInline: 8, blockSize: 24 }}
                    onClick={() => {
                      setText(sample.text);
                      setLanguage(sample.lang);
                    }}
                  >
                    {sample.label}
                  </Button>
                ))}
              </Space>
            </div>

            <TextArea
              id={textInputId}
              name="text"
              rows={4}
              maxLength={5000}
              showCount
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  e.preventDefault();
                  void handleGenerate();
                }
              }}
              placeholder="输入要合成的台词文本（选中文字后可点击右上角「插入多音字 / 音标标注」）..."
            />
          </div>

          {showSegmentPreview && estimatedSegments.length > 0 && (
            <div className="studio-segment-list">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <Text strong style={{ fontSize: 12 }}>
                  分句估算（每段上限 {maxTextTokensPerSegment} Tokens；实际切分以模型分词器为准）
                </Text>
                <Button
                  htmlType="button"
                  type="link"
                  size="small"
                  style={{ padding: 0, blockSize: "auto", fontSize: 12 }}
                  onClick={() => scrollToSettings("segment")}
                >
                  调整分句阈值
                </Button>
              </div>
              {estimatedSegments.map((seg, idx) => (
                <div key={idx} className="studio-segment-item studio-tabular">
                  <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                    #{idx + 1}
                  </Tag>
                  <span style={{ flex: 1 }}>{seg.text}</span>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    ~{seg.estTokens} tok
                  </Text>
                </div>
              ))}
            </div>
          )}

          {/* Primary Prosody Direct Bar */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "1rem",
              paddingTop: 4,
            }}
          >
            <div className="studio-field-group">
              <LabelWithTip
                label="目标合成语种"
                tip="支持跨语种音色迁移（例如用中文干声直接合成地道英语、日语、西语或阿语）"
              />
              <Select
                value={language}
                onChange={(val) => setLanguage(val as LanguageCode)}
                options={[
                  { value: "zh", label: "中文普通话 (ZH)" },
                  { value: "en", label: "English 英语 (EN)" },
                  { value: "ja", label: "日本語 日语 (JA)" },
                  { value: "es", label: "Español 西班牙语 (ES)" },
                  { value: "ar", label: "العربية 阿拉伯语 (AR)" },
                ]}
              />
            </div>

            <div className="studio-field-group studio-tabular">
              <div className="studio-field-label">
                <LabelWithTip
                  label="语速时长倍率 (duration_factor)"
                  tip="控制 S2Mel 长度调节器的目标帧长比例：<1.0 语速加快，1.0 标准原速，>1.0 语速放慢"
                />
                <Space size={4}>
                  <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                    {durationFactor.toFixed(2)}x
                  </Tag>
                  {Math.abs(durationFactor - 1.0) > 0.005 && (
                    <Button
                      htmlType="button"
                      type="link"
                      size="small"
                      style={{ padding: 0, blockSize: "auto", fontSize: 12 }}
                      onClick={() => setDurationFactor(1.0)}
                    >
                      重置
                    </Button>
                  )}
                </Space>
              </div>
              <Slider
                min={0.5}
                max={2.0}
                step={0.01}
                value={durationFactor}
                onChange={setDurationFactor}
              />
            </div>

            <div className="studio-field-group studio-tabular">
              <div className="studio-field-label">
                <LabelWithTip
                  label="句间停顿静音 (interval_silence)"
                  tip="长文本切分为多个片段时，片段之间插入的自然呼吸停顿毫秒数（默认 200ms）"
                />
                <Tag style={{ marginInlineEnd: 0 }}>{intervalSilenceMs} ms</Tag>
              </div>
              <Slider
                min={0}
                max={2000}
                step={25}
                value={intervalSilenceMs}
                onChange={setIntervalSilenceMs}
              />
            </div>
          </div>
        </Space>
      </Card>

      {/* Primary controls stay visible; only engine settings are collapsed. */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <SlidersOutlined style={{ color: "var(--studio-accent)" }} />
            <span>3. 情绪与生成参数</span>
          </Space>
        }
      >
        {[
            {
              key: "emotion",
              label: (
                <span>
                  <ExperimentOutlined /> 情感与表现力
                </span>
              ),
              children: (
                <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
                  <Segmented
                    block
                    options={[
                      { label: "沿用参考", value: "clone" },
                      { label: "情绪向量", value: "vector" },
                      { label: "参考情绪", value: "reference" },
                      { label: "文字描述", value: "text" },
                    ]}
                    value={emotionMode}
                    onChange={(val) => setEmotionMode(val as EmotionMode)}
                  />

                  {emotionMode === "clone" && (
                    <Alert
                      type="info"
                      showIcon
                      message="沿用说话人参考音频的语气；如需改变情绪，可切换到向量、参考音频或文字描述。"
                    />
                  )}

                  {emotionMode === "vector" && (
                    <Space direction="vertical" size={12} style={{ inlineSize: "100%" }}>
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 8,
                          padding: "0.55rem 0.8rem",
                          borderRadius: 8,
                          background: "var(--studio-surface-subtle)",
                          border: "1px solid var(--studio-border)",
                        }}
                      >
                        <Space wrap size={[6, 6]}>
                          <Text style={{ fontSize: 12, fontWeight: 600 }}>快捷情绪模板：</Text>
                          <Button
                            htmlType="button"
                            size="small"
                            onClick={() => setEmotionVector({ ...ZERO_EMO_VECTOR, happy: 0.8 })}
                          >
                            高兴愉悦
                          </Button>
                          <Button
                            htmlType="button"
                            size="small"
                            onClick={() => setEmotionVector({ ...ZERO_EMO_VECTOR, angry: 0.75 })}
                          >
                            愤怒质问
                          </Button>
                          <Button
                            htmlType="button"
                            size="small"
                            onClick={() =>
                              setEmotionVector({ ...ZERO_EMO_VECTOR, sad: 0.7, melancholic: 0.2 })
                            }
                          >
                            悲伤哭腔
                          </Button>
                          <Button
                            htmlType="button"
                            size="small"
                            onClick={() => setEmotionVector({ ...ZERO_EMO_VECTOR, melancholic: 0.8 })}
                          >
                            低落内敛
                          </Button>
                          <Button
                            htmlType="button"
                            size="small"
                            onClick={() => setEmotionVector({ ...ZERO_EMO_VECTOR, surprised: 0.85 })}
                          >
                            惊喜感叹
                          </Button>
                          <Button
                            htmlType="button"
                            size="small"
                            onClick={() => setEmotionVector({ ...ZERO_EMO_VECTOR, calm: 0.95 })}
                          >
                            沉稳平静
                          </Button>
                          <Button
                            htmlType="button"
                            size="small"
                            onClick={() => setEmotionVector({ ...ZERO_EMO_VECTOR })}
                          >
                            全部清零
                          </Button>
                        </Space>

                        <Space size={8} className="studio-tabular">
                          <Tooltip title="IndexTTS-2.5 官方建议 8 维情绪加权总和不超过 0.80，开启防破音保护会自动按比例缩放超限向量，防止音色失真">
                            <Tag color={emoStats.capped ? "warning" : "success"} style={{ marginInlineEnd: 0 }}>
                              原始和 {emoStats.rawSum.toFixed(2)} → 生效强度 {emoStats.effectiveSum.toFixed(2)}
                              {emoStats.capped ? " (已智能限幅 ≤0.8)" : ""}
                            </Tag>
                          </Tooltip>
                        </Space>
                      </div>

                      <div className="studio-emo-grid studio-tabular">
                        {EMO_DIMENSIONS.map((dim) => (
                          <div key={dim.key} className="studio-field-group">
                            <div className="studio-field-label">
                              <LabelWithTip label={`${dim.label} (${dim.en})`} tip={dim.tip} />
                              <Text code style={{ fontSize: 12 }}>
                                {emotionVector[dim.key].toFixed(2)}
                              </Text>
                            </div>
                            <Slider
                              min={0}
                              max={1}
                              step={0.01}
                              value={emotionVector[dim.key]}
                              onChange={(v) =>
                                setEmotionVector((prev) => ({ ...prev, [dim.key]: v }))
                              }
                            />
                          </div>
                        ))}
                      </div>

                      <Space wrap size={[20, 8]}>
                        <Space size={6}>
                          <Switch
                            size="small"
                            checked={normalizeEmoVector}
                            onChange={setNormalizeEmoVector}
                          />
                          <LabelWithTip
                            label="情绪总和防破音保护 (≤0.8)"
                            tip="开启后调用官方 normalize_emo_vec 将向量总和约束在 0.8 以内，避免负向抵消原说话人音色"
                          />
                        </Space>
                        <Space size={6}>
                          <Switch size="small" checked={applyEmoBias} onChange={setApplyEmoBias} />
                          <LabelWithTip
                            label="官方听感偏置校正 (apply_bias)"
                            tip="对惊讶、愤怒等易过激维度施加官方经验系数校正，使合成听感更自然"
                          />
                        </Space>
                        <Space size={6}>
                          <Switch size="small" checked={useRandom} onChange={setUseRandom} />
                          <LabelWithTip
                            label="随机情感说话人基底 (use_random)"
                            tip="默认按余弦相似度检索最匹配音色的情感特征；开启后随机抽取特征以增加演绎变化"
                          />
                        </Space>
                      </Space>
                    </Space>
                  )}

                  {emotionMode === "reference" && (
                    <AudioSourceField
                      label="第二段情感参考音频（音色与情绪解耦迁移）"
                      hint="保留第 1 步音频的说话人音色，提取并迁移此段参考音频的情绪起伏"
                      value={emotionAudio}
                      onChange={setEmotionAudio}
                      presets={presets}
                      allowPreset
                    />
                  )}

                  {emotionMode === "text" && (
                    <Space direction="vertical" size={10} style={{ inlineSize: "100%" }}>
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 8,
                        }}
                      >
                        <Space size={8}>
                          <Switch
                            checked={autoEmotionFromText}
                            onChange={setAutoEmotionFromText}
                          />
                          <LabelWithTip
                            label="直接根据合成台词文本自动推理情绪"
                            tip="开启后无需手写情绪词，QwenEmotion (qwen0.6bemo4-merge) 会直接阅读上方台词自动生成 8 维情绪权重"
                          />
                        </Space>
                        <Space size={6}>
                          <Switch size="small" checked={useRandom} onChange={setUseRandom} />
                          <Text style={{ fontSize: 13 }}>随机情感特征微调</Text>
                        </Space>
                      </div>

                      {!autoEmotionFromText && (
                        <div className="studio-field-group">
                          <div className="studio-field-label">
                            <label htmlFor={emoTextInputId}>自定义自然语言情绪描述词</label>
                            <span className="studio-field-hint">
                              支持中文或英文描述语气、心理状态或场景氛围
                            </span>
                          </div>
                          <Input
                            id={emoTextInputId}
                            name="emotion_text"
                            value={emotionText}
                            onChange={(e) => setEmotionText(e.target.value)}
                            placeholder="例如：委屈巴巴地低声倾诉 / 激动兴奋地宣布好消息"
                          />
                          <Space wrap size={[6, 6]} style={{ marginBlockStart: 2 }}>
                            {EMO_TEXT_EXAMPLES.map((ex) => (
                              <Button
                                key={ex}
                                htmlType="button"
                                size="small"
                                onClick={() => setEmotionText(ex)}
                              >
                                {ex}
                              </Button>
                            ))}
                          </Space>
                        </div>
                      )}
                    </Space>
                  )}

                  {emotionMode !== "clone" && (
                    <div className="studio-field-group studio-tabular">
                      <div className="studio-field-label">
                        <LabelWithTip
                          label="情感融合强度权重 (emo_alpha)"
                          tip="0.0 表示完全保持原参考音频平淡语气，1.0 表示最大化应用所选情绪表现"
                        />
                        <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                          {emoAlpha.toFixed(2)}
                        </Tag>
                      </div>
                      <Slider min={0} max={1} step={0.01} value={emoAlpha} onChange={setEmoAlpha} />
                    </div>
                  )}
                </Space>
              ),
            },
            {
              key: "segment",
              label: (
                <span>
                  <ScissorOutlined /> 分句与文本处理
                </span>
              ),
              children: (
                <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
                  <div className="studio-param-grid studio-tabular">
                    <div className="studio-field-group">
                      <div className="studio-field-label">
                        <LabelWithTip
                          label="单段最大文本 Token 数"
                          tip="官方建议 80~200。数值越小分句越细（适合短促口播与低显存），数值越大跨句连贯感越强"
                        />
                        <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                          {maxTextTokensPerSegment} tokens
                        </Tag>
                      </div>
                      <Slider
                        min={20}
                        max={200}
                        step={2}
                        value={maxTextTokensPerSegment}
                        onChange={setMaxTextTokensPerSegment}
                        marks={{ 20: "20", 80: "80", 120: "120(默认)", 200: "200" }}
                      />
                    </div>

                  </div>

                  <Divider style={{ marginBlock: 2 }} />

                  <Space wrap size={[24, 10]}>
                    <Space size={8}>
                      <Switch checked={textNormalization} onChange={setTextNormalization} />
                      <LabelWithTip
                        label="启用智能文本正则化 (Text Normalization)"
                        tip="自动将阿拉伯数字、年份、百分比、货币符号（如 2026年、99.5%）展开为自然口语读法；若台词已手工转写为纯汉字/纯单词可关闭"
                      />
                    </Space>
                  </Space>
                </Space>
              ),
            },
            {
              key: "sampling",
              label: (
                <span>
                  <ControlOutlined /> GPT2 与 CFM 声学采样
                </span>
              ),
              children: (
                <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                    <Space size={8}>
                      <Switch size="small" checked={doSample} onChange={setDoSample} />
                      <LabelWithTip
                        label="启用 GPT2 随机核采样 (do_sample)"
                        tip="开启后结合 Temperature / Top-P / Top-K 生成丰富自然抑扬顿挫；关闭则仅按 Beam Search 确定性解码"
                      />
                    </Space>
                    <Button htmlType="button" size="small" icon={<ReloadOutlined />} onClick={resetSamplingDefaults}>
                      恢复推荐采样默认值
                    </Button>
                  </div>

                  <div className="studio-param-grid studio-tabular">
                    <div className="studio-field-group">
                      <div className="studio-field-label">
                        <LabelWithTip
                          label="采样温度 (temperature)"
                          tip="控制 GPT2 语义编码多样性：0.6~0.75 更稳健克制，0.8~1.0 语气更灵动富有表现力"
                        />
                        <Text code>{temperature.toFixed(2)}</Text>
                      </div>
                      <Slider min={0.1} max={2.0} step={0.05} value={temperature} onChange={setTemperature} disabled={!doSample} />
                    </div>

                    <div className="studio-field-group">
                      <div className="studio-field-label">
                        <LabelWithTip
                          label="核采样阈值 (top_p)"
                          tip="仅在累积概率达到 top_p 的高置信候选集合中采样（默认 0.80）"
                        />
                        <Text code>{topP.toFixed(2)}</Text>
                      </div>
                      <Slider min={0.05} max={1.0} step={0.01} value={topP} onChange={setTopP} disabled={!doSample} />
                    </div>

                    <div className="studio-field-group">
                      <div className="studio-field-label">
                        <LabelWithTip
                          label="S2Mel 扩散步数 (CFM Steps)"
                          tip="流匹配声学解码器迭代步数：默认 25 步；调高至 32~45 步音质细节更细腻纯净，调低至 15~20 步推理更快"
                        />
                        <Tag color="blue" style={{ marginInlineEnd: 0 }}>{diffusionSteps} 步</Tag>
                      </div>
                      <Slider min={10} max={50} step={1} value={diffusionSteps} onChange={setDiffusionSteps} />
                    </div>

                    <div className="studio-field-group">
                      <div className="studio-field-label">
                        <LabelWithTip
                          label="音色引导强度 (CFG Rate)"
                          tip="S2Mel 无分类器引导强度（默认 0.70）：调高（0.8~1.1）音色更贴近参考人声，调低（0.4~0.6）咬字更松弛"
                        />
                        <Text code>{inferenceCfgRate.toFixed(2)}</Text>
                      </div>
                      <Slider min={0.0} max={1.5} step={0.05} value={inferenceCfgRate} onChange={setInferenceCfgRate} />
                    </div>

                    <div className="studio-field-group">
                      <LabelWithTip label="Top-K 候选数 (0=不限)" tip="每步仅保留概率最高的 K 个语义 Token（默认 30，设为 0 则关闭 Top-K 截断）" />
                      <InputNumber
                        style={{ inlineSize: "100%" }}
                        min={0}
                        max={100}
                        step={1}
                        value={topK}
                        disabled={!doSample}
                        onChange={(v) => setTopK(typeof v === "number" ? v : 30)}
                      />
                    </div>

                    <div className="studio-field-group">
                      <LabelWithTip label="束搜索宽度 (num_beams)" tip="Beam Search 并行候选路径数（默认 3；设为 1 可加快长文本生成速度）" />
                      <InputNumber
                        style={{ inlineSize: "100%" }}
                        min={1}
                        max={10}
                        step={1}
                        value={numBeams}
                        onChange={(v) => setNumBeams(typeof v === "number" ? v : 3)}
                      />
                    </div>

                    <div className="studio-field-group">
                      <LabelWithTip label="重复惩罚 (repetition_penalty)" tip="抑制 GPT2 卡顿复读或异常拖长音（IndexTTS-2.5 官方默认 10.0）" />
                      <InputNumber
                        style={{ inlineSize: "100%" }}
                        min={0.1}
                        max={20.0}
                        step={0.5}
                        value={repetitionPenalty}
                        onChange={(v) => setRepetitionPenalty(typeof v === "number" ? v : 10.0)}
                      />
                    </div>

                    <div className="studio-field-group">
                      <LabelWithTip label="长度惩罚 (length_penalty)" tip="Beam Search 序列长度偏好：正值鼓励更长语音，负值鼓励简短收尾（默认 0.0）" />
                      <InputNumber
                        style={{ inlineSize: "100%" }}
                        min={-2.0}
                        max={2.0}
                        step={0.1}
                        value={lengthPenalty}
                        onChange={(v) => setLengthPenalty(typeof v === "number" ? v : 0.0)}
                      />
                    </div>

                    <div className="studio-field-group">
                      <LabelWithTip label="单段最大 Mel Tokens" tip="单个分句允许生成的最大声学 Token 上限（默认 1500，过小会导致单句尾部被截断）" />
                      <InputNumber
                        style={{ inlineSize: "100%" }}
                        min={50}
                        max={1815}
                        step={25}
                        value={maxMelTokens}
                        onChange={(v) => setMaxMelTokens(typeof v === "number" ? v : 1500)}
                      />
                    </div>
                  </div>
                </Space>
              ),
            },
            {
              key: "mastering",
              label: (
                <span>
                  <SoundOutlined /> 音频后处理
                </span>
              ),
              children: (
                <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
                  <div className="studio-param-grid studio-tabular">
                    <div className="studio-field-group">
                      <div className="studio-field-label">
                        <LabelWithTip
                          label="额外句尾平滑淡出 (tail_fade_ms)"
                          tip="除模型内置防爆音保护外，额外对结尾施加余弦平滑淡出（0~500ms）"
                        />
                        <Tag style={{ marginInlineEnd: 0 }}>{tailFadeMs} ms</Tag>
                      </div>
                      <Slider min={0} max={500} step={10} value={tailFadeMs} onChange={setTailFadeMs} />
                    </div>
                  </div>

                  <Space wrap size={[22, 10]}>
                    <Space size={6}>
                      <Switch size="small" checked={loudnessNorm} onChange={setLoudnessNorm} />
                      <LabelWithTip
                        label="响度标准化 (-16 LUFS)"
                        tip="使用 FFmpeg EBU R128 广播标准均衡响度并限制真峰值 -1.5 dBTP，多条配音音量高度统一"
                      />
                    </Space>
                    <Space size={6}>
                      <Switch size="small" checked={trimSilence} onChange={setTrimSilence} />
                      <LabelWithTip
                        label="自动裁剪首尾静音"
                        tip="自动检测并切除音频起止处低于 -43 dBFS 的多余空白，方便直接拖入剪辑时间线"
                      />
                    </Space>
                  </Space>

                  <details className="studio-native-details">
                    <summary>引擎与显存设置</summary>
                    <div className="studio-details-body">
                  <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                    <Space wrap size={[20, 8]}>
                      <Space size={6}>
                        <Switch size="small" checked={useBf16} onChange={setUseBf16} />
                        <LabelWithTip label="BF16 混合精度加速" tip="在 A100/H100/L4 等显卡上大幅提速并降低显存占用" />
                      </Space>
                      <Space size={6}>
                        <Switch size="small" checked={useTorchCompile} onChange={setUseTorchCompile} />
                        <LabelWithTip
                          label="s2mel torch.compile"
                          tip="开启 PyTorch 图编译优化；首次合成需数十秒编译，后续批量合成速度显著提升"
                        />
                      </Space>
                      <Space size={6}>
                        <Switch size="small" checked={useCudaKernel} onChange={setUseCudaKernel} />
                        <LabelWithTip label="BigVGAN CUDA 算子" tip="当环境已编译自定义激活算子时启用底层加速，未安装时自动安全回退" />
                      </Space>
                      <Space size={6}>
                        <Switch size="small" checked={autoFreeMemory} onChange={setAutoFreeMemory} />
                        <LabelWithTip label="单次完成后自动卸载显存" tip="连续创作请保持关闭以免重复读盘加载权重" />
                      </Space>
                    </Space>

                    <Button
                      htmlType="button"
                      size="small"
                      loading={releasingVram}
                      disabled={isBusy}
                      onClick={async () => {
                        setReleasingVram(true);
                        try {
                          const res = await triggerModelRelease();
                          message.success(`已释放显存模型缓存（共卸载 ${res.released_instances ?? 0} 个实例）`);
                        } catch (err) {
                          message.error(err instanceof Error ? err.message : "释放显存失败");
                        } finally {
                          setReleasingVram(false);
                        }
                      }}
                    >
                      立即手动清空显存
                    </Button>
                  </div>
                      <Button
                        htmlType="button"
                        size="small"
                        onClick={() => {
                          setUseBf16(true);
                          setUseTorchCompile(false);
                          setUseCudaKernel(false);
                          setAutoFreeMemory(false);
                        }}
                      >
                        恢复推荐引擎设置
                      </Button>
                    </div>
                  </details>
                </Space>
              ),
            },
          ].map((section, index) => (
            <section
              key={section.key}
              id={`${settingsSectionId}-${section.key}`}
              style={{ scrollMarginTop: 100, paddingBlockStart: index ? 20 : 0, marginBlockStart: index ? 20 : 0, borderBlockStart: index ? "1px solid var(--studio-border)" : undefined }}
            >
              <h3 style={{ fontSize: 14, marginBlock: "0 14px" }}>{section.label}</h3>
              {section.children}
            </section>
          ))}
      </Card>

      {/* Zone D: Sticky Primary Generate Dock (Always Visible in Viewport!) */}
      <div className="studio-action-dock">
        <Space wrap size={[10, 6]} className="studio-tabular">
          <Space size={6}>
            <Tooltip title={seed > 0 ? "已锁定种子，便于使用相同参数再次生成" : "0 表示每次随机生成新种子"}>
              {seed > 0 ? (
                <LockOutlined style={{ color: "var(--studio-accent)" }} />
              ) : (
                <UnlockOutlined style={{ color: "var(--studio-text-muted)" }} />
              )}
            </Tooltip>
            <Text style={{ fontSize: 13, fontWeight: 500 }}>Seed:</Text>
            <InputNumber
              size="small"
              min={0}
              max={2147483647}
              precision={0}
              value={seed}
              style={{ inlineSize: 125 }}
              onChange={(v) => setSeed(typeof v === "number" ? v : 0)}
            />
            {seed > 0 && (
              <Button
                htmlType="button"
                size="small"
                type="link"
                style={{ paddingInline: 4 }}
                onClick={() => setSeed(0)}
              >
                改回随机
              </Button>
            )}
          </Space>

          <Divider type="vertical" />

          <Space size={4}>
            <Text type="secondary" style={{ fontSize: 12 }}>格式:</Text>
            <Segmented
              size="small"
              options={[
                { label: "MP3", value: "mp3" },
                { label: "WAV", value: "wav" },
                { label: "FLAC", value: "flac" },
              ]}
              value={outputFormat}
              onChange={(val) => setOutputFormat(val as OutputFormat)}
            />
          </Space>
        </Space>

        <Space size={10}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            快捷键 ⌘ / Ctrl + Enter
          </Text>
          <Button
            htmlType="submit"
            type="primary"
            size="large"
            icon={<RocketOutlined />}
            loading={isBusy}
            style={{ paddingInline: 28, fontWeight: 600 }}
          >
            {isBusy ? "正在合成语音..." : "开始合成语音"}
          </Button>
        </Space>
      </div>
    </form>
  );

  const rightPane = (
    <>
      {activeTask && (activeTask.status === "queued" || activeTask.status === "running") && (
        <Card className="studio-card" title="实时推理进度">
          <Space direction="vertical" size={10} style={{ inlineSize: "100%" }}>
            <Progress percent={Math.round(activeTask.progress * 100)} status="active" />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Text type="secondary">{activeTask.stage || "模型推理处理中..."}</Text>
              {activeTask.status === "queued" && (
                <Button htmlType="button" size="small" danger onClick={() => void cancelActive()}>
                  取消排队
                </Button>
              )}
            </div>
          </Space>
        </Card>
      )}

      {activeTask?.status === "failed" && activeTask.error && (
        <Alert
          type="error"
          showIcon
          closable
          message="语音合成任务未成功完成"
          description={activeTask.error}
        />
      )}

      {/* Zone E: Audition, A/B Voice Compare & Interactive Subtitle Stage */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <PlayCircleOutlined style={{ color: "var(--studio-accent)" }} />
            <span>试听母带与 A/B 音色对比</span>
          </Space>
        }
        extra={
          displayedEntry && (
            <Space size={6}>
              <Button
                htmlType="button"
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => applyParamsFromHistory(displayedEntry)}
              >
                回填参数
              </Button>
              <Button
                htmlType="button"
                type="primary"
                size="small"
                icon={<DownloadOutlined />}
                href={resolveApiUrl(displayedEntry.result.download_url, true)}
                target="_blank"
                rel="noreferrer"
              >
                下载 {displayedEntry.result.format.toUpperCase()}
              </Button>
            </Space>
          )
        }
      >
        {displayedEntry ? (
          <Space direction="vertical" size={12} style={{ inlineSize: "100%" }}>
            {/* A/B Audition Switcher */}
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <Segmented
                size="small"
                options={[
                  { label: "🔊 试听合成结果", value: "synth" },
                  { label: "🎙️ A/B 对比原参考音色", value: "ref" },
                ]}
                value={auditionSource}
                onChange={(v) => setAuditionSource(v as "synth" | "ref")}
              />
              {auditionSource === "ref" && (
                <Tag icon={<SwapOutlined />} color="processing" style={{ marginInlineEnd: 0 }}>
                  正在播放克隆源参考人声
                </Tag>
              )}
            </div>

            <audio
              ref={audioPlayerRef}
              key={
                auditionSource === "synth"
                  ? displayedEntry.result.audio_url
                  : `ref_${referenceCompareUrl}`
              }
              className="studio-audio-player"
              controls
              autoPlay={auditionSource === "synth" && activeTask?.task_id === displayedEntry.id}
              src={
                auditionSource === "synth"
                  ? resolveApiUrl(displayedEntry.result.audio_url, true)
                  : referenceCompareUrl
              }
              onLoadedMetadata={() => {
                if (auditionSource === "synth" && pendingSeekRef.current !== null) seekSynthAudio(pendingSeekRef.current);
              }}
            />

            {/* Telemetry Metadata Badges */}
            <Space wrap size={[6, 6]} className="studio-tabular">
              <Tag color="success">{displayedEntry.result.duration_sec}s</Tag>
              <Tag color="processing">{displayedEntry.result.sample_rate} Hz</Tag>
              <Tag>{displayedEntry.result.format.toUpperCase()}</Tag>
              <Tag>{EMO_MODE_LABELS[displayedEntry.result.emotion_mode]}</Tag>
              <Tag>{displayedEntry.result.language.toUpperCase()}</Tag>
              {displayedEntry.result.segments_count != null && (
                <Tag>约 {displayedEntry.result.segments_count} 段</Tag>
              )}
              {displayedEntry.result.rtf != null && (
                <Tooltip title="Real-Time Factor 实时率（越小表示生成速度越快）">
                  <Tag>RTF {displayedEntry.result.rtf}</Tag>
                </Tooltip>
              )}
              <Tooltip title="点击将此 Seed 锁定到下方生成栏，便于固定语气微调其他参数">
                <Tag
                  icon={<LockOutlined />}
                  color="blue"
                  style={{ cursor: "pointer", marginInlineEnd: 0 }}
                  onClick={() => {
                    setSeed(displayedEntry.result.seed);
                    message.success(`已锁定 Seed: ${displayedEntry.result.seed}`);
                  }}
                >
                  Seed: {displayedEntry.result.seed}
                </Tag>
              </Tooltip>
            </Space>

            {/* Interactive Timeline & Subtitle Export */}
            <div className="studio-field-group">
              <div className="studio-field-label">
                <Segmented
                  size="small"
                  options={[
                    { label: "估算时间轴", value: "timeline" },
                    { label: "SRT 字幕", value: "srt" },
                    { label: "WebVTT", value: "vtt" },
                  ]}
                  value={subtitleViewMode}
                  onChange={(v) => setSubtitleViewMode(v as "timeline" | "srt" | "vtt")}
                />
                <Space size={4}>
                  <Button
                    htmlType="button"
                    size="small"
                    type="text"
                    icon={<CopyOutlined />}
                    onClick={async () => {
                      const raw =
                        subtitleViewMode === "vtt" && displayedEntry.result.vtt
                          ? displayedEntry.result.vtt
                          : displayedEntry.result.srt;
                      try {
                        await navigator.clipboard.writeText(raw);
                        message.success(`已复制 ${subtitleViewMode === "vtt" ? "WebVTT" : "SRT"} 字幕`);
                      } catch {
                        message.error("复制失败，请使用字幕下载按钮");
                      }
                    }}
                  >
                    复制
                  </Button>
                  <Button
                    htmlType="button"
                    size="small"
                    type="text"
                    icon={<DownloadOutlined />}
                    onClick={() =>
                      downloadTextFile(
                        displayedEntry.result.srt,
                        displayedEntry.result.filename,
                        "srt"
                      )
                    }
                  >
                    .srt
                  </Button>
                  {displayedEntry.result.vtt && (
                    <Button
                      htmlType="button"
                      size="small"
                      type="text"
                      icon={<DownloadOutlined />}
                      onClick={() =>
                        downloadTextFile(
                          displayedEntry.result.vtt || "",
                          displayedEntry.result.filename,
                          "vtt"
                        )
                      }
                    >
                      .vtt
                    </Button>
                  )}
                </Space>
              </div>

              <Text type="secondary" style={{ fontSize: 12 }}>
                字幕时间按文本长度估算，未做语音对齐；精确剪辑前请试听校准。
              </Text>
              {subtitleViewMode === "timeline" && displayedEntry.result.timeline?.length ? (
                <div className="studio-timeline-list studio-tabular">
                  {displayedEntry.result.timeline.map((row) => (
                    <div
                      key={row.index}
                      className="studio-timeline-row"
                      role="button"
                      tabIndex={0}
                      onClick={() => seekSynthAudio(row.start_sec)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          seekSynthAudio(row.start_sec);
                        }
                      }}
                    >
                      <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                        {row.start_sec.toFixed(2)}s
                      </Tag>
                      <span style={{ fontSize: 13, color: "var(--studio-text)" }}>{row.text}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <pre className="studio-code-block" style={{ maxBlockSize: 190 }}>
                  {subtitleViewMode === "vtt" && displayedEntry.result.vtt
                    ? displayedEntry.result.vtt
                    : displayedEntry.result.srt || displayedEntry.result.subtitle}
                </pre>
              )}
            </div>
          </Space>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="配置左侧音色与台词后点击底部「开始合成语音」，此处可实时试听、A/B 对比原声并导出时间轴字幕"
          />
        )}
      </Card>

      {/* Zone F: Searchable Local Takes History */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <HistoryOutlined style={{ color: "var(--studio-accent)" }} />
            <span>本地生成作品库 ({historyItems.length})</span>
          </Space>
        }
        extra={
          historyItems.length > 0 && (
            <Popconfirm
              title="确定清空所有本地历史生成记录吗？"
              onConfirm={clearAll}
              okText="确认清空"
              cancelText="取消"
            >
              <Button htmlType="button" size="small" danger type="text" icon={<ClearOutlined />}>
                清空
              </Button>
            </Popconfirm>
          )
        }
      >
        {historyItems.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无历史生成记录" />
        ) : (
          <Space direction="vertical" size={10} style={{ inlineSize: "100%" }}>
            {historyItems.length > 2 && (
              <Input
                size="small"
                allowClear
                prefix={<SearchOutlined style={{ color: "var(--studio-text-muted)" }} />}
                placeholder="搜索历史台词关键词、语种或 Seed..."
                value={historyFilter}
                onChange={(e) => setHistoryFilter(e.target.value)}
              />
            )}

            <div className="studio-scroll-panel">
              <Space direction="vertical" size={8} style={{ inlineSize: "100%" }}>
                {filteredHistory.map((item) => {
                  const isSelected = displayedEntry?.id === item.id;
                  return (
                    <div
                      key={item.id}
                      className="studio-history-item"
                      data-active={isSelected ? "true" : "false"}
                    >
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 8,
                        }}
                      >
                        <Space wrap size={[5, 4]} className="studio-tabular">
                          <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                            {EMO_MODE_LABELS[item.result.emotion_mode] || item.result.emotion_mode}
                          </Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {item.result.duration_sec}s · {item.result.language.toUpperCase()} ·{" "}
                            {item.result.format.toUpperCase()}
                          </Text>
                        </Space>
                        <Space size={2}>
                          <Button
                            htmlType="button"
                            size="small"
                            type={isSelected ? "primary" : "default"}
                            onClick={() => {
                              setSelectedHistoryId(item.id);
                              setAuditionSource("synth");
                            }}
                          >
                            试听
                          </Button>
                          <Tooltip title="一键回填该条记录的全部参数">
                            <Button
                              htmlType="button"
                              size="small"
                              type="text"
                              icon={<ReloadOutlined />}
                              onClick={() => applyParamsFromHistory(item)}
                            />
                          </Tooltip>
                          <Tooltip title="删除记录">
                            <Button
                              htmlType="button"
                              size="small"
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={() => removeEntry(item.id)}
                            />
                          </Tooltip>
                        </Space>
                      </div>
                      <Text
                        ellipsis={{ tooltip: item.params.text }}
                        style={{ fontSize: 13, color: "var(--studio-text-secondary)" }}
                      >
                        {item.params.text}
                      </Text>
                    </div>
                  );
                })}
              </Space>
            </div>
          </Space>
        )}
      </Card>
    </>
  );

  return (
    <StudioShell
      brandBadge="TTS"
      defaultTitle="IndexTTS 2.5 语音合成工作台"
      defaultSubtitle="多语种音色克隆 · 情绪控制 · 音频与字幕导出"
      apiEndpointPath="/api/v1/generate"
      sampleRequestBody={currentPayload as unknown as Record<string, unknown>}
      topBanner={topBanner}
      leftPane={leftPane}
      rightPane={rightPane}
      onAuthChanged={refreshPresets}
    />
  );
}
