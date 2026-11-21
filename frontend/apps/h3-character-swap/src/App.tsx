import {
  Alert,
  Button,
  Card,
  ClearOutlined,
  CollapsibleSection,
  DeleteOutlined,
  Empty,
  FieldLabel,
  GenerateButton,
  HistoryOutlined,
  ImageSourceField,
  Input,
  InputNumber,
  Kbd,
  LockOutlined,
  PictureOutlined,
  PlusOutlined,
  Popconfirm,
  Progress,
  ScrollArea,
  SeedControl,
  Segmented,
  Select,
  Space,
  StudioShell,
  Switch,
  Tag,
  Text,
  TextArea,
  TokenChip,
  UserOutlined,
  VideoCameraOutlined,
  resolveApiUrl,
  useHistoryStore,
  useStudioFeedback,
  useStudioLocale,
  useTaskRunner,
} from "@colab/shared";
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { VideoCompareStage } from "./VideoCompareStage";
import { VideoInputCard, type VideoSourceMeta } from "./VideoInputCard";
import {
  buildCharacterSwapRequest,
  computeSwapPreviewDimensions,
  estimateWindowCount,
  restoreCharacterSwapState,
} from "./request";
import {
  createEmptyCharacterSlot,
  DEFAULT_SWAP_PARAMS,
  type ClipRangeMode,
  type H3CharacterSwapParams,
  type H3CharacterSwapRequest,
  type H3CharacterSwapResult,
  type ResolutionTier,
  type SwapMode,
  type VideoOutputFormat,
} from "./types";

const MAX_UI_CHARACTERS = 4;

export function H3CharacterSwapStudioApp() {
  const promptInputId = useId();
  const startTimeInputId = useId();
  const durationInputId = useId();
  const outputFormatId = useId();
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const { t } = useStudioLocale();
  const { message } = useStudioFeedback();

  const [params, setParams] = useState<H3CharacterSwapParams>(DEFAULT_SWAP_PARAMS);
  const [sourceMeta, setSourceMeta] = useState<VideoSourceMeta | null>(null);
  const [seedLocked, setSeedLocked] = useState(false);
  const [selectedTakeId, setSelectedTakeId] = useState<string | null>(null);

  const { items: historyItems, addEntry, clearAll } = useHistoryStore<
    H3CharacterSwapResult,
    H3CharacterSwapRequest
  >("h3-character-swap", 24);

  const effectivePayload = useMemo(
    () =>
      buildCharacterSwapRequest(params, {
        fallbackSource: "<UPLOADED_VIDEO_ID>",
        fallbackCharImage: "<UPLOADED_CHARACTER_IMAGE_ID>",
      }),
    [params]
  );

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<
    H3CharacterSwapResult,
    H3CharacterSwapRequest
  >({
    endpointPath: "/api/v1/generate",
    onSuccess: (finishedTask) => {
      if (finishedTask.result) {
        addEntry({
          id: finishedTask.task_id,
          feature: "h3-character-swap",
          createdAt: finishedTask.finished_at || new Date().toISOString(),
          elapsedSec: finishedTask.elapsed_sec,
          params: finishedTask.params,
          result: finishedTask.result,
        });
        setSelectedTakeId(finishedTask.task_id);
        if (seedLocked && finishedTask.result.seed) {
          setParams((prev) => ({ ...prev, seed: finishedTask.result!.seed }));
        }
        message.success(
          t(
            `Character swap completed (${finishedTask.result.width}×${finishedTask.result.height} · ${finishedTask.result.duration_sec.toFixed(1)}s)`,
            `人物替换完成（${finishedTask.result.width}×${finishedTask.result.height} · ${finishedTask.result.duration_sec.toFixed(1)}s）`,
          )
        );
      }
    },
    onError: (errMsg) => {
      message.error(errMsg);
    },
  });

  const updateField = useCallback(
    <K extends keyof H3CharacterSwapParams>(key: K, val: H3CharacterSwapParams[K]) => {
      setParams((prev) => ({ ...prev, [key]: val }));
    },
    []
  );

  const handleModeChange = (nextMode: SwapMode) => {
    setParams((prev) => {
      if (prev.mode === nextMode) return prev;
      if (nextMode === "multi") {
        const nextChars =
          prev.characters.length >= 2
            ? prev.characters
            : [...prev.characters, createEmptyCharacterSlot()];
        return { ...prev, mode: "multi", characters: nextChars };
      }
      return {
        ...prev,
        mode: "single",
        characters: [prev.characters[0] ?? createEmptyCharacterSlot()],
      };
    });
  };

  const updateCharacter = (
    idx: number,
    patch: Partial<H3CharacterSwapParams["characters"][number]>
  ) => {
    setParams((prev) => ({
      ...prev,
      characters: prev.characters.map((slot, i) => (i === idx ? { ...slot, ...patch } : slot)),
    }));
  };

  const addCharacterSlot = () => {
    setParams((prev) => {
      if (prev.mode !== "multi" || prev.characters.length >= MAX_UI_CHARACTERS) return prev;
      return { ...prev, characters: [...prev.characters, createEmptyCharacterSlot()] };
    });
  };

  const removeCharacterSlot = (idx: number) => {
    setParams((prev) => {
      if (prev.mode !== "multi" || prev.characters.length <= 2) return prev;
      return {
        ...prev,
        characters: prev.characters.filter((_, i) => i !== idx),
      };
    });
  };

  const insertToken = (token: string) => {
    const el = promptRef.current;
    const text = params.prompt;
    if (el && typeof el.selectionStart === "number" && typeof el.selectionEnd === "number") {
      const start = el.selectionStart;
      const end = el.selectionEnd;
      const needsSpaceBefore = start > 0 && !/\s$/.test(text.slice(0, start));
      const needsSpaceAfter = end < text.length && !/^\s/.test(text.slice(end));
      const inserted = `${needsSpaceBefore ? " " : ""}${token}${needsSpaceAfter ? " " : " "}`;
      const next = `${text.slice(0, start)}${inserted}${text.slice(end)}`;
      updateField("prompt", next);
      window.requestAnimationFrame(() => {
        el.focus();
        const cursor = start + inserted.length;
        el.setSelectionRange(cursor, cursor);
      });
      return;
    }
    const separator = text && !/\s$/.test(text) ? " " : "";
    updateField("prompt", `${text}${separator}${token} `);
  };

  const handleSubmit = () => {
    if (!params.source_video.trim()) {
      message.warning(t("Please upload a source video first.", "请先上传待替换的原视频。"));
      return;
    }
    const scoped = params.mode === "single" ? params.characters.slice(0, 1) : params.characters;
    const validChars = scoped.filter((c) => c.image.trim().length > 0);
    if (validChars.length === 0) {
      message.warning(t("Please upload a target character reference image.", "请先上传目标角色参考图。"));
      return;
    }
    if (params.mode === "multi" && validChars.length < 2) {
      message.warning(
        t(
          "Multi-Person Swap requires at least 2 character images (or switch to Character Swap).",
          "多人物替换模式请至少上传 2 张角色参考图（或切换为人物替换）。",
        ),
      );
      return;
    }
    const payload = buildCharacterSwapRequest(params);
    void runTask(payload);
  };

  const previewDims = computeSwapPreviewDimensions(
    sourceMeta?.w || 16,
    sourceMeta?.h || 9,
    params.resolution_tier,
    params.preserve_aspect
  );
  const estimatedClipSec =
    params.clip_range_mode === "full"
      ? sourceMeta?.dur || 0
      : params.clip_range_mode === "preview5s"
      ? Math.min(sourceMeta?.dur || 5, 5)
      : Math.min(sourceMeta?.dur || params.duration_sec, params.duration_sec);
  const estimatedWindows = estimateWindowCount(estimatedClipSec);

  const displayedEntry =
    historyItems.find((item) => item.id === selectedTakeId) || historyItems[0] || null;
  const activeGuide = params.guide_frames[0] || null;
  const statusUpper = activeTask?.status?.toUpperCase() || "";
  const isRunning = isBusy;
  const isQueued = activeTask?.status === "queued";
  const visibleCharacters = params.mode === "single" ? params.characters.slice(0, 1) : params.characters;

  const leftPane = (
    <>
      {/* 1. Mode & Source Video */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <VideoCameraOutlined style={{ color: "var(--studio-accent)" }} />
            <span>{t("Mode & Source Video", "模式与源视频")}</span>
          </Space>
        }
        extra={
          <Button
            htmlType="button"
            size="small"
            type="text"
            icon={<ClearOutlined />}
            onClick={() => {
              setParams(DEFAULT_SWAP_PARAMS);
              setSourceMeta(null);
              setSeedLocked(false);
            }}
          >
            {t("Reset", "恢复默认")}
          </Button>
        }
      >
        <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
          <div className="studio-field-group">
            <FieldLabel
              label={t("Swap Mode", "替换模式")}
              tooltip={t(
                "Character Swap replaces one person in the video; Multi-Person Swap replaces 2–4 distinct people in the same shot.",
                "人物替换用于替换视频中的主角；多人物替换支持为同一镜头中的 2–4 位人物分别指定替换角色。",
              )}
            />
            <Segmented
              block
              value={params.mode}
              onChange={(val) => handleModeChange(val as SwapMode)}
              options={[
                { label: t("Character Swap", "人物替换"), value: "single" },
                { label: t("Multi-Person Swap", "多人物替换"), value: "multi" },
              ]}
            />
          </div>

          <VideoInputCard
            label={t("Source Video", "原视频")}
            badgeText="<Video 1>"
            value={params.source_video}
            onChange={(val) => updateField("source_video", val)}
            onMetadataChange={setSourceMeta}
          />
        </Space>
      </Card>

      {/* 2. Target Character Reference(s) */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <UserOutlined style={{ color: "var(--studio-accent)" }} />
            <span>
              {params.mode === "single"
                ? t("Target Character", "目标角色参考图")
                : t(`Character Mapping (${visibleCharacters.length})`, `多人物角色映射（${visibleCharacters.length} 位）`)}
            </span>
          </Space>
        }
        extra={
          params.mode === "multi" && params.characters.length < MAX_UI_CHARACTERS ? (
            <Button
              htmlType="button"
              size="small"
              icon={<PlusOutlined />}
              onClick={addCharacterSlot}
            >
              {t("Add Character", "添加替换角色")}
            </Button>
          ) : undefined
        }
      >
        <Space direction="vertical" size={12} style={{ inlineSize: "100%" }}>
          {visibleCharacters.map((slot, idx) => {
            const picBadge = `<Picture ${idx + 1}>`;
            const slotLabel =
              params.mode === "single"
                ? t("Target Character", "目标角色")
                : t(`Character ${idx + 1}`, `替换角色 ${idx + 1}`);
            const targetId = `swap-char-target-${idx}`;
            return (
              <div
                key={idx}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                  padding: "0.75rem",
                  borderRadius: "var(--m3e-shape-corner-medium)",
                  background: "var(--m3e-color-surface-container)",
                }}
              >
                <ImageSourceField
                  label={slotLabel}
                  badgeText={picBadge}
                  value={slot.image}
                  onChange={(val) => updateCharacter(idx, { image: val })}
                  onRemoveSlot={
                    params.mode === "multi" && params.characters.length > 2
                      ? () => removeCharacterSlot(idx)
                      : undefined
                  }
                />
                <div className="studio-field-group">
                  <label htmlFor={targetId} className="studio-field-label">
                    <span>{t("Who to replace in source video (optional)", "原视频中要替换谁（可选）")}</span>
                  </label>
                  <Input
                    id={targetId}
                    name={targetId}
                    value={slot.target_description || ""}
                    placeholder={
                      params.mode === "multi"
                        ? idx === 0
                          ? t("e.g., dancer in black on the left", "例如：画面左侧穿黑衣的舞者")
                          : t("e.g., singer in a hat on the right", "例如：画面右侧戴帽子的歌手")
                        : t("e.g., the dancing person in the center", "例如：画面中央正在跳舞的人")
                    }
                    onValueChange={(val) => updateCharacter(idx, { target_description: val })}
                  />
                </div>
              </div>
            );
          })}
        </Space>
      </Card>

      {/* 3. Prompt & Optional Keyframe Guide */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <PictureOutlined style={{ color: "var(--studio-accent)" }} />
            <span>{t("Instructions & Keyframe Anchor", "替换说明与可选关键帧引导")}</span>
          </Space>
        }
      >
        <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
          <div className="studio-field-group">
            <FieldLabel
              htmlFor={promptInputId}
              label={t("Swap Prompt (optional)", "替换描述（Prompt，可选）")}
              tooltip={t(
                "Leave blank to automatically build the <Video 1> + <Picture 1..N> replacement instruction, or write your own custom prompt referencing <Video 1> and <Picture 1>.",
                "留空时会自动生成基于 <Video 1> 与 <Picture 1..N> 的人物替换指令；也可补充细节要求或自定义完整替换提示词。",
              )}
              extra={
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  <TokenChip onClick={() => insertToken("<Video 1>")}>{"<Video 1>"}</TokenChip>
                  {visibleCharacters.map((_, idx) => (
                    <TokenChip key={idx} onClick={() => insertToken(`<Picture ${idx + 1}>`)}>
                      {`<Picture ${idx + 1}>`}
                    </TokenChip>
                  ))}
                </div>
              }
            />
            <TextArea
              ref={promptRef}
              id={promptInputId}
              rows={4}
              maxLength={8000}
              showCount
              value={params.prompt}
              placeholder={t(
                "Optional: add lighting style, preservation notes, or specific mapping rules (leave empty to auto-build the full swap prompt from your video and character image).",
                "可选：补充目标氛围、细节保留要求或特定替换关系（留空则自动根据上传的视频与角色图构造完整替换指令）",
              )}
              onValueChange={(val) => updateField("prompt", val)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  handleSubmit();
                }
              }}
            />
            <div className="studio-shortcut-hint">
              <Kbd keys={["mod", "enter"]} size="sm" />
              <span>{t("Start swap", "快捷开始替换")}</span>
            </div>
          </div>

          <CollapsibleSection
            title={t("Optional: Keyframe Anchor Guide", "可选：关键帧锚点引导（Anchor Guide）")}
            subtitle={t(
              "Pin frame 0 (or a target frame) with an edited frame image to lock subject placement and look.",
              "上传一张修绘后的源帧画面，钉住首帧或指定帧的人物与构图一致性",
            )}
            trailingBadge={
              activeGuide?.image ? <Tag color="processing">{t("Guide Attached", "已挂载引导帧")}</Tag> : undefined
            }
          >
            <Space direction="vertical" size={12} style={{ inlineSize: "100%" }}>
              <ImageSourceField
                label={t("Anchor Frame Image", "关键帧锚点图")}
                badgeText={activeGuide ? `Frame ${activeGuide.frame_index}` : "Frame 0"}
                value={activeGuide?.image || ""}
                onChange={(val) =>
                  updateField(
                    "guide_frames",
                    val
                      ? [{ image: val, frame_index: activeGuide?.frame_index ?? 0 }]
                      : []
                  )
                }
              />
              {activeGuide?.image && (
                <div className="studio-field-group">
                  <FieldLabel
                    htmlFor="swap-guide-frame-index"
                    label={t("Anchor Frame Index (24 fps)", "锚定帧序号（24 fps）")}
                    tooltip={t(
                      "0 = first frame (recommended). Anchors the edited frame as a keyframe guide at this exact 24 fps position.",
                      "0 表示第 1 帧（推荐），将该引导图锚定在对应 24 fps 帧位置以锁定人物与构图。",
                    )}
                  />
                  <InputNumber
                    id="swap-guide-frame-index"
                    aria-label={t("Anchor frame index", "锚定帧序号")}
                    min={0}
                    max={2000}
                    precision={0}
                    value={activeGuide.frame_index}
                    onChange={(val) =>
                      updateField("guide_frames", [
                        {
                          image: activeGuide.image,
                          frame_index: Math.max(0, Math.round(Number(val) || 0)),
                        },
                      ])
                    }
                  />
                </div>
              )}
            </Space>
          </CollapsibleSection>
        </Space>
      </Card>

      {/* 4. Output & Generation Settings */}
      <Card className="studio-card" title={t("Output & Generation Settings", "输出与生成设置")}>
        <Space direction="vertical" size={14} style={{ inlineSize: "100%" }}>
          <div className="studio-field-group">
            <FieldLabel
              label={t("Resolution Tier", "画质档位")}
              tooltip={t(
                "480p is fast and fits 40GB+ VRAM; 736p delivers sharp HD detail (80GB+ recommended).",
                "480p 适合快速验证效果（支持 40GB+ 显存）；736p 为高清晰度出片（推荐 80GB+ 显存）。",
              )}
              extra={
                <span className="studio-tabular" style={{ fontSize: 12, color: "var(--studio-text-muted)" }}>
                  ~{previewDims.width} × {previewDims.height} px · 24 fps
                  {estimatedWindows > 1
                    ? t(` · ~${estimatedWindows} windows`, ` · 约 ${estimatedWindows} 窗连续渲染`)
                    : ""}
                </span>
              }
            />
            <Segmented
              block
              value={params.resolution_tier}
              onChange={(val) => updateField("resolution_tier", val as ResolutionTier)}
              options={[
                { label: t("480p · Fast", "480p · 快速稳定"), value: "480p" },
                { label: t("736p · HD Detail", "736p · 高清细节"), value: "736p" },
              ]}
            />
          </div>

          <div className="studio-field-group">
            <FieldLabel
              label={t("Clip Range", "处理时长范围")}
              tooltip={t(
                "Clips longer than 226 frames automatically chain with 5-frame motion overlap. Try First 5s first to verify look & alignment.",
                "整段处理时超过单个 226 帧窗口会自动使用 5 帧历史无缝接续；首次建议先试跑前 5 秒检查替换效果。",
              )}
            />
            <Segmented
              block
              value={params.clip_range_mode}
              onChange={(val) => updateField("clip_range_mode", val as ClipRangeMode)}
              options={[
                { label: t("Full Video", "整段原视频"), value: "full" },
                { label: t("First 5s Preview", "前 5 秒试跑"), value: "preview5s" },
                { label: t("Custom Range", "自定义片段"), value: "custom" },
              ]}
            />
          </div>

          {params.clip_range_mode === "custom" && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                gap: 12,
              }}
            >
              <div className="studio-field-group">
                <label htmlFor={startTimeInputId} className="studio-field-label">
                  <span>{t("Start Time (sec)", "起始时间（秒）")}</span>
                </label>
                <InputNumber
                  id={startTimeInputId}
                  aria-label={t("Start time (sec)", "起始时间（秒）")}
                  min={0}
                  max={3600}
                  step={0.5}
                  precision={1}
                  addonAfter="s"
                  value={params.start_time_sec}
                  onChange={(val) => updateField("start_time_sec", Math.max(0, Number(val) || 0))}
                />
              </div>
              <div className="studio-field-group">
                <label htmlFor={durationInputId} className="studio-field-label">
                  <span>{t("Clip Duration (sec)", "截取时长（秒）")}</span>
                </label>
                <InputNumber
                  id={durationInputId}
                  aria-label={t("Clip duration (sec)", "截取时长（秒）")}
                  min={1}
                  max={60}
                  step={0.5}
                  precision={1}
                  addonAfter="s"
                  value={params.duration_sec}
                  onChange={(val) =>
                    updateField("duration_sec", Math.max(1, Math.min(60, Number(val) || 5)))
                  }
                />
              </div>
            </div>
          )}

          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <Switch
              checked={params.keep_audio}
              label={t("Keep original audio", "保留原视频音轨")}
              onChange={(checked) => updateField("keep_audio", checked)}
            />
            <Switch
              checked={params.preserve_aspect}
              label={t("Preserve aspect ratio", "保持原画幅比例")}
              onChange={(checked) => updateField("preserve_aspect", checked)}
            />
          </div>

          <div className="studio-settings-grid">
            <div className="studio-field-group">
              <label htmlFor={outputFormatId} className="studio-field-label">
                <span>{t("Output Format", "输出格式")}</span>
              </label>
              <Select
                id={outputFormatId}
                aria-label={t("Output format", "输出格式")}
                value={params.output_format}
                onChange={(val) => updateField("output_format", val as VideoOutputFormat)}
                options={[
                  { label: "MP4", value: "mp4" },
                  { label: "WebM", value: "webm" },
                  { label: "MKV", value: "mkv" },
                ]}
              />
            </div>
            <SeedControl
              value={params.seed}
              max={2147483647}
              onChange={(val) => updateField("seed", val)}
              onLockedChange={setSeedLocked}
            />
          </div>
        </Space>
      </Card>

      <GenerateButton
        busy={isRunning}
        queued={isQueued}
        label={t("Start Swap", "开始替换")}
        onGenerate={handleSubmit}
        onCancel={cancelActive}
      />
    </>
  );

  const rightPane = (
    <>
      <Card className="studio-card" title={t("Output & A/B Comparison", "替换结果与 A/B 对比")}>
        {activeTask && ["queued", "running"].includes(activeTask.status) && (
          <div style={{ marginBlockEnd: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBlockEnd: 6 }}>
              <Tag color="processing">{statusUpper}</Tag>
              <Text className="studio-tabular" type="secondary">
                {Math.round(activeTask.progress * 100)}%
              </Text>
            </div>
            <Progress percent={Math.round(activeTask.progress * 100)} />
            <Text type="secondary" style={{ display: "block", marginBlockStart: 6, fontSize: 12.5 }}>
              {activeTask.stage || t("Preparing task...", "准备任务中...")}
            </Text>
          </div>
        )}

        {activeTask?.status === "failed" && activeTask.error && (
          <Alert
            type="error"
            showIcon
            message={t("Character swap failed", "人物替换失败")}
            description={activeTask.error}
            style={{ marginBlockEnd: 14 }}
          />
        )}

        {!displayedEntry ? (
          <Empty
            shape="clover4Leaf"
            title={t("Ready for Character Swap", "等待人物替换")}
            description={t(
              "Upload a source video and target character image(s), then click Start Swap to inspect results with A/B comparison.",
              "上传原视频与目标角色参考图，点击开始替换即可同屏拖拽对比。",
            )}
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <VideoCompareStage
              result={displayedEntry.result}
              outputUrl={resolveApiUrl(displayedEntry.result.video_url)}
              downloadUrl={resolveApiUrl(`${displayedEntry.result.video_url}?download=true`)}
              inputUrl={
                displayedEntry.result.source_video_ref
                  ? resolveApiUrl(
                      `/api/v1/files/${encodeURIComponent(displayedEntry.result.source_video_ref)}`,
                    )
                  : undefined
              }
            />

            <div className="studio-meta-bar">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                <Tag color="processing">
                  {displayedEntry.result.mode === "multi"
                    ? t(`Multi-Person Swap (${displayedEntry.result.character_count})`, `多人物替换 (${displayedEntry.result.character_count} 人)`)
                    : t("Character Swap", "人物替换")}
                </Tag>
                <Tag className="studio-tabular">
                  {displayedEntry.result.width}×{displayedEntry.result.height} · {displayedEntry.result.fps}fps
                </Tag>
                <Tag className="studio-tabular">
                  {displayedEntry.result.duration_sec.toFixed(1)}s · {displayedEntry.result.window_count} {t("win", "窗")}
                </Tag>
                <Tag>{displayedEntry.result.has_audio ? t("Original Audio", "保留原声") : t("Muted", "静音")}</Tag>
              </div>
              <Button
                htmlType="button"
                size="small"
                icon={<LockOutlined />}
                onClick={() => {
                  setSeedLocked(true);
                  updateField("seed", displayedEntry.result.seed);
                  message.success(t(`Locked seed: ${displayedEntry.result.seed}`, `已锁定种子：${displayedEntry.result.seed}`));
                }}
              >
                {t(`Use seed ${displayedEntry.result.seed}`, `使用种子 ${displayedEntry.result.seed}`)}
              </Button>
            </div>
          </div>
        )}
      </Card>

      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <HistoryOutlined style={{ color: "var(--studio-accent)" }} />
            <span>{t(`Session History (${historyItems.length})`, `本次会话历史（${historyItems.length}）`)}</span>
          </Space>
        }
        extra={
          historyItems.length > 0 && (
            <Popconfirm
              title={t("Clear current session history?", "清空当前会话历史？")}
              okText={t("Clear", "清空")}
              cancelText={t("Cancel", "取消")}
              onConfirm={() => {
                clearAll();
                setSelectedTakeId(null);
              }}
            >
              <Button htmlType="button" size="small" type="text" danger icon={<DeleteOutlined />}>
                {t("Clear", "清空")}
              </Button>
            </Popconfirm>
          )
        }
      >
        {historyItems.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12.5 }}>
            {t(
              "Completed swaps appear here so you can preview them or restore their settings.",
              "替换完成的结果会保存在当前会话历史中，点击即可切换预览或恢复参数。",
            )}
          </Text>
        ) : (
          <ScrollArea maxHeight={420}>
            <div className="studio-video-history-list" style={{ paddingInlineEnd: 8 }}>
              {historyItems.map((item) => {
                const isSelected = displayedEntry?.id === item.id;
                const mediaSrc = resolveApiUrl(item.result.video_url);
                const titleText = `${
                  item.result.mode === "multi"
                    ? t("Multi-Person Swap", "多人物替换")
                    : t("Character Swap", "人物替换")
                } · ${item.result.resolution_tier}`;
                return (
                  <div
                    key={item.id}
                    className="studio-video-history-card"
                    data-active={isSelected ? "true" : "false"}
                  >
                    <video
                      src={mediaSrc}
                      controls
                      playsInline
                      preload="none"
                      width={148}
                      height={84}
                      {...({ loading: "lazy" } as Record<string, unknown>)}
                      style={{
                        inlineSize: "100%",
                        aspectRatio: "16 / 9",
                        objectFit: "cover",
                        borderRadius: 6,
                        background: "var(--m3e-color-on-surface)",
                      }}
                    />
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                        gap: 6,
                        minInlineSize: 0,
                      }}
                    >
                      <button
                        type="button"
                        className="studio-video-history-select"
                        aria-pressed={isSelected}
                        onClick={() => setSelectedTakeId(item.id)}
                      >
                        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--studio-text)" }}>
                          {titleText}
                        </div>
                      </button>
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 6,
                        }}
                      >
                        <span className="studio-tabular" style={{ fontSize: 11.5, color: "var(--studio-text-muted)" }}>
                          {item.result.width}×{item.result.height} · {item.result.duration_sec.toFixed(1)}s
                        </span>
                        <Button
                          htmlType="button"
                          size="small"
                          type="link"
                          style={{ padding: 0, blockSize: "auto", fontSize: 12 }}
                          onClick={() => {
                            const restored = restoreCharacterSwapState(item.params);
                            setParams(restored);
                            setSeedLocked(restored.seed > 0);
                            setSourceMeta({
                              w: item.result.input_width,
                              h: item.result.input_height,
                              dur: item.result.duration_sec,
                            });
                            message.info(t("Restored parameters from history", "已恢复该次替换参数"));
                          }}
                        >
                          {t("Reuse", "再次使用")}
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </Card>
    </>
  );

  return (
    <StudioShell
      brandBadge="CS"
      defaultTitle="H3 Character Swap"
      defaultSubtitle={t(
        "Character & Multi-Person Video Swap · Preserves motion, lighting & audio",
        "人物 / 多人物视频替换 · 保留动作、光影与原声",
      )}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
