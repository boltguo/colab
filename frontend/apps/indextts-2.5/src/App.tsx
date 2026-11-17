import {
Alert,AudioSourceField,Button,Card,DeleteOutlined,DownloadOutlined,Empty,
GenerateDock,HistoryOutlined,PlayCircleOutlined,Popconfirm,Progress,ReloadOutlined,
ScrollArea,Segmented,Select,Slider,SoundOutlined,Space,StudioShell,
Tag,Text,TextArea,Tooltip,fetchPresets,resolveApiUrl,
useHistoryStore,useStudioFeedback,useTaskRunner,
type HistoryEntry,type PresetItem,
} from "@colab/shared";
import React,{ useCallback,useEffect,useId,useMemo,useState } from "react";
import { DEFAULT_FORM,EXAMPLE_TEXT,buildTtsRequest,restoreTtsForm } from "./request";
import "./studio.css";
import type { IndexTTSRequestPayload,IndexTTSResult,LanguageCode,OutputFormat,TtsForm } from "./types";

type TtsEntry = HistoryEntry<IndexTTSResult, IndexTTSRequestPayload>;

export function IndexTTSStudioApp() {
  const { message } = useStudioFeedback();
  const [form, setForm] = useState<TtsForm>({ ...DEFAULT_FORM });
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [auditionSource, setAuditionSource] = useState<"synth" | "ref">("synth");
  const textId = useId();
  const languageId = useId();
  const emotionTextId = useId();
  const { items: history, addEntry, clearAll } = useHistoryStore<IndexTTSResult, IndexTTSRequestPayload>("indextts-2.5", 30);

  const update = <Key extends keyof TtsForm>(key: Key, value: TtsForm[Key]) => {
    setForm((previous) => ({ ...previous, [key]: value }));
  };
  const refreshPresets = useCallback(() => {
    void fetchPresets().then(setPresets).catch(() => setPresets([]));
  }, []);
  useEffect(refreshPresets, [refreshPresets]);

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<IndexTTSResult, IndexTTSRequestPayload>({
    onSuccess: (task) => {
      if (!task.result) return;
      addEntry({ id: task.task_id, feature: "indextts-2.5", createdAt: task.finished_at || task.created_at,
        elapsedSec: task.elapsed_sec, params: task.params, result: task.result });
      setSelectedId(task.task_id);
      setAuditionSource("synth");
      message.success("语音已生成，可以试听或下载");
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
    if (!form.text.trim()) { message.warning("请输入要合成的文本"); return; }
    if (!form.speakerAudio) { message.warning("请选择参考音色"); return; }
    if (form.emotionMode === "reference" && !form.emotionAudio) {
      message.warning("请上传用于参考情绪的音频"); return;
    }
    await runTask(payload);
  };
  const reuse = (entry: TtsEntry) => {
    setForm(restoreTtsForm(entry.params));
    setSelectedId(entry.id);
    setAuditionSource("synth");
    message.success("已填入这次生成的文本和常用设置");
  };

  const leftPane = (
    <form onSubmit={(event) => void generate(event)} className="tts-form">
      <Card className="studio-card" title={<Space size={8}><SoundOutlined /><span>参考音色</span></Space>}>
        <AudioSourceField label="选择一段参考人声" hint="使用内置音色，也可以上传或录制自己的声音"
          value={form.speakerAudio} onChange={(value) => update("speakerAudio", value)} presets={presets} allowPreset />
      </Card>

      <Card className="studio-card" title="合成文本"
        extra={<Button type="text" size="small" onClick={() => update("text", EXAMPLE_TEXT[form.language])}>填入示例</Button>}>
        <div className="tts-stack">
          <div className="studio-field-group">
            <label className="studio-visually-hidden" htmlFor={textId}>要合成的文本</label>
            <TextArea id={textId} aria-label="要合成的文本" rows={6} maxLength={5000} value={form.text}
              placeholder="输入你希望说出的内容……" onValueChange={(value) => update("text", value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                  event.preventDefault(); void generate();
                }
              }} />
            <div className="tts-text-footer"><span>⌘ / Ctrl + Enter 生成</span><span>{form.text.length} / 5000</span></div>
          </div>
          <div className="tts-main-settings">
            <div className="studio-field-group">
              <div className="tts-control-heading"><label htmlFor={languageId}>语言</label></div>
              <div className="tts-control-body">
                <Select id={languageId} aria-label="合成语言" value={form.language} onChange={(value) => update("language", value as LanguageCode)}
                  options={[{ label: "中文", value: "zh" }, { label: "English", value: "en" }, { label: "日本語", value: "ja" },
                    { label: "Español", value: "es" }, { label: "العربية", value: "ar" }]} />
              </div>
            </div>
            <div className="studio-field-group">
              <div className="tts-control-heading">
                <span>语速</span>
                <Space size={6}><span className="studio-tabular">{form.speed.toFixed(2)} 倍</span>
                  <Tooltip title="恢复正常语速"><Button type="text" size="small" icon={<ReloadOutlined />}
                    aria-label="恢复正常语速" disabled={form.speed === 1} onClick={() => update("speed", 1)} /></Tooltip>
                </Space>
              </div>
              <div className="tts-control-body"><Slider aria-label="语速" min={0.5} max={2} step={0.05}
                value={form.speed} onChange={(value) => update("speed", value)} /></div>
            </div>
          </div>
        </div>
      </Card>

      <Card className="studio-card" title="情绪">
        <div className="tts-stack">
          <Segmented block aria-label="情绪方式" value={form.emotionMode}
            onChange={(value) => update("emotionMode", value as TtsForm["emotionMode"])}
            options={[{ label: "沿用参考", value: "clone" }, { label: "描述语气", value: "text" }, { label: "参考音频", value: "reference" }]} />
          {form.emotionMode === "clone" && <Text type="secondary">保持参考音色原有的语气，自然朗读文本。</Text>}
          {form.emotionMode === "text" && <div className="studio-field-group">
            <label htmlFor={emotionTextId}>想要什么语气？</label>
            <TextArea id={emotionTextId} aria-label="想要什么语气" rows={2} maxLength={500} value={form.emotionText}
              onValueChange={(value) => update("emotionText", value)} placeholder="例如：温柔地讲故事，或兴奋地宣布好消息。留空则根据文本判断。" />
          </div>}
          {form.emotionMode === "reference" && <AudioSourceField label="情绪参考音频"
            hint="借用这段音频的语气，保留上方选择的音色" value={form.emotionAudio}
            onChange={(value) => update("emotionAudio", value)} />}
          {form.emotionMode !== "clone" && <div className="studio-field-group">
            <div className="tts-control-heading"><span>情绪强度</span><span className="studio-tabular">{Math.round(form.emotionStrength * 100)}%</span></div>
            <Slider aria-label="情绪强度" min={0} max={1} step={0.05} value={form.emotionStrength}
              onChange={(value) => update("emotionStrength", value)} />
          </div>}
        </div>
      </Card>

      <GenerateDock format={form.outputFormat} onFormatChange={(value) => update("outputFormat", value as OutputFormat)}
        formats={[{ label: "MP3", value: "mp3" }, { label: "WAV", value: "wav" }, { label: "FLAC", value: "flac" }]}
        busy={isBusy} queued={activeTask?.status === "queued"} onCancel={() => void cancelActive()} onGenerate={() => void generate()} />
    </form>
  );

  const rightPane = <>
    {isBusy && activeTask && <Card className="studio-card" title={activeTask.status === "queued" ? "等待合成" : "正在合成"}>
      <div className="tts-stack"><Progress percent={Math.round(activeTask.progress * 100)} />
        <Text type="secondary">{activeTask.stage || "正在准备语音合成……"}</Text>
        {activeTask.status === "queued" && <Button onClick={() => void cancelActive()}>取消排队</Button>}
      </div>
    </Card>}
    {activeTask?.status === "failed" && <Alert type="error" showIcon message="生成失败" description={activeTask.error} />}
    <Card className="studio-card" title={<Space size={8}><PlayCircleOutlined /><span>试听</span></Space>}>
      {displayed ? <div className="tts-stack">
        <Segmented aria-label="试听来源" value={auditionSource} onChange={(value) => setAuditionSource(value as "synth" | "ref")}
          options={[{ label: "合成结果", value: "synth" }, { label: "参考原声", value: "ref" }]} />
        <audio className="studio-audio-player" controls preload="metadata"
          key={`${displayed.id}-${auditionSource}`} src={auditionSource === "synth" ? resolveApiUrl(displayed.result.audio_url, true) : referenceUrl} />
        <Space wrap size={8} className="studio-tabular"><Tag>{displayed.result.duration_sec} 秒</Tag>
          <Tag>{displayed.result.format.toUpperCase()}</Tag><Text type="secondary">{(displayed.result.sample_rate / 1000).toFixed(1)} kHz</Text>
        </Space>
        <Text>{displayed.params.text}</Text>
        <Space wrap size={8}>
          <Button type="primary" icon={<DownloadOutlined />} href={resolveApiUrl(displayed.result.download_url, true)}
            target="_blank" rel="noreferrer">下载音频</Button>
          <Button onClick={() => reuse(displayed)}>再次使用</Button>
        </Space>
      </div> : <Empty description="生成后在这里试听、对比原声和下载音频" />}
    </Card>

    <Card className="studio-card" title={<Space size={8}><HistoryOutlined /><span>本次历史（{history.length}）</span></Space>}
      extra={history.length > 0 && <Popconfirm title="清空本次会话的历史记录？" onConfirm={clearAll}>
        <Button type="text" size="small" icon={<DeleteOutlined />}>清空</Button>
      </Popconfirm>}>
      {history.length === 0 ? <Text type="secondary">生成过的语音会出现在这里。</Text> :
        <ScrollArea maxHeight={360}><div className="tts-history-list">{history.map((entry) =>
          <div key={entry.id} className="tts-history-entry">
            <Button type={entry.id === displayed?.id ? "default" : "text"} block onClick={() => { setSelectedId(entry.id); setAuditionSource("synth"); }}>
              <span className="tts-history-label">{entry.params.text}</span>
            </Button>
            <div className="tts-history-meta"><Text type="secondary">{new Date(entry.createdAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })} · {entry.result.duration_sec} 秒</Text>
              <Button type="text" size="small" onClick={() => reuse(entry)}>再次使用</Button>
            </div>
          </div>
        )}</div></ScrollArea>}
    </Card>
  </>;

  return <StudioShell brandBadge="TTS" defaultTitle="IndexTTS 2.5"
    defaultSubtitle="选择音色 · 输入文本 · 生成试听" onAuthChanged={refreshPresets}
    sampleRequestBody={{ ...payload, text: payload.text || EXAMPLE_TEXT[form.language] }}
    leftPane={leftPane} rightPane={rightPane} />;
}
