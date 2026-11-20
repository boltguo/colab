import {
  Alert,
  AudioSourceField,
  Button,
  Card,
  DeleteOutlined,
  DownloadOutlined,
  Empty,
  GenerateButton,
  HistoryOutlined,
  Kbd,
  List,
  ListItem,
  PlayCircleOutlined,
  Popconfirm,
  Progress,
  ReloadOutlined,
  ScrollArea,
  Segmented,
  Select,
  Slider,
  SoundOutlined,
  Space,
  StudioShell,
  Tag,
  Text,
  TextArea,
  Tooltip,
  fetchPresets,
  resolveApiUrl,
  useHistoryStore,
  useStudioFeedback,
  useStudioLocale,
  useTaskRunner,
  type HistoryEntry,
  type PresetItem,
} from "@colab/shared";
import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import { DEFAULT_FORM, EXAMPLE_TEXT, buildTtsRequest, defaultPresetForLanguage, restoreTtsForm, switchTtsLanguage } from "./request";
import "./studio.css";
import type { IndexTTSRequestPayload, IndexTTSResult, LanguageCode, OutputFormat, TtsForm } from "./types";

type TtsEntry = HistoryEntry<IndexTTSResult, IndexTTSRequestPayload>;

const EN_PRESET_LABELS: Record<string, { label: string; description: string }> = {
  "preset:ref_audio": {
    label: "Sage · Built-in Voice",
    description: "Sage reference voice (~8.9s) for zero-shot cloning or cross-lingual speech.",
  },
  "preset:ref_audio_ja": {
    label: "Japanese · Built-in Voice",
    description: "Japanese sample voice (~6.8s) for Japanese synthesis and cross-lingual cloning.",
  },
};

export function IndexTTSStudioApp() {
  const { locale, isZh, t } = useStudioLocale();
  const { message } = useStudioFeedback();
  const [form, setForm] = useState<TtsForm>({ ...DEFAULT_FORM });
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [auditionSource, setAuditionSource] = useState<"synth" | "ref">("synth");
  const textId = useId();
  const languageId = useId();
  const outputFormatId = useId();
  const emotionTextId = useId();
  const { items: history, addEntry, clearAll } = useHistoryStore<IndexTTSResult, IndexTTSRequestPayload>("indextts-2.5", 30);

  const update = <Key extends keyof TtsForm>(key: Key, value: TtsForm[Key]) => {
    setForm((previous) => ({ ...previous, [key]: value }));
  };
  const refreshPresets = useCallback(() => {
    void fetchPresets().then(setPresets).catch(() => setPresets([]));
  }, []);
  useEffect(refreshPresets, [refreshPresets]);

  const localizedPresets = useMemo(
    () =>
      presets.map((preset) => {
        if (isZh) return preset;
        const localized = EN_PRESET_LABELS[preset.id];
        return localized ? { ...preset, ...localized } : preset;
      }),
    [isZh, presets],
  );

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<IndexTTSResult, IndexTTSRequestPayload>({
    onSuccess: (task) => {
      if (!task.result) return;
      addEntry({
        id: task.task_id,
        feature: "indextts-2.5",
        createdAt: task.finished_at || task.created_at,
        elapsedSec: task.elapsed_sec,
        params: task.params,
        result: task.result,
      });
      setSelectedId(task.task_id);
      setAuditionSource("synth");
      message.success(t("Speech generated — ready to preview or download", "语音已生成，可以试听或下载"));
    },
    onError: (error) => message.error(error),
  });
  const payload = useMemo(() => buildTtsRequest(form), [form]);
  const displayed = history.find((item) => item.id === selectedId) || history[0] || null;
  const referenceId = displayed?.params.speaker_audio || form.speakerAudio;
  const referenceUrl = referenceId.startsWith("preset:")
    ? resolveApiUrl(presets.find((preset) => preset.id === referenceId)?.url || `/api/v1/presets/${encodeURIComponent(referenceId.slice(7))}`, true)
    : resolveApiUrl(`/api/v1/files/${encodeURIComponent(referenceId)}`, true);

  const generate = async (event?: React.FormEvent) => {
    event?.preventDefault();
    if (isBusy) return;
    if (!form.text.trim()) {
      message.warning(t("Please enter text to synthesize.", "请输入要合成的文本"));
      return;
    }
    if (!form.speakerAudio) {
      message.warning(t("Please select a reference voice.", "请选择参考音色"));
      return;
    }
    if (form.emotionMode === "reference" && !form.emotionAudio) {
      message.warning(t("Please upload an emotion reference audio clip.", "请上传用于参考情绪的音频"));
      return;
    }
    await runTask(payload);
  };
  const reuse = (entry: TtsEntry) => {
    setForm(restoreTtsForm(entry.params));
    setSelectedId(entry.id);
    setAuditionSource("synth");
    message.success(t("Loaded text and settings from history", "已填入这次生成的文本和常用设置"));
  };

  const leftPane = (
    <form onSubmit={(event) => void generate(event)} className="tts-form">
      <Card className="studio-card" title={<Space size={8}><SoundOutlined /><span>{t("Reference Voice", "参考音色")}</span></Space>}>
        <AudioSourceField
          label={t("Select a reference voice", "选择一段参考人声")}
          hint={t("Use a built-in voice, upload a file, or record your own", "使用内置音色，也可以上传或录制自己的声音")}
          value={form.speakerAudio}
          defaultPresetId={defaultPresetForLanguage(form.language)}
          onChange={(value) => update("speakerAudio", value)}
          presets={localizedPresets}
          allowPreset
        />
      </Card>

      <Card
        className="studio-card"
        title={t("Speech Text", "合成文本")}
        extra={
          <Button type="text" size="small" onClick={() => update("text", EXAMPLE_TEXT[form.language])}>
            {t("Insert Example", "填入示例")}
          </Button>
        }
      >
        <div className="tts-stack">
          <div className="studio-field-group">
            <label className="studio-visually-hidden" htmlFor={textId}>
              {t("Text to synthesize", "要合成的文本")}
            </label>
            <TextArea
              id={textId}
              aria-label={t("Text to synthesize", "要合成的文本")}
              rows={6}
              maxLength={5000}
              value={form.text}
              placeholder={t("Enter what you want the voice to say…", "输入你希望说出的内容……")}
              onValueChange={(value) => update("text", value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                  event.preventDefault();
                  void generate();
                }
              }}
            />
            <div className="tts-text-footer">
              <span className="studio-shortcut-hint">
                <Kbd keys={["mod", "enter"]} size="sm" />
                <span>{t("Generate", "生成")}</span>
              </span>
              <span>{form.text.length} / 5000</span>
            </div>
          </div>
          <div className="tts-main-settings">
            <div className="studio-field-group">
              <div className="tts-control-heading">
                <label htmlFor={languageId}>{t("Language", "语言")}</label>
              </div>
              <div className="tts-control-body">
                <Select
                  id={languageId}
                  aria-label={t("Speech language", "合成语言")}
                  value={form.language}
                  onChange={(value) => setForm((previous) => switchTtsLanguage(previous, value as LanguageCode))}
                  options={[
                    { label: "中文", value: "zh" },
                    { label: "English", value: "en" },
                    { label: "日本語", value: "ja" },
                    { label: "Español", value: "es" },
                    { label: "العربية", value: "ar" },
                  ]}
                />
              </div>
            </div>
            <div className="studio-field-group">
              <div className="tts-control-heading">
                <label htmlFor={outputFormatId}>{t("Output Format", "输出格式")}</label>
              </div>
              <div className="tts-control-body">
                <Select
                  id={outputFormatId}
                  aria-label={t("Output format", "输出格式")}
                  value={form.outputFormat}
                  onChange={(value) => update("outputFormat", value as OutputFormat)}
                  options={[
                    { label: "MP3", value: "mp3" },
                    { label: "WAV", value: "wav" },
                    { label: "FLAC", value: "flac" },
                  ]}
                />
              </div>
            </div>
            <div className="studio-field-group tts-speed-field">
              <div className="tts-control-heading">
                <span>{t("Speed", "语速")}</span>
                <Space size={6}>
                  <span className="studio-tabular">{t(`${form.speed.toFixed(2)}x`, `${form.speed.toFixed(2)} 倍`)}</span>
                  <Tooltip title={t("Reset speed to 1.0x", "恢复正常语速")}>
                    <Button
                      type="text"
                      size="small"
                      icon={<ReloadOutlined />}
                      aria-label={t("Reset speed to 1.0x", "恢复正常语速")}
                      disabled={form.speed === 1}
                      onClick={() => update("speed", 1)}
                    />
                  </Tooltip>
                </Space>
              </div>
              <div className="tts-control-body">
                <Slider
                  aria-label={t("Speaking speed", "语速")}
                  min={0.5}
                  max={2}
                  step={0.05}
                  value={form.speed}
                  onChange={(value) => update("speed", value)}
                />
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card className="studio-card" title={t("Emotion", "情绪")}>
        <div className="tts-stack">
          <Segmented
            block
            aria-label={t("Emotion mode", "情绪方式")}
            value={form.emotionMode}
            onChange={(value) => update("emotionMode", value as TtsForm["emotionMode"])}
            options={[
              { label: t("Match Voice", "沿用参考"), value: "clone" },
              { label: t("Describe Tone", "描述语气"), value: "text" },
              { label: t("Reference Audio", "参考音频"), value: "reference" },
            ]}
          />
          {form.emotionMode === "clone" && (
            <Text type="secondary">
              {t("Preserve the natural tone of your selected reference voice.", "保持参考音色原有的语气，自然朗读文本。")}
            </Text>
          )}
          {form.emotionMode === "text" && (
            <div className="studio-field-group">
              <label htmlFor={emotionTextId}>{t("Desired tone", "想要什么语气？")}</label>
              <TextArea
                id={emotionTextId}
                aria-label={t("Desired tone", "想要什么语气")}
                rows={2}
                maxLength={500}
                value={form.emotionText}
                onValueChange={(value) => update("emotionText", value)}
                placeholder={t(
                  "e.g., warm storytelling, or excited announcement. Leave empty to infer from the text.",
                  "例如：温柔地讲故事，或兴奋地宣布好消息。留空则根据文本判断。",
                )}
              />
            </div>
          )}
          {form.emotionMode === "reference" && (
            <AudioSourceField
              label={t("Emotion Reference Audio", "情绪参考音频")}
              hint={t("Transfer prosody from this clip while keeping the speaker voice above", "借用这段音频的语气，保留上方选择的音色")}
              value={form.emotionAudio}
              onChange={(value) => update("emotionAudio", value)}
            />
          )}
          {form.emotionMode !== "clone" && (
            <div className="studio-field-group">
              <div className="tts-control-heading">
                <span>{t("Emotion Strength", "情绪强度")}</span>
                <span className="studio-tabular">{Math.round(form.emotionStrength * 100)}%</span>
              </div>
              <Slider
                aria-label={t("Emotion strength", "情绪强度")}
                min={0}
                max={1}
                step={0.05}
                value={form.emotionStrength}
                onChange={(value) => update("emotionStrength", value)}
              />
            </div>
          )}
        </div>
      </Card>

      <GenerateButton
        busy={isBusy}
        queued={activeTask?.status === "queued"}
        onCancel={() => void cancelActive()}
        onGenerate={() => void generate()}
      />
    </form>
  );

  const rightPane = (
    <>
      {isBusy && activeTask && (
        <Card className="studio-card" title={activeTask.status === "queued" ? t("Queued", "等待合成") : t("Synthesizing", "正在合成")}>
          <div className="tts-stack">
            <Progress percent={Math.round(activeTask.progress * 100)} />
            <Text type="secondary">{activeTask.stage || t("Preparing speech synthesis…", "正在准备语音合成……")}</Text>
            {activeTask.status === "queued" && <Button onClick={() => void cancelActive()}>{t("Cancel queue", "取消排队")}</Button>}
          </div>
        </Card>
      )}
      {activeTask?.status === "failed" && <Alert type="error" showIcon message={t("Synthesis failed", "生成失败")} description={activeTask.error} />}
      <Card className="studio-card" title={<Space size={8}><PlayCircleOutlined /><span>{t("Audition", "试听")}</span></Space>}>
        {displayed ? (
          <div className="tts-stack">
            <Segmented
              aria-label={t("Audition source", "试听来源")}
              value={auditionSource}
              onChange={(value) => setAuditionSource(value as "synth" | "ref")}
              options={[
                { label: t("Synthesized", "合成结果"), value: "synth" },
                { label: t("Reference", "参考原声"), value: "ref" },
              ]}
            />
            <audio
              className="studio-audio-player"
              controls
              preload="metadata"
              key={`${displayed.id}-${auditionSource}`}
              src={auditionSource === "synth" ? resolveApiUrl(displayed.result.audio_url, true) : referenceUrl}
            />
            <Space wrap size={8} className="studio-tabular">
              <Tag>{t(`${displayed.result.duration_sec}s`, `${displayed.result.duration_sec} 秒`)}</Tag>
              <Tag>{displayed.result.format.toUpperCase()}</Tag>
              <Text type="secondary">{(displayed.result.sample_rate / 1000).toFixed(1)} kHz</Text>
            </Space>
            <Text>{displayed.params.text}</Text>
            <Space wrap size={8}>
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                href={resolveApiUrl(displayed.result.download_url, true)}
                target="_blank"
                rel="noreferrer"
              >
                {t("Download Audio", "下载音频")}
              </Button>
              <Button onClick={() => reuse(displayed)}>{t("Reuse", "再次使用")}</Button>
            </Space>
          </div>
        ) : (
          <Empty
            title={t("Ready to Synthesize", "等待语音合成")}
            description={t("Generated speech will appear here for playback, A/B comparison, and download.", "生成后在这里试听、对比原声和下载音频")}
            icon={<SoundOutlined />}
            shape="softBurst"
          />
        )}
      </Card>

      <Card
        className="studio-card"
        title={<Space size={8}><HistoryOutlined /><span>{t(`Session History (${history.length})`, `本次历史（${history.length}）`)}</span></Space>}
        extra={
          history.length > 0 && (
            <Popconfirm
              title={t("Clear session history?", "清空本次会话的历史记录？")}
              onConfirm={clearAll}
            >
              <Button type="text" size="small" icon={<DeleteOutlined />}>
                {t("Clear", "清空")}
              </Button>
            </Popconfirm>
          )
        }
      >
        {history.length === 0 ? (
          <Text type="secondary">{t("Synthesized clips will appear here.", "生成过的语音会出现在这里。")}</Text>
        ) : (
          <ScrollArea maxHeight={360}>
            <div className="tts-history-list">
              <List variant="segmented" className="studio-history-segmented" aria-label={t("Session history", "本次历史")}>
                {history.map((entry) => (
                  <ListItem
                    key={entry.id}
                    interactive
                    selected={entry.id === displayed?.id}
                    headline={entry.params.text}
                    supportingText={`${new Date(entry.createdAt).toLocaleTimeString(locale === "zh" ? "zh-CN" : "en-US", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })} · ${t(`${entry.result.duration_sec}s`, `${entry.result.duration_sec} 秒`)}`}
                    trailing={<Button type="text" size="small" onClick={() => reuse(entry)}>{t("Reuse", "再次使用")}</Button>}
                    trailingDivider
                    onClick={() => {
                      setSelectedId(entry.id);
                      setAuditionSource("synth");
                    }}
                  />
                ))}
              </List>
            </div>
          </ScrollArea>
        )}
      </Card>
    </>
  );

  return (
    <StudioShell
      brandBadge="TTS"
      defaultTitle="IndexTTS 2.5"
      defaultSubtitle={t("Reference Voice · Text Input · Audition", "选择音色 · 输入文本 · 生成试听")}
      onAuthChanged={refreshPresets}
      sampleRequestBody={{ ...payload, text: payload.text || EXAMPLE_TEXT[form.language] }}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
