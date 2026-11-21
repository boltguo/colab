import {
  Alert,
  Button,
  Card,
  ChoiceButton,
  ClearOutlined,
  DeleteOutlined,
  Empty,
  ExperimentOutlined,
  FieldLabel,
  GenerateButton,
  HistoryOutlined,
  ImageCompareStage,
  ImageSourceField,
  InfoCircleOutlined,
  InputNumber,
  LockOutlined,
  PictureOutlined,
  Popconfirm,
  Progress,
  ScrollArea,
  SeedControl,
  Segmented,
  Select,
  Slider,
  Space,
  StudioShell,
  Switch,
  Tag,
  Text,
  ThunderboltOutlined,
  VideoCameraOutlined,
  resolveApiUrl,
  useHistoryStore,
  useStudioFeedback,
  useStudioLocale,
  useTaskRunner,
} from "@colab/shared";
import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { VideoCompareStage } from "./VideoCompareStage";
import type { VideoSourceMeta } from "./VideoInputCard";
import { VideoInputCard } from "./VideoInputCard";
import { buildUpscaleStudioRequest, type SeedVR2StudioRequest } from "./request";
import type {
  CropMode,
  ImageOutputFormat,
  SeedVR2Mode,
  SeedVR2ModelVariant,
  SeedVR2Params,
  SeedVR2Result,
  SizingMode,
  VideoOutputFormat,
} from "./types";
import { DEFAULT_SEEDVR2_PARAMS, computeTargetDimensions } from "./types";

const SCALE_PRESETS_VIDEO = [1.5, 2.0, 3.0, 4.0];
const SCALE_PRESETS_IMAGE = [2.0, 3.0, 4.0, 6.0];
const SHORTER_EDGE_PRESETS = [
  { label: "1080P (1080)", value: 1080 },
  { label: "2K QHD (1440)", value: 1440 },
  { label: "4K UHD (2160)", value: 2160 },
];
const LONGER_EDGE_PRESETS = [
  { label: "FHD (1920)", value: 1920 },
  { label: "2.5K (2560)", value: 2560 },
  { label: "4K (3840)", value: 3840 },
  { label: "DCI 4K (4096)", value: 4096 },
];

export function SeedVR2StudioApp() {
  const { t } = useStudioLocale();
  const scaleInputId = useId();
  const shortEdgeInputId = useId();
  const longEdgeInputId = useId();
  const customWidthId = useId();
  const customHeightId = useId();
  const outputFormatId = useId();

  const { message } = useStudioFeedback();

  const [params, setParams] = useState<SeedVR2Params>(DEFAULT_SEEDVR2_PARAMS);
  const [videoFileRef, setVideoFileRef] = useState("");
  const [imageFileRef, setImageFileRef] = useState("");
  const [videoSourceMeta, setVideoSourceMeta] = useState<VideoSourceMeta | null>(null);
  const [imageSourceDims, setImageSourceDims] = useState<{ w: number; h: number } | null>(null);

  const [seedLocked, setSeedLocked] = useState(false);
  const [selectedTakeId, setSelectedTakeId] = useState<string | null>(null);

  const { items: historyItems, addEntry, clearAll } = useHistoryStore<
    SeedVR2Result,
    SeedVR2Params
  >("seedvr2", 24);

  const activeInputRef = params.mode === "video" ? videoFileRef : imageFileRef;

  const effectivePayload = useMemo(
    () => buildUpscaleStudioRequest(params, activeInputRef || "<YOUR_UPLOADED_FILE_ID>"),
    [params, activeInputRef],
  );

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<
    SeedVR2Result,
    SeedVR2StudioRequest
  >({
    endpointPath: "/api/v1/generate",
    onSuccess: (finishedTask) => {
      if (finishedTask.result) {
        addEntry({
          id: finishedTask.task_id,
          feature: "seedvr2",
          createdAt: finishedTask.finished_at || new Date().toISOString(),
          elapsedSec: finishedTask.elapsed_sec,
          params: { ...DEFAULT_SEEDVR2_PARAMS, ...finishedTask.params },
          result: finishedTask.result,
        });
        setSelectedTakeId(finishedTask.task_id);
        if (seedLocked && finishedTask.result.used_seed) {
          setParams((prev) => ({ ...prev, seed: finishedTask.result!.used_seed }));
        }
        message.success(
          t(
            `Upscale completed: ${finishedTask.result.input_width}×${finishedTask.result.input_height} → ${finishedTask.result.width}×${finishedTask.result.height}`,
            `超分完成：${finishedTask.result.input_width}×${finishedTask.result.input_height} → ${finishedTask.result.width}×${finishedTask.result.height}`,
          ),
        );
      }
    },
    onError: (errMsg) => {
      message.error(errMsg);
    },
  });

  const updateParam = useCallback(
    <K extends keyof SeedVR2Params>(key: K, val: SeedVR2Params[K]) => {
      setParams((prev) => ({ ...prev, [key]: val }));
    },
    []
  );

  const handleModeSwitch = useCallback((nextMode: SeedVR2Mode) => {
    setParams((prev) => {
      if (prev.mode === nextMode) return prev;
      let nextScale = prev.scale_factor;
      if (prev.sizing_mode === "multiplier") {
        if (nextMode === "image" && prev.scale_factor === 2.0) {
          nextScale = 4.0;
        } else if (nextMode === "video" && prev.scale_factor === 4.0) {
          nextScale = 2.0;
        }
      }
      return {
        ...prev,
        mode: nextMode,
        scale_factor: nextScale,
      };
    });
  }, []);

  const handleVariantSwitch = useCallback((nextVariant: SeedVR2ModelVariant) => {
    setParams((prev) => ({
      ...prev,
      model_variant: nextVariant,
      split_latent:
        prev.mode === "video" && nextVariant === "3b_fast" ? true : prev.split_latent,
    }));
  }, []);

  const activeSourceDims = useMemo(() => {
    if (params.mode === "video") {
      return videoSourceMeta && videoSourceMeta.w > 0 && videoSourceMeta.h > 0
        ? { w: videoSourceMeta.w, h: videoSourceMeta.h }
        : null;
    }
    return imageSourceDims && imageSourceDims.w > 0 && imageSourceDims.h > 0
      ? imageSourceDims
      : null;
  }, [params.mode, videoSourceMeta, imageSourceDims]);

  const previewTarget = useMemo(() => {
    const base = activeSourceDims || (params.mode === "video" ? { w: 960, h: 540 } : { w: 1024, h: 1024 });
    const calc = computeTargetDimensions(base.w, base.h, params);
    const megapixels = ((calc.width * calc.height) / 1_000_000).toFixed(2);
    return {
      srcW: base.w,
      srcH: base.h,
      isExample: !activeSourceDims,
      ...calc,
      megapixels,
    };
  }, [activeSourceDims, params]);

  const validationMessage = useMemo(() => {
    if (params.sizing_mode === "dimensions" && !params.target_width && !params.target_height) {
      return t(
        "Target width and height cannot both be 0; set at least one dimension.",
        "目标宽度与高度不能同时为 0，请至少设置一个尺寸。",
      );
    }
    if (activeSourceDims && Math.max(previewTarget.width, previewTarget.height) > 16384) {
      return t(
        "Target dimension exceeds 16,384 px per side; reduce scale factor or target size.",
        "目标尺寸超出单边 16384 像素上限，请降低放大倍数或目标尺寸。",
      );
    }
    return "";
  }, [params, activeSourceDims, previewTarget, t]);

  const handleGenerate = useCallback(async () => {
    if (isBusy) return;
    if (validationMessage) {
      message.warning(validationMessage);
      return;
    }
    if (!activeInputRef.trim()) {
      message.warning(
        params.mode === "video"
          ? t("Please upload a source video to upscale.", "请先上传待超分的源视频文件。")
          : t("Please upload a source image to upscale.", "请先上传待超分的源图片文件。"),
      );
      return;
    }
    const payload = buildUpscaleStudioRequest(params, activeInputRef);
    await runTask(payload);
  }, [isBusy, activeInputRef, params, message, runTask, t, validationMessage]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        void handleGenerate();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleGenerate]);

  const displayedEntry = useMemo(() => {
    if (selectedTakeId) {
      const found = historyItems.find((x) => x.id === selectedTakeId);
      if (found) return found;
    }
    return historyItems[0] || null;
  }, [historyItems, selectedTakeId]);

  const stageOutputUrl = displayedEntry
    ? resolveApiUrl(displayedEntry.result.output_url)
    : "";
  const stageDownloadUrl = displayedEntry
    ? resolveApiUrl(`${displayedEntry.result.output_url}?download=1`)
    : "";
  const stageInputUrl = displayedEntry?.result.input_url
    ? resolveApiUrl(displayedEntry.result.input_url)
    : "";

  const leftPane = (
    <>
      <Card
        className="studio-card"
        title={
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
            <Segmented
              value={params.mode}
              onChange={(val) => handleModeSwitch(val as SeedVR2Mode)}
              options={[
                {
                  label: t("Video Upscale", "视频画质超分"),
                  value: "video",
                  icon: <VideoCameraOutlined />,
                },
                {
                  label: t("Image 4K Upscale", "图片 4K 超分"),
                  value: "image",
                  icon: <PictureOutlined />,
                },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12.5, fontWeight: 400 }}>
              {params.mode === "video"
                ? t("Preserves original audio & FPS · Temporal chunking", "保留原声与帧率 · 支持时间分块")
                : t("Single-image 4K detail restoration · Alpha preserved", "单图 4K 细节重绘 · 保留透明通道")}
            </Text>
          </div>
        }
        extra={
          <Button
            htmlType="button"
            size="small"
            type="text"
            icon={<ClearOutlined />}
            onClick={() => {
              setParams((prev) => ({
                ...DEFAULT_SEEDVR2_PARAMS,
                mode: prev.mode,
                scale_factor: prev.mode === "image" ? 4.0 : 2.0,
              }));
              message.info(t("Restored recommended upscale defaults", "已恢复推荐默认超分参数"));
            }}
          >
            {t("Reset", "恢复默认")}
          </Button>
        }
      >
        {params.mode === "video" ? (
          <VideoInputCard
            label={t("Source Video", "待超分源视频")}
            badgeText="MP4 / WebM / MOV / MKV"
            value={videoFileRef}
            onChange={setVideoFileRef}
            onMetadataChange={setVideoSourceMeta}
          />
        ) : (
          <ImageSourceField
            label={t("Source Image", "待超分源图片")}
            badgeText="PNG / JPG / WebP"
            value={imageFileRef}
            onChange={setImageFileRef}
            onDimensionsChange={setImageSourceDims}
          />
        )}
      </Card>

      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <ThunderboltOutlined style={{ color: "var(--studio-accent)" }} />
            <span>{t("Model & Sizing", "模型与尺寸")}</span>
          </Space>
        }
        extra={
          <Tag color="processing" className="studio-tabular" style={{ marginInlineEnd: 0 }}>
            {t("Proportional upscale", "按原图比例放大")}
          </Tag>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div className="studio-field-group">
            <FieldLabel
              label={t("Model", "模型")}
              tooltip={t(
                "7B Sharp (15.35 GB FP16) maximizes texture & skin/hair crispness; 3B Fast (6.32 GB) excels on long videos and 40GB GPUs.",
                "7B Sharp 拥有 15.35GB FP16 权重，人像肤质、毛发与建筑锐度最高；3B Fast 仅 6.32GB，适合长视频高吞吐与 40GB 显卡快速超分。",
              )}
            />
            <div className="studio-image-slot-grid">
              <ChoiceButton
                type="button"
                align="start"
                className="studio-aspect-pill"
                active={params.model_variant === "7b_sharp"}
                style={{
                  padding: "0.65rem 0.9rem",
                  minBlockSize: 68,
                }}
                onClick={() => handleVariantSwitch("7b_sharp")}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", inlineSize: "100%", gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 13.5 }}>{t("7B Sharp · Best Detail", "7B Sharp · 清晰优先")}</span>
                </div>
                <span style={{ fontSize: 12, opacity: 0.8 }}>
                  {t("Highest fidelity & micro-texture restoration", "适合细节修复和高品质放大")}
                </span>
              </ChoiceButton>

              <ChoiceButton
                type="button"
                align="start"
                className="studio-aspect-pill"
                active={params.model_variant === "3b_fast"}
                style={{
                  padding: "0.65rem 0.9rem",
                  minBlockSize: 68,
                }}
                onClick={() => handleVariantSwitch("3b_fast")}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", inlineSize: "100%", gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 13.5 }}>{t("3B Fast · Speed Priority", "3B Fast · 速度优先")}</span>
                </div>
                <span style={{ fontSize: 12, opacity: 0.8 }}>
                  {t("Best for long videos & faster throughput", "适合长视频与快速处理")}
                </span>
              </ChoiceButton>
            </div>
          </div>

          <div className="studio-field-group">
            <FieldLabel
              label={t("Resize Mode", "调整尺寸")}
              tooltip={t(
                "Upscale by factor, lock standard shorter edge (1080P/2K/4K), lock longer edge, or set exact dimensions.",
                "支持按倍数等比放大、锁定标准短边档位（如 1080P/2K/4K）、锁定长边像素或指定精确宽高。",
              )}
            />
            <Segmented
              block
              value={params.sizing_mode}
              onChange={(val) => updateParam("sizing_mode", val as SizingMode)}
              options={[
                { label: t("Scale", "倍数"), value: "multiplier" },
                { label: t("Short Edge", "短边"), value: "shorter_edge" },
                { label: t("Long Edge", "长边"), value: "longer_edge" },
                { label: t("Custom", "自定义"), value: "dimensions" },
              ]}
            />
          </div>

          <div className="studio-dim-bar">
            {params.sizing_mode === "multiplier" && (
              <div className="studio-field-group" style={{ flex: "1 1 280px" }}>
                <FieldLabel label={t("Scale Factor", "等比放大倍数 (Scale Factor)")} htmlFor={scaleInputId} />
                <div className="studio-preset-field">
                  <Segmented
                    size="small"
                    variant="tonal"
                    aria-label={t("Scale presets", "等比放大倍数预设")}
                    value={params.scale_factor}
                    onChange={(value) => updateParam("scale_factor", Number(value))}
                    options={(params.mode === "image" ? SCALE_PRESETS_IMAGE : SCALE_PRESETS_VIDEO).map(
                      (preset) => ({ label: `${preset}x`, value: preset })
                    )}
                  />
                  <InputNumber
                    id={scaleInputId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 176 }}
                    min={1.0}
                    max={8.0}
                    step={0.25}
                    addonAfter="x"
                    value={params.scale_factor}
                    onChange={(v) =>
                      updateParam("scale_factor", Math.max(1.0, Math.min(8.0, Number(v || 2.0))))
                    }
                  />
                </div>
              </div>
            )}

            {params.sizing_mode === "shorter_edge" && (
              <div className="studio-field-group" style={{ flex: "1 1 320px" }}>
                <FieldLabel label={t("Target Shorter Edge (px)", "目标短边像素 (Shorter Edge)")} htmlFor={shortEdgeInputId} />
                <div className="studio-preset-field">
                  <Segmented
                    size="small"
                    variant="tonal"
                    aria-label={t("Short edge presets", "目标短边预设")}
                    value={params.target_shorter_edge}
                    onChange={(value) => updateParam("target_shorter_edge", Number(value))}
                    options={SHORTER_EDGE_PRESETS.map((preset) => ({ label: preset.label, value: preset.value }))}
                  />
                  <InputNumber
                    id={shortEdgeInputId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 176 }}
                    min={128}
                    max={8192}
                    step={16}
                    addonAfter="px"
                    value={params.target_shorter_edge}
                    onChange={(v) =>
                      updateParam(
                        "target_shorter_edge",
                        Math.max(128, Math.min(8192, Math.round(Number(v || 1440))))
                      )
                    }
                  />
                </div>
              </div>
            )}

            {params.sizing_mode === "longer_edge" && (
              <div className="studio-field-group" style={{ flex: "1 1 320px" }}>
                <FieldLabel label={t("Target Longer Edge (px)", "目标长边像素 (Longer Edge)")} htmlFor={longEdgeInputId} />
                <div className="studio-preset-field">
                  <Segmented
                    size="small"
                    variant="tonal"
                    aria-label={t("Long edge presets", "目标长边预设")}
                    value={params.target_longer_edge}
                    onChange={(value) => updateParam("target_longer_edge", Number(value))}
                    options={LONGER_EDGE_PRESETS.map((preset) => ({ label: preset.label, value: preset.value }))}
                  />
                  <InputNumber
                    id={longEdgeInputId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 176 }}
                    min={128}
                    max={8192}
                    step={16}
                    addonAfter="px"
                    value={params.target_longer_edge}
                    onChange={(v) =>
                      updateParam(
                        "target_longer_edge",
                        Math.max(128, Math.min(8192, Math.round(Number(v || 3840))))
                      )
                    }
                  />
                </div>
              </div>
            )}

            {params.sizing_mode === "dimensions" && (
              <div className="studio-field-group" style={{ flex: "1 1 360px" }}>
                <FieldLabel
                  label={t("Exact Target Width × Height (0 = auto aspect)", "精确目标宽 × 高 (0 = 按原比例自适应)")}
                  htmlFor={customWidthId}
                />
                <Space wrap size={8}>
                  <InputNumber
                    id={customWidthId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 176 }}
                    min={0}
                    max={8192}
                    step={16}
                    addonBefore={t("W", "宽")}
                    value={params.target_width}
                    onChange={(v) =>
                      updateParam(
                        "target_width",
                        Math.max(0, Math.min(8192, Math.round(Number(v ?? 0))))
                      )
                    }
                  />
                  <Text type="secondary">×</Text>
                  <label htmlFor={customHeightId} className="studio-visually-hidden">
                    {t("Target height in pixels", "目标高度像素")}
                  </label>
                  <InputNumber
                    id={customHeightId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 176 }}
                    min={0}
                    max={8192}
                    step={16}
                    addonBefore={t("H", "高")}
                    value={params.target_height}
                    onChange={(v) =>
                      updateParam(
                        "target_height",
                        Math.max(0, Math.min(8192, Math.round(Number(v ?? 0))))
                      )
                    }
                  />
                  <Select
                    size="small"
                    style={{ inlineSize: 150 }}
                    value={params.crop_mode}
                    onChange={(v) => updateParam("crop_mode", v as CropMode)}
                    options={[
                      { label: t("Center Crop", "居中裁切保比例"), value: "center" },
                      { label: t("Stretch to Fit", "强制拉伸填充"), value: "disabled" },
                    ]}
                  />
                </Space>
              </div>
            )}

            <div
              className="studio-tabular"
              style={{
                inlineSize: "100%",
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                paddingBlockStart: 8,
                borderBlockStart: "1px dashed var(--studio-border)",
                fontSize: 12.5,
              }}
            >
              <span style={{ color: "var(--studio-text-secondary)" }}>
                {previewTarget.isExample
                  ? t("Estimated example (updates on upload): ", "预估换算示例（上传后读取真实尺寸）：")
                  : t("Target dimensions: ", "实时尺寸换算：")}
                <strong>
                  {previewTarget.srcW} × {previewTarget.srcH}
                </strong>{" "}
                →{" "}
                <strong style={{ color: "var(--studio-accent)" }}>
                  {previewTarget.width} × {previewTarget.height} px
                </strong>
              </span>
              <Space size={6}>
                <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                  {t(`Scale ×${previewTarget.effectiveScale.toFixed(2)}`, `等效 ×${previewTarget.effectiveScale.toFixed(2)}`)}
                </Tag>
                <Tag style={{ marginInlineEnd: 0 }}>{previewTarget.megapixels} MP</Tag>
              </Space>
            </div>
          </div>
        </div>
      </Card>

      <Card
        className="studio-card"
        title={t("Generation Settings", "生成设置")}
        extra={
          params.mode === "video" && (
            <Switch
              label={t("Keep original audio", "保留原声")}
              checked={params.keep_audio}
              onChange={(value) => updateParam("keep_audio", value)}
              aria-label={t("Keep original audio", "保留原声")}
            />
          )
        }
      >
        <div className="studio-settings-grid">
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>{t("Steps", "步数")}</span>
              <span className="studio-tabular">{t(`${params.steps} step${params.steps === 1 ? "" : "s"}`, `${params.steps} 步`)}</span>
            </div>
            <Slider aria-label={t("Steps", "生成步数")} min={1} max={20} step={1} value={params.steps} onChange={(value) => updateParam("steps", value)} />
          </div>
          <div className="studio-field-group">
            <label htmlFor={outputFormatId} className="studio-field-label">
              <span>{t("Output Format", "输出格式")}</span>
            </label>
            <Select
              id={outputFormatId}
              aria-label={t("Output format", "输出格式")}
              value={params.mode === "video" ? params.video_output_format : params.image_output_format}
              options={
                params.mode === "video"
                  ? [{ label: "MP4", value: "mp4" }, { label: "WebM", value: "webm" }, { label: "MKV", value: "mkv" }]
                  : [{ label: "PNG", value: "png" }, { label: "WebP", value: "webp" }, { label: "JPEG", value: "jpeg" }]
              }
              onChange={(value) => {
                if (params.mode === "image") {
                  updateParam("image_output_format", value as ImageOutputFormat);
                  return;
                }
                const format = value as VideoOutputFormat;
                setParams((previous) => ({
                  ...previous,
                  video_output_format: format,
                  video_codec: format === "webm" && previous.video_codec === "h264" ? "auto" : previous.video_codec,
                }));
              }}
            />
          </div>
          <SeedControl
            value={params.seed}
            max={2147483647}
            onChange={(value) => updateParam("seed", value)}
            onLockedChange={setSeedLocked}
          />
        </div>
      </Card>

      {validationMessage && <Alert type="warning" showIcon message={validationMessage} />}

      <GenerateButton
        label={t("Start Upscale", "开始超分")}
        disabled={Boolean(validationMessage) || !activeInputRef.trim()}
        busy={isBusy}
        queued={activeTask?.status === "queued"}
        onCancel={() => void cancelActive()}
        onGenerate={() => void handleGenerate()}
      />
    </>
  );

  const rightPane = (
    <>
      {isBusy && activeTask && (
        <Card className="studio-card" size="small">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Space size={6}>
                <ExperimentOutlined style={{ color: "var(--studio-accent)" }} />
                <Text strong style={{ fontSize: 13 }}>
                  {activeTask.status === "queued"
                    ? t(`Queued (#${activeTask.queue_position || 1})`, `排队等待中（#${activeTask.queue_position || 1}）`)
                    : t("SeedVR2 rebuilding fine details", "SeedVR2 正在执行超分细节重建")}
                </Text>
              </Space>
              <Text strong className="studio-tabular" style={{ color: "var(--studio-accent)" }}>
                {Math.round(activeTask.progress * 100)}%
              </Text>
            </div>
            <Progress
              percent={Math.round(activeTask.progress * 100)}
              status="active"
              showInfo={false}
              size="small"
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {activeTask.stage || t("Scheduling Tiled VAE & SeedVR2 diffusion...", "正在调度 Tiled VAE 与 SeedVR2 扩散模型...")}
            </Text>
          </div>
        </Card>
      )}

      <Card
        className="studio-card"
        title={
          <Space size={8}>
            {displayedEntry?.result.media_type === "image" ? (
              <PictureOutlined style={{ color: "var(--studio-accent)" }} />
            ) : (
              <VideoCameraOutlined style={{ color: "var(--studio-accent)" }} />
            )}
            <span>{t("Before / After A/B Inspector", "超分前后 A/B 对比检视台")}</span>
          </Space>
        }
        extra={
          displayedEntry?.result.mock ? (
            <Tag color="warning" style={{ marginInlineEnd: 0 }}>
              {t("Mock Preview", "本地 Mock 预览")}
            </Tag>
          ) : displayedEntry?.result ? (
            <Tag color="success" style={{ marginInlineEnd: 0 }}>
              {t("GPU Upscaled", "GPU 真实超分")}
            </Tag>
          ) : null
        }
      >
        {!displayedEntry || !stageOutputUrl ? (
          <Empty
            title={t("Ready to Upscale", "等待超分任务完成")}
            description={t(
              "Upload a video or image, pick your target sizing mode, then click Start Upscale for interactive A/B wipe inspection.",
              "上传视频或图片并选择放大策略后点击开始超分，完成后可拖拽卷帘实时对比细节。",
            )}
            icon={params.mode === "video" ? <VideoCameraOutlined /> : <PictureOutlined />}
            shape="flower"
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            {displayedEntry.result.media_type === "video" ? (
              <VideoCompareStage
                result={displayedEntry.result}
                outputUrl={stageOutputUrl}
                downloadUrl={stageDownloadUrl}
                inputUrl={stageInputUrl || undefined}
                referenceFit={
                  displayedEntry.params.sizing_mode === "dimensions"
                    ? displayedEntry.params.crop_mode === "center"
                      ? "cover"
                      : "fill"
                    : "contain"
                }
                onUseAsInput={() => {
                  const outRef = `output:${displayedEntry.result.filename}`;
                  setVideoFileRef(outRef);
                  setVideoSourceMeta({
                    w: displayedEntry.result.width,
                    h: displayedEntry.result.height,
                    dur: displayedEntry.result.duration_sec || 0,
                  });
                  handleModeSwitch("video");
                  message.success(t("Loaded upscaled video as new input source", "已将该超分视频挂载为新的源视频"));
                }}
              />
            ) : (
              <ImageCompareStage
                images={[
                  {
                    url: stageOutputUrl,
                    filename: displayedEntry.result.filename,
                    width: displayedEntry.result.width,
                    height: displayedEntry.result.height,
                    sizeBytes: displayedEntry.result.size_bytes,
                    format: displayedEntry.result.format,
                  },
                ]}
                referenceUrl={stageInputUrl || undefined}
                referenceLabel={t(
                  `Original (${displayedEntry.result.input_width}×${displayedEntry.result.input_height})`,
                  `超分前原图 (${displayedEntry.result.input_width}×${displayedEntry.result.input_height})`,
                )}
                resultLabel={t(
                  `SeedVR2 (${displayedEntry.result.width}×${displayedEntry.result.height})`,
                  `SeedVR2 超分 (${displayedEntry.result.width}×${displayedEntry.result.height})`,
                )}
                useAsReferenceLabel={t("Use as Input", "设为源图继续放大")}
                onUseAsReference={(img) => {
                  const outRef = `output:${img.filename}`;
                  setImageFileRef(outRef);
                  setImageSourceDims({ w: img.width, h: img.height });
                  handleModeSwitch("image");
                  message.success(t("Loaded upscaled image as new input source", "已将该超分图挂载为新的源图片"));
                }}
              />
            )}

            {displayedEntry.result.warnings?.map((w, idx) => (
              <Alert key={idx} type="info" showIcon icon={<InfoCircleOutlined />} message={w} />
            ))}

            <div className="studio-meta-bar">
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.4rem" }}>
                <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                  {displayedEntry.result.model_variant === "7b_sharp" ? "7B Sharp" : "3B Fast"}
                </Tag>
                <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                  {displayedEntry.result.input_width}×{displayedEntry.result.input_height} →{" "}
                  {displayedEntry.result.width}×{displayedEntry.result.height} (×
                  {displayedEntry.result.effective_scale})
                </Tag>
                <Tag style={{ marginInlineEnd: 0 }}>
                  {t(`Color: ${displayedEntry.result.color_correction.toUpperCase()}`, `追色: ${displayedEntry.result.color_correction.toUpperCase()}`)}
                </Tag>
                {displayedEntry.result.media_type === "video" && (
                  <Tag
                    color={displayedEntry.result.has_audio ? "success" : "default"}
                    style={{ marginInlineEnd: 0 }}
                  >
                    {displayedEntry.result.has_audio ? t("Audio Kept", "原声保留") : t("Muted", "无音轨")}
                  </Tag>
                )}
                {displayedEntry.result.split_latent && (
                  <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                    Split Latent
                  </Tag>
                )}
                <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                  {t(`${displayedEntry.result.steps} steps`, `${displayedEntry.result.steps} 步`)} · CFG {displayedEntry.result.cfg}
                </Tag>
              </div>

              <Button
                htmlType="button"
                size="small"
                icon={<LockOutlined />}
                onClick={() => {
                  setSeedLocked(true);
                  updateParam("seed", displayedEntry.result.used_seed);
                  message.success(t(`Locked seed: ${displayedEntry.result.used_seed}`, `已锁定种子：${displayedEntry.result.used_seed}`));
                }}
              >
                {t("Use this seed", "使用此种子")}
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
            <span>{t(`Session History (${historyItems.length})`, `本次会话超分历史（${historyItems.length}）`)}</span>
          </Space>
        }
        extra={
          historyItems.length > 0 && (
            <Popconfirm
              title={t("Clear session upscale history?", "清空当前会话超分记录？")}
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
              "Completed video and image upscales appear here so you can compare results or restore parameters.",
              "本次会话完成的视频与图片超分记录会自动保存在此，支持随时切换对比或一键回填全部参数。",
            )}
          </Text>
        ) : (
          <ScrollArea maxHeight={420}>
            <div className="studio-video-history-list" style={{ paddingInlineEnd: 8 }}>
              {historyItems.map((item) => {
                const isSelected = displayedEntry?.id === item.id;
                const mediaSrc = resolveApiUrl(item.result.output_url);
                const isVideo = item.result.media_type === "video";
                const titleText = `${
                  isVideo ? t("Video Upscale", "视频超分") : t("Image Upscale", "图片超分")
                } · ${
                  item.result.model_variant === "7b_sharp" ? "7B Sharp" : "3B Fast"
                } (×${item.result.effective_scale})`;

                return (
                  <div
                    key={item.id}
                    className="studio-video-history-card"
                    data-active={isSelected ? "true" : "false"}
                  >
                    {isVideo ? (
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
                    ) : (
                      <img
                        src={mediaSrc}
                        alt={titleText}
                        loading="lazy"
                        width={148}
                        height={84}
                        style={{
                          inlineSize: "100%",
                          aspectRatio: "16 / 9",
                          objectFit: "cover",
                          borderRadius: 6,
                          background: "var(--m3e-color-surface-container-lowest)",
                          border: "1px solid var(--studio-border)",
                        }}
                      />
                    )}

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
                        <div
                          style={{
                            fontSize: 12.5,
                            fontWeight: 600,
                            color: "var(--studio-text)",
                          }}
                        >
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
                        <span
                          className="studio-tabular"
                          style={{ fontSize: 11.5, color: "var(--studio-text-muted)" }}
                        >
                          {item.result.input_width}×{item.result.input_height} → {item.result.width}
                          ×{item.result.height}
                        </span>

                        <Button
                          htmlType="button"
                          size="small"
                          type="link"
                          style={{ padding: 0, blockSize: "auto", fontSize: 12 }}
                          onClick={() => {
                            setParams({ ...DEFAULT_SEEDVR2_PARAMS, ...buildUpscaleStudioRequest(item.params) });
                            setSeedLocked(item.params.seed > 0);
                            if (item.params.mode === "video") {
                              setVideoFileRef(item.params.input_file);
                              setVideoSourceMeta({ w: item.result.input_width, h: item.result.input_height, dur: 0 });
                            } else {
                              setImageFileRef(item.params.input_file);
                              setImageSourceDims({ w: item.result.input_width, h: item.result.input_height });
                            }
                            message.info(t("Restored settings from history", "已恢复常用超分设置"));
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
      brandBadge="VR2"
      defaultTitle="SeedVR2"
      defaultSubtitle={t(
        "Video & Image Super-Resolution · 7B Sharp or 3B Fast",
        "视频与图片超分 · 清晰优先或速度优先",
      )}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
