import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ClearOutlined,
  ControlOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  ImageCompareStage,
  ImageSourceField,
  InfoCircleOutlined,
  InputNumber,
  LockOutlined,
  PictureOutlined,
  Popconfirm,
  Progress,
  QuestionCircleOutlined,
  ReloadOutlined,
  RocketOutlined,
  Segmented,
  Select,
  Slider,
  Space,
  StudioShell,
  Switch,
  Tag,
  Text,
  ThunderboltOutlined,
  Tooltip,
  UnlockOutlined,
  VideoCameraOutlined,
  resolveApiUrl,
  triggerModelRelease,
  useHistoryStore,
  useStudioFeedback,
  useTaskRunner,
} from "@colab/shared";
import { VideoCompareStage } from "./VideoCompareStage";
import { VideoInputCard } from "./VideoInputCard";
import type { VideoSourceMeta } from "./VideoInputCard";
import {
  DEFAULT_SEEDVR2_PARAMS,
  alignChunkFrames,
  computeTargetDimensions,
} from "./types";
import type {
  BitDepthChoice,
  ChunkingMode,
  ColorCorrectionMethod,
  ColorSpaceChoice,
  CropMode,
  ImageOutputFormat,
  SamplerName,
  SchedulerName,
  SeedVR2Mode,
  SeedVR2ModelVariant,
  SeedVR2Params,
  SeedVR2Result,
  SizingMode,
  UnetWeightDtype,
  UpscaleInterpolation,
  VideoCodecChoice,
  VideoOutputFormat,
} from "./types";

function FieldLabel({ label, tooltip, htmlFor }: { label: string; tooltip?: string; htmlFor?: string }) {
  const inner = (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      {label}
      {tooltip && (
        <Tooltip title={tooltip}>
          <QuestionCircleOutlined style={{ color: "var(--studio-text-muted)", fontSize: 13 }} />
        </Tooltip>
      )}
    </span>
  );
  return (
    <div className="studio-field-label">
      {htmlFor ? <label htmlFor={htmlFor}>{inner}</label> : inner}
    </div>
  );
}

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
const CHUNK_FRAME_PRESETS = [9, 13, 17, 21, 25, 33, 49];

export function SeedVR2StudioApp() {
  const scaleInputId = useId();
  const shortEdgeInputId = useId();
  const longEdgeInputId = useId();
  const customWidthId = useId();
  const customHeightId = useId();
  const seedInputId = useId();

  const { message } = useStudioFeedback();

  const [params, setParams] = useState<SeedVR2Params>(DEFAULT_SEEDVR2_PARAMS);
  const [videoFileRef, setVideoFileRef] = useState("");
  const [imageFileRef, setImageFileRef] = useState("");
  const [videoSourceMeta, setVideoSourceMeta] = useState<VideoSourceMeta | null>(null);
  const [imageSourceDims, setImageSourceDims] = useState<{ w: number; h: number } | null>(null);

  const [seedLocked, setSeedLocked] = useState(false);
  const [releasingVram, setReleasingVram] = useState(false);
  const [selectedTakeId, setSelectedTakeId] = useState<string | null>(null);

  const { items: historyItems, addEntry, clearAll } = useHistoryStore<
    SeedVR2Result,
    SeedVR2Params
  >("seedvr2", 24);

  const activeInputRef = params.mode === "video" ? videoFileRef : imageFileRef;

  const effectivePayload = useMemo<SeedVR2Params>(
    () => ({
      ...params,
      input_file: activeInputRef || "<YOUR_UPLOADED_FILE_ID>",
      frames_per_chunk: alignChunkFrames(params.frames_per_chunk),
    }),
    [params, activeInputRef]
  );

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<
    SeedVR2Result,
    SeedVR2Params
  >({
    endpointPath: "/api/v1/generate",
    onSuccess: (finishedTask) => {
      if (finishedTask.result) {
        addEntry({
          id: finishedTask.task_id,
          feature: "seedvr2",
          createdAt: finishedTask.finished_at || new Date().toISOString(),
          elapsedSec: finishedTask.elapsed_sec,
          params: finishedTask.params,
          result: finishedTask.result,
        });
        setSelectedTakeId(finishedTask.task_id);
        if (seedLocked && finishedTask.result.used_seed) {
          setParams((prev) => ({ ...prev, seed: finishedTask.result!.used_seed }));
        }
        message.success(
          `超分完成：${finishedTask.result.input_width}×${finishedTask.result.input_height} → ${finishedTask.result.width}×${finishedTask.result.height}`
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
      return "目标宽度与高度不能同时为 0，请至少设置一个尺寸。";
    }
    if (activeSourceDims && Math.max(previewTarget.width, previewTarget.height) > 16384) {
      return "目标尺寸超出单边 16384 像素上限，请降低放大倍数或目标尺寸。";
    }
    if (params.mode === "video") {
      if (params.trim_video && videoSourceMeta?.dur && params.start_time >= videoSourceMeta.dur) {
        return `截取起点必须早于视频结束时间（${videoSourceMeta.dur.toFixed(2)} 秒）。`;
      }
      if (params.fps_override > 0 && params.fps_override < 1) {
        return "播放帧率请设为 0（原速）或 1~120 FPS。";
      }
      if (params.fps_override > 0 && params.keep_audio) {
        return "修改播放帧率会改变视频速度；请关闭保留原声，或将播放帧率设为 0。";
      }
    }
    return "";
  }, [params, activeSourceDims, previewTarget, videoSourceMeta]);

  const handleGenerate = useCallback(async () => {
    if (isBusy) return;
    if (validationMessage) {
      message.warning(validationMessage);
      return;
    }
    if (!activeInputRef.trim()) {
      message.warning(
        params.mode === "video"
          ? "请先上传待超分的源视频文件。"
          : "请先上传待超分的源图片文件。"
      );
      return;
    }
    const payload: SeedVR2Params = {
      ...params,
      input_file: activeInputRef.trim(),
      frames_per_chunk: alignChunkFrames(params.frames_per_chunk),
    };
    await runTask(payload);
  }, [isBusy, activeInputRef, params, message, runTask, validationMessage]);

  // Global Cmd/Ctrl + Enter shortcut
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

  const handleManualReleaseVram = async () => {
    setReleasingVram(true);
    try {
      await triggerModelRelease();
      message.success("已向推理引擎发送 GPU 显存卸载与回收指令");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "显存释放失败");
    } finally {
      setReleasingVram(false);
    }
  };

  const resetEngineDefaults = () => {
    setParams((prev) => ({
      ...prev,
      unet_weight_dtype: DEFAULT_SEEDVR2_PARAMS.unet_weight_dtype,
      vae_tile_size: DEFAULT_SEEDVR2_PARAMS.vae_tile_size,
      vae_tile_overlap: DEFAULT_SEEDVR2_PARAMS.vae_tile_overlap,
      vae_temporal_size: DEFAULT_SEEDVR2_PARAMS.vae_temporal_size,
      vae_temporal_overlap: DEFAULT_SEEDVR2_PARAMS.vae_temporal_overlap,
      fps_override: DEFAULT_SEEDVR2_PARAMS.fps_override,
      video_codec: DEFAULT_SEEDVR2_PARAMS.video_codec,
      crf: DEFAULT_SEEDVR2_PARAMS.crf,
      color_space: DEFAULT_SEEDVR2_PARAMS.color_space,
      bit_depth: DEFAULT_SEEDVR2_PARAMS.bit_depth,
      image_quality: DEFAULT_SEEDVR2_PARAMS.image_quality,
      release_vram_after: DEFAULT_SEEDVR2_PARAMS.release_vram_after,
    }));
    message.info("已恢复底层 Tiled VAE 与编码引擎推荐参数");
  };

  const displayedEntry = useMemo(() => {
    if (selectedTakeId) {
      const found = historyItems.find((x) => x.id === selectedTakeId);
      if (found) return found;
    }
    return historyItems[0] || null;
  }, [historyItems, selectedTakeId]);

  const stageOutputUrl = displayedEntry
    ? resolveApiUrl(displayedEntry.result.output_url, true)
    : "";
  const stageDownloadUrl = displayedEntry
    ? resolveApiUrl(`${displayedEntry.result.output_url}?download=1`, true)
    : "";
  const stageInputUrl = displayedEntry?.result.input_url
    ? resolveApiUrl(displayedEntry.result.input_url, true)
    : "";

  const leftPane = (
    <>
      {/* 1. Mode & Source Media Card */}
      <Card
        className="studio-card"
        title={
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
            <Segmented
              value={params.mode}
              onChange={(val) => handleModeSwitch(val as SeedVR2Mode)}
              options={[
                {
                  label: "视频画质超分",
                  value: "video",
                  icon: <VideoCameraOutlined />,
                },
                {
                  label: "图片 4K 超分",
                  value: "image",
                  icon: <PictureOutlined />,
                },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12.5, fontWeight: 400 }}>
              {params.mode === "video"
                ? "保留原声与帧率 · 支持时间分块"
                : "单图 4K 细节重绘 · 保留透明通道"}
            </Text>
          </div>
        }
        extra={
          <Button
            htmlType="button"
            size="small"
            icon={<ClearOutlined />}
            onClick={() => {
              setParams((prev) => ({
                ...DEFAULT_SEEDVR2_PARAMS,
                mode: prev.mode,
                scale_factor: prev.mode === "image" ? 4.0 : 2.0,
              }));
              message.info("已恢复推荐默认超分参数");
            }}
          >
            恢复默认
          </Button>
        }
      >
        {params.mode === "video" ? (
          <VideoInputCard
            label="待超分源视频"
            badgeText="MP4 / WebM / MOV / MKV"
            value={videoFileRef}
            onChange={setVideoFileRef}
            onMetadataChange={setVideoSourceMeta}
          />
        ) : (
          <ImageSourceField
            label="待超分源图片"
            badgeText="PNG / JPG / WebP"
            value={imageFileRef}
            onChange={setImageFileRef}
            onDimensionsChange={setImageSourceDims}
          />
        )}
      </Card>

      {/* 2. Model Variant & Independent Target Resolution Card */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <ThunderboltOutlined style={{ color: "var(--studio-accent)" }} />
            <span>模型规格与输出分辨率控制</span>
          </Space>
        }
        extra={
          <Tag color="processing" className="studio-tabular" style={{ marginInlineEnd: 0 }}>
            输出对齐偶数像素 · Tiled VAE 防爆显存
          </Tag>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Model Variant Flat Cards */}
          <div className="studio-field-group">
            <FieldLabel
              label="SeedVR2 模型权重规格 (Model Variant)"
              tooltip="7B Sharp 拥有 15.35GB FP16 权重，人像肤质、毛发与建筑锐度最高；3B Fast 仅 6.32GB，适合长视频高吞吐与 40GB 显卡快速超分。"
            />
            <div className="studio-image-slot-grid">
              <button
                type="button"
                className="studio-aspect-pill"
                data-active={params.model_variant === "7b_sharp" ? "true" : "false"}
                style={{
                  alignItems: "flex-start",
                  textAlign: "start",
                  padding: "0.65rem 0.85rem",
                  minBlockSize: 68,
                }}
                onClick={() => handleVariantSwitch("7b_sharp")}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", inlineSize: "100%", gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 13.5 }}>7B Sharp · 旗舰细节锐化版</span>
                  <code className="studio-ref-badge">15.35 GB</code>
                </div>
                <span style={{ fontSize: 12, color: "var(--studio-text-muted)" }}>
                  最高频纹理重建精度，推荐 4K 图片超分与高品质短片精修
                </span>
              </button>

              <button
                type="button"
                className="studio-aspect-pill"
                data-active={params.model_variant === "3b_fast" ? "true" : "false"}
                style={{
                  alignItems: "flex-start",
                  textAlign: "start",
                  padding: "0.65rem 0.85rem",
                  minBlockSize: 68,
                }}
                onClick={() => handleVariantSwitch("3b_fast")}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", inlineSize: "100%", gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 13.5 }}>3B Fast · 长视频高吞吐版</span>
                  <code className="studio-ref-badge">6.32 GB</code>
                </div>
                <span style={{ fontSize: 12, color: "var(--studio-text-muted)" }}>
                  轻量高速推理，视频模式下自动联动开启时间分块省显存
                </span>
              </button>
            </div>
          </div>

          {/* Sizing Strategy Bar */}
          <div className="studio-field-group">
            <FieldLabel
              label="目标尺寸放大策略 (Target Sizing)"
              tooltip="支持按倍数等比放大、锁定标准短边档位（如 1080P/2K/4K）、锁定长边像素或指定精确宽高。"
            />
            <Segmented
              block
              value={params.sizing_mode}
              onChange={(val) => updateParam("sizing_mode", val as SizingMode)}
              options={[
                { label: "按放大倍数", value: "multiplier" },
                { label: "固定短边档位", value: "shorter_edge" },
                { label: "固定长边像素", value: "longer_edge" },
                { label: "自定义宽高", value: "dimensions" },
              ]}
            />
          </div>

          {/* Active Sizing Controls + Pre-Interpolation */}
          <div className="studio-dim-bar">
            {params.sizing_mode === "multiplier" && (
              <div className="studio-field-group" style={{ flex: "1 1 280px" }}>
                <FieldLabel label="等比放大倍数 (Scale Factor)" htmlFor={scaleInputId} />
                <Space wrap size={6}>
                  {(params.mode === "image" ? SCALE_PRESETS_IMAGE : SCALE_PRESETS_VIDEO).map(
                    (preset) => (
                      <Button
                        key={preset}
                        htmlType="button"
                        size="small"
                        type={params.scale_factor === preset ? "primary" : "default"}
                        ghost={params.scale_factor === preset}
                        className="studio-tabular"
                        onClick={() => updateParam("scale_factor", preset)}
                      >
                        {preset}x
                      </Button>
                    )
                  )}
                  <InputNumber
                    id={scaleInputId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 96 }}
                    min={1.0}
                    max={8.0}
                    step={0.25}
                    addonAfter="x"
                    value={params.scale_factor}
                    onChange={(v) =>
                      updateParam("scale_factor", Math.max(1.0, Math.min(8.0, Number(v || 2.0))))
                    }
                  />
                </Space>
              </div>
            )}

            {params.sizing_mode === "shorter_edge" && (
              <div className="studio-field-group" style={{ flex: "1 1 320px" }}>
                <FieldLabel label="目标短边像素 (Shorter Edge)" htmlFor={shortEdgeInputId} />
                <Space wrap size={6}>
                  {SHORTER_EDGE_PRESETS.map((p) => (
                    <Button
                      key={p.value}
                      htmlType="button"
                      size="small"
                      type={params.target_shorter_edge === p.value ? "primary" : "default"}
                      ghost={params.target_shorter_edge === p.value}
                      className="studio-tabular"
                      onClick={() => updateParam("target_shorter_edge", p.value)}
                    >
                      {p.label}
                    </Button>
                  ))}
                  <InputNumber
                    id={shortEdgeInputId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 112 }}
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
                </Space>
              </div>
            )}

            {params.sizing_mode === "longer_edge" && (
              <div className="studio-field-group" style={{ flex: "1 1 320px" }}>
                <FieldLabel label="目标长边像素 (Longer Edge)" htmlFor={longEdgeInputId} />
                <Space wrap size={6}>
                  {LONGER_EDGE_PRESETS.map((p) => (
                    <Button
                      key={p.value}
                      htmlType="button"
                      size="small"
                      type={params.target_longer_edge === p.value ? "primary" : "default"}
                      ghost={params.target_longer_edge === p.value}
                      className="studio-tabular"
                      onClick={() => updateParam("target_longer_edge", p.value)}
                    >
                      {p.label}
                    </Button>
                  ))}
                  <InputNumber
                    id={longEdgeInputId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 112 }}
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
                </Space>
              </div>
            )}

            {params.sizing_mode === "dimensions" && (
              <div className="studio-field-group" style={{ flex: "1 1 360px" }}>
                <FieldLabel
                  label="精确目标宽 × 高 (0 = 按原比例自适应)"
                  htmlFor={customWidthId}
                />
                <Space wrap size={8}>
                  <InputNumber
                    id={customWidthId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 118 }}
                    min={0}
                    max={8192}
                    step={16}
                    addonBefore="宽"
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
                    目标高度像素
                  </label>
                  <InputNumber
                    id={customHeightId}
                    size="small"
                    className="studio-tabular"
                    style={{ inlineSize: 118 }}
                    min={0}
                    max={8192}
                    step={16}
                    addonBefore="高"
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
                    style={{ inlineSize: 132 }}
                    value={params.crop_mode}
                    onChange={(v) => updateParam("crop_mode", v as CropMode)}
                    options={[
                      { label: "居中裁切保比例", value: "center" },
                      { label: "强制拉伸填充", value: "disabled" },
                    ]}
                  />
                </Space>
              </div>
            )}

            <div className="studio-field-group" style={{ minInlineSize: 176 }}>
              <FieldLabel
                label="预缩放插值核"
                tooltip="进入 SeedVR2 潜空间前的几何放大核：实拍与通用素材推荐 Lanczos，像素画推荐 Nearest-Exact。"
              />
              <Select
                size="small"
                value={params.upscale_interpolation}
                onChange={(v) => updateParam("upscale_interpolation", v as UpscaleInterpolation)}
                options={[
                  { label: "Lanczos (高频推荐)", value: "lanczos" },
                  { label: "Bicubic (三次立方)", value: "bicubic" },
                  { label: "Bilinear (双线性)", value: "bilinear" },
                  { label: "Area (像素面积)", value: "area" },
                  { label: "Nearest (像素风专用)", value: "nearest-exact" },
                ]}
              />
            </div>

            {/* Live Dimension Readout */}
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
                {previewTarget.isExample ? "预估换算示例（上传后读取真实尺寸）：" : "实时尺寸换算："}
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
                  等效 ×{previewTarget.effectiveScale.toFixed(2)}
                </Tag>
                <Tag style={{ marginInlineEnd: 0 }}>{previewTarget.megapixels} MP</Tag>
              </Space>
            </div>
          </div>
        </div>
      </Card>

      {/* 3. Color Correction, Temporal Chunking & Sampling Card */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <ControlOutlined style={{ color: "var(--studio-accent)" }} />
            <span>色彩追色、时间分块与扩散采样</span>
          </Space>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Color Correction */}
          <div className="studio-field-group">
            <FieldLabel
              label="后处理色彩对齐算法 (Color Correction)"
              tooltip="消除扩散超分轻微色偏：CIELAB 最忠实还原原片明度与色相；Wavelet 保留高频纹理同时对齐低频色调。"
            />
            <Segmented
              block
              value={params.color_correction}
              onChange={(val) => updateParam("color_correction", val as ColorCorrectionMethod)}
              options={[
                { label: "CIELAB 精准追色", value: "lab" },
                { label: "Wavelet 小波追色", value: "wavelet" },
                { label: "AdaIN 通道追色", value: "adain" },
                { label: "不追色 (none)", value: "none" },
              ]}
            />
          </div>

          {/* Modality-Specific Switches (Video vs Image) */}
          {params.mode === "video" ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 10,
                padding: "0.75rem 0.9rem",
                borderRadius: "0.65rem",
                background: "var(--studio-surface-subtle)",
                border: "1px solid var(--studio-border)",
              }}
            >
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                  gap: "0.65rem 1.15rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>无损保留原视频音轨</div>
                    <div style={{ fontSize: 11.5, color: "var(--studio-text-muted)" }}>
                      自动提取原声并混流进超分成片
                    </div>
                  </div>
                  <Switch
                    checked={params.keep_audio}
                    onChange={(v) => updateParam("keep_audio", v)}
                    aria-label="无损保留原视频音轨"
                  />
                </div>

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>长视频时间分块 (Split Latent)</div>
                    <div style={{ fontSize: 11.5, color: "var(--studio-text-muted)" }}>
                      Hann 窗平滑融合，防止长视频爆显存
                    </div>
                  </div>
                  <Switch
                    checked={params.split_latent}
                    onChange={(v) => updateParam("split_latent", v)}
                    aria-label="长视频时间分块省显存"
                  />
                </div>

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>截取片段试跑 (Trim Video)</div>
                    <div style={{ fontSize: 11.5, color: "var(--studio-text-muted)" }}>
                      先超分几秒样片快速检验参数效果
                    </div>
                  </div>
                  <Switch
                    checked={params.trim_video}
                    onChange={(v) => updateParam("trim_video", v)}
                    aria-label="截取片段试跑"
                  />
                </div>
              </div>

              {/* Inline Split Latent Parameters */}
              {params.split_latent && (
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "flex-end",
                    gap: "0.75rem 1rem",
                    paddingBlockStart: 8,
                    borderBlockStart: "1px dashed var(--studio-border)",
                  }}
                >
                  <div className="studio-field-group">
                    <FieldLabel label="时间分块模式" />
                    <Segmented
                      size="small"
                      value={params.chunking_mode}
                      onChange={(val) => updateParam("chunking_mode", val as ChunkingMode)}
                      options={[
                        { label: "自动显存感知 (auto)", value: "auto" },
                        { label: "手动固定帧数 (4n+1)", value: "manual" },
                      ]}
                    />
                  </div>

                  {params.chunking_mode === "manual" && (
                    <div className="studio-field-group">
                      <FieldLabel
                        label={`每块像素帧数 (自动对齐 ${alignChunkFrames(params.frames_per_chunk)} 帧)`}
                      />
                      <Space wrap size={5}>
                        {CHUNK_FRAME_PRESETS.map((f) => (
                          <Button
                            key={f}
                            htmlType="button"
                            size="small"
                            type={alignChunkFrames(params.frames_per_chunk) === f ? "primary" : "default"}
                            ghost={alignChunkFrames(params.frames_per_chunk) === f}
                            className="studio-tabular"
                            onClick={() => updateParam("frames_per_chunk", f)}
                          >
                            {f}
                          </Button>
                        ))}
                        <InputNumber
                          size="small"
                          className="studio-tabular"
                          style={{ inlineSize: 88 }}
                          min={5}
                          max={257}
                          step={4}
                          value={params.frames_per_chunk}
                          onChange={(v) =>
                            updateParam("frames_per_chunk", alignChunkFrames(Number(v || 21)))
                          }
                        />
                      </Space>
                    </div>
                  )}

                  <div className="studio-field-group" style={{ minInlineSize: 180 }}>
                    <FieldLabel
                      label="相邻块重叠潜帧数"
                      tooltip="重叠潜空间帧采用 Hann 窗交叉混合，默认 2 即可消除时间分块接缝闪烁。"
                    />
                    <InputNumber
                      size="small"
                      className="studio-tabular"
                      style={{ inlineSize: "100%" }}
                      min={0}
                      max={32}
                      step={1}
                      addonAfter="潜帧"
                      value={params.temporal_overlap}
                      onChange={(v) =>
                        updateParam(
                          "temporal_overlap",
                          Math.max(0, Math.min(32, Math.round(Number(v ?? 2))))
                        )
                      }
                    />
                  </div>
                </div>
              )}

              {/* Inline Trim Video Parameters */}
              {params.trim_video && (
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "flex-end",
                    gap: "0.75rem 1rem",
                    paddingBlockStart: 8,
                    borderBlockStart: "1px dashed var(--studio-border)",
                  }}
                >
                  <div className="studio-field-group" style={{ minInlineSize: 160 }}>
                    <FieldLabel label="起始时间 (Start)" />
                    <InputNumber
                      size="small"
                      className="studio-tabular"
                      style={{ inlineSize: "100%" }}
                      min={0}
                      max={7200}
                      step={0.5}
                      addonAfter="秒"
                      value={params.start_time}
                      onChange={(v) => updateParam("start_time", Math.max(0, Number(v || 0)))}
                    />
                  </div>
                  <div className="studio-field-group" style={{ minInlineSize: 190 }}>
                    <FieldLabel label="截取时长 (0 = 截取至片尾)" />
                    <InputNumber
                      size="small"
                      className="studio-tabular"
                      style={{ inlineSize: "100%" }}
                      min={0}
                      max={7200}
                      step={0.5}
                      addonAfter="秒"
                      value={params.duration}
                      onChange={(v) => updateParam("duration", Math.max(0, Number(v || 0)))}
                    />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
                padding: "0.65rem 0.9rem",
                borderRadius: "0.65rem",
                background: "var(--studio-surface-subtle)",
                border: "1px solid var(--studio-border)",
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>保留图片透明通道 (Preserve Alpha)</div>
                <div style={{ fontSize: 12, color: "var(--studio-text-muted)" }}>
                  对带透明底的 PNG / WebP 贴图同步放大 Alpha 遮罩并无损合成
                </div>
              </div>
              <Switch
                checked={params.preserve_alpha}
                onChange={(v) => updateParam("preserve_alpha", v)}
                aria-label="保留图片透明通道"
              />
            </div>
          )}

          {/* Core Diffusion Sampling Controls */}
          <div className="studio-param-grid">
            <div className="studio-field-group">
              <div className="studio-field-label">
                <FieldLabel
                  label="修复采样步数 (Steps)"
                  tooltip="SeedVR2 原生采用 1 步对抗蒸馏架构，默认 1 步即可获得最锐利细节且速度最快。"
                />
                <span className="studio-tabular" style={{ fontSize: 12.5, color: "var(--studio-accent)" }}>
                  {params.steps} 步
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <Slider
                    min={1}
                    max={20}
                    step={1}
                    value={params.steps}
                    onChange={(v) => updateParam("steps", v)}
                  />
                </div>
                <InputNumber
                  size="small"
                  className="studio-tabular"
                  style={{ inlineSize: 68 }}
                  min={1}
                  max={20}
                  step={1}
                  value={params.steps}
                  onChange={(v) => updateParam("steps", Math.max(1, Math.min(20, Math.round(Number(v || 1)))))}
                />
              </div>
            </div>

            <div className="studio-field-group">
              <div className="studio-field-label">
                <FieldLabel
                  label="引导系数 (CFG Scale)"
                  tooltip="SeedVR2 无文本负向条件，官方标准 CFG 为 1.0。"
                />
                <span className="studio-tabular" style={{ fontSize: 12.5 }}>
                  {params.cfg.toFixed(1)}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <Slider
                    min={1.0}
                    max={8.0}
                    step={0.1}
                    value={params.cfg}
                    onChange={(v) => updateParam("cfg", v)}
                  />
                </div>
                <InputNumber
                  size="small"
                  className="studio-tabular"
                  style={{ inlineSize: 68 }}
                  min={1.0}
                  max={8.0}
                  step={0.1}
                  value={params.cfg}
                  onChange={(v) => updateParam("cfg", Math.max(1.0, Math.min(8.0, Number(v || 1.0))))}
                />
              </div>
            </div>

            <div className="studio-field-group">
              <div className="studio-field-label">
                <FieldLabel
                  label="重绘幅度 (Denoise)"
                  tooltip="默认 1.0 执行完整细节超分重建；适度调低可减弱生成纹理。"
                />
                <span className="studio-tabular" style={{ fontSize: 12.5 }}>
                  {params.denoise.toFixed(2)}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <Slider
                    min={0.1}
                    max={1.0}
                    step={0.05}
                    value={params.denoise}
                    onChange={(v) => updateParam("denoise", v)}
                  />
                </div>
                <InputNumber
                  size="small"
                  className="studio-tabular"
                  style={{ inlineSize: 68 }}
                  min={0.05}
                  max={1.0}
                  step={0.05}
                  value={params.denoise}
                  onChange={(v) => updateParam("denoise", Math.max(0.05, Math.min(1.0, Number(v || 1.0))))}
                />
              </div>
            </div>

            <div className="studio-field-group">
              <FieldLabel label="求解器与噪声调度 (Sampler / Scheduler)" />
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <Select
                  size="small"
                  value={params.sampler_name}
                  onChange={(v) => updateParam("sampler_name", v as SamplerName)}
                  options={[
                    { label: "euler (推荐)", value: "euler" },
                    { label: "euler_ancestral", value: "euler_ancestral" },
                    { label: "heun", value: "heun" },
                    { label: "dpmpp_2m", value: "dpmpp_2m" },
                    { label: "uni_pc", value: "uni_pc" },
                  ]}
                />
                <Select
                  size="small"
                  value={params.scheduler}
                  onChange={(v) => updateParam("scheduler", v as SchedulerName)}
                  options={[
                    { label: "simple (推荐)", value: "simple" },
                    { label: "normal", value: "normal" },
                    { label: "sgm_uniform", value: "sgm_uniform" },
                    { label: "beta", value: "beta" },
                    { label: "karras", value: "karras" },
                  ]}
                />
              </div>
            </div>
          </div>

          {/* Progressive Disclosure for Low-Level Tiled VAE, Precision & Encoding */}
          <details className="studio-native-details">
            <summary>
              底层引擎、Tiled VAE 分块与导出编码高级配置（FP16/FP8 · 空间/时间瓦片 · 显存回收）
            </summary>
            <div className="studio-details-body">
              <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
                <div className="studio-param-grid">
                  <div className="studio-field-group">
                    <FieldLabel
                      label="主模型推理精度 (Weight Dtype)"
                      tooltip="80GB A100/H100 保持默认 FP16；40GB A100 超分超大尺寸时可切换 fp8_e4m3fn 降低权重显存占用。"
                    />
                    <Select
                      size="small"
                      value={params.unet_weight_dtype}
                      onChange={(v) => updateParam("unet_weight_dtype", v as UnetWeightDtype)}
                      options={[
                        { label: "default (原生 FP16 全精度)", value: "default" },
                        { label: "fp8_e4m3fn (省显存量化)", value: "fp8_e4m3fn" },
                        { label: "fp8_e4m3fn_fast", value: "fp8_e4m3fn_fast" },
                        { label: "fp8_e5m2", value: "fp8_e5m2" },
                      ]}
                    />
                  </div>

                  <div className="studio-field-group">
                    <FieldLabel label="Tiled VAE 空间瓦片边长 / 重叠 (px)" />
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <InputNumber
                        size="small"
                        className="studio-tabular"
                        style={{ inlineSize: "100%" }}
                        min={256}
                        max={2048}
                        step={64}
                        addonBefore="边长"
                        value={params.vae_tile_size}
                        onChange={(v) =>
                          updateParam("vae_tile_size", Math.max(256, Math.min(2048, Number(v || 512))))
                        }
                      />
                      <InputNumber
                        size="small"
                        className="studio-tabular"
                        style={{ inlineSize: "100%" }}
                        min={32}
                        max={512}
                        step={32}
                        addonBefore="重叠"
                        value={params.vae_tile_overlap}
                        onChange={(v) =>
                          updateParam("vae_tile_overlap", Math.max(32, Math.min(512, Number(v || 128))))
                        }
                      />
                    </div>
                  </div>

                  {params.mode === "video" ? (
                    <>
                      <div className="studio-field-group">
                        <FieldLabel label="Tiled VAE 时间窗口 / 重叠 (帧)" />
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                          <InputNumber
                            size="small"
                            className="studio-tabular"
                            style={{ inlineSize: "100%" }}
                            min={8}
                            max={4096}
                            step={8}
                            addonBefore="窗口"
                            value={params.vae_temporal_size}
                            onChange={(v) =>
                              updateParam("vae_temporal_size", Math.max(8, Number(v || 64)))
                            }
                          />
                          <InputNumber
                            size="small"
                            className="studio-tabular"
                            style={{ inlineSize: "100%" }}
                            min={4}
                            max={256}
                            step={4}
                            addonBefore="重叠"
                            value={params.vae_temporal_overlap}
                            onChange={(v) =>
                              updateParam("vae_temporal_overlap", Math.max(4, Number(v || 8)))
                            }
                          />
                        </div>
                      </div>

                      <div className="studio-field-group">
                    <FieldLabel label="视频编码器与 CRF（数值越低画质越高）" />
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                          <Select
                            size="small"
                            value={params.video_codec}
                            onChange={(v) => updateParam("video_codec", v as VideoCodecChoice)}
                            options={[
                              { label: "auto (自动)", value: "auto" },
                              ...(params.video_output_format !== "webm"
                                ? [{ label: "H.264", value: "h264" }]
                                : []),
                              { label: "AV1", value: "av1" },
                            ]}
                          />
                          <InputNumber
                            size="small"
                            className="studio-tabular"
                            style={{ inlineSize: "100%" }}
                            min={0}
                            max={51}
                            step={1}
                            addonBefore="CRF"
                            disabled={params.video_codec === "auto"}
                            value={params.crf}
                            onChange={(v) => updateParam("crf", Math.max(0, Math.min(51, Number(v ?? 18))))}
                          />
                        </div>
                      </div>

                      <div className="studio-field-group">
                        <FieldLabel
                          label="色彩空间 / 位深 / 播放帧率"
                          tooltip="帧率设为 0 保持原速；非零值改变现有帧的播放速度和时长，不补帧。变速时请关闭保留原声。"
                        />
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                          <Select
                            size="small"
                            value={params.color_space}
                            onChange={(v) => updateParam("color_space", v as ColorSpaceChoice)}
                            options={[
                              { label: "继承色彩", value: "match_input" },
                              { label: "sRGB", value: "sRGB" },
                              { label: "HDR", value: "HDR" },
                              { label: "HDR PQ", value: "HDR PQ" },
                            ]}
                          />
                          <Select
                            size="small"
                            value={params.bit_depth}
                            onChange={(v) => updateParam("bit_depth", v as BitDepthChoice)}
                            options={[
                              { label: "继承位深", value: "match_input" },
                              { label: "auto", value: "auto" },
                              { label: "8-bit", value: "8" },
                              { label: "10-bit", value: "10" },
                            ]}
                          />
                          <InputNumber
                            size="small"
                            className="studio-tabular"
                            style={{ inlineSize: "100%" }}
                            min={0}
                            max={120}
                            step={1}
                            placeholder="0=原FPS"
                            aria-label="播放帧率，0 保持原速"
                            value={params.fps_override}
                            onChange={(v) => updateParam("fps_override", Math.max(0, Number(v || 0)))}
                          />
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="studio-field-group">
                      <FieldLabel label="WebP / JPEG 导出画质 (PNG 始终无损)" />
                      <InputNumber
                        size="small"
                        className="studio-tabular"
                        style={{ inlineSize: "100%" }}
                        min={60}
                        max={100}
                        step={1}
                        addonAfter="%"
                        value={params.image_quality}
                        onChange={(v) =>
                          updateParam("image_quality", Math.max(60, Math.min(100, Number(v || 94))))
                        }
                      />
                    </div>
                  )}
                </div>

                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    paddingBlockStart: 8,
                    borderBlockStart: "1px dashed var(--studio-border)",
                  }}
                >
                  <Space size={8}>
                    <Switch
                      size="small"
                      checked={params.release_vram_after}
                      onChange={(v) => updateParam("release_vram_after", v)}
                      aria-label="任务完成后自动卸载模型释放显存"
                    />
                    <Text style={{ fontSize: 12.5 }}>超分完成后自动从 GPU 卸载权重回收显存</Text>
                  </Space>

                  <Space size={8}>
                    <Button htmlType="button" size="small" onClick={resetEngineDefaults}>
                      重置底层引擎默认
                    </Button>
                    <Button
                      htmlType="button"
                      size="small"
                      danger
                      loading={releasingVram}
                      disabled={isBusy}
                      onClick={() => void handleManualReleaseVram()}
                    >
                      立即释放 GPU 显存
                    </Button>
                  </Space>
                </div>
              </div>
            </div>
          </details>
        </div>
      </Card>

      {validationMessage && <Alert type="warning" showIcon message={validationMessage} />}

      {/* Sticky Primary Action Dock */}
      <div className="studio-action-dock">
        <Space wrap size={[10, 8]}>
          <Space size={6}>
            <label htmlFor={seedInputId} style={{ fontSize: 13, fontWeight: 600 }}>
              种子：
            </label>
            <InputNumber
              id={seedInputId}
              size="small"
              className="studio-tabular"
              style={{ inlineSize: 132 }}
              min={0}
              step={1}
              value={params.seed}
              onChange={(v) => updateParam("seed", Math.max(0, Math.floor(Number(v || 0))))}
              placeholder="0 = 随机"
            />
            <Tooltip title={seedLocked ? "已锁定种子" : "锁定当前种子"}>
              <Button
                htmlType="button"
                size="small"
                type={seedLocked ? "primary" : "default"}
                ghost={seedLocked}
                icon={seedLocked ? <LockOutlined /> : <UnlockOutlined />}
                aria-label={seedLocked ? "取消锁定种子" : "锁定当前种子"}
                onClick={() => setSeedLocked((v) => !v)}
              />
            </Tooltip>
            <Tooltip title="重置为随机种子 (0)">
              <Button
                htmlType="button"
                size="small"
                icon={<ReloadOutlined />}
                aria-label="重置为随机种子"
                onClick={() => {
                  setSeedLocked(false);
                  updateParam("seed", 0);
                }}
              />
            </Tooltip>
          </Space>

          {params.mode === "video" ? (
            <Select
              size="small"
              style={{ inlineSize: 118 }}
              value={params.video_output_format}
              onChange={(v) => {
                const fmt = v as VideoOutputFormat;
                setParams((prev) => ({
                  ...prev,
                  video_output_format: fmt,
                  video_codec:
                    fmt === "webm" && prev.video_codec === "h264" ? "auto" : prev.video_codec,
                }));
              }}
              options={[
                { label: "MP4 通用", value: "mp4" },
                { label: "WebM 网页", value: "webm" },
                { label: "MKV 封装", value: "mkv" },
              ]}
            />
          ) : (
            <Select
              size="small"
              style={{ inlineSize: 122 }}
              value={params.image_output_format}
              onChange={(v) => updateParam("image_output_format", v as ImageOutputFormat)}
              options={[
                { label: "PNG 真无损", value: "png" },
                { label: "WebP 高压缩", value: "webp" },
                { label: "JPEG 照片", value: "jpeg" },
              ]}
            />
          )}
        </Space>

        <Space size={8}>
          {isBusy && activeTask?.status === "queued" && (
            <Button htmlType="button" danger onClick={() => void cancelActive()}>
              取消排队
            </Button>
          )}
          <Button
            htmlType="button"
            type="primary"
            size="large"
            icon={<RocketOutlined />}
            loading={isBusy}
            disabled={Boolean(validationMessage) || !activeInputRef.trim()}
            onClick={() => void handleGenerate()}
          >
            {isBusy
              ? `超分重建中 ${Math.round((activeTask?.progress || 0.05) * 100)}%`
              : params.mode === "video"
                ? `开始视频超分（${previewTarget.width}×${previewTarget.height}）`
                : `开始图片 4K 超分（${previewTarget.width}×${previewTarget.height}）`}
          </Button>
        </Space>
      </div>
    </>
  );

  const rightPane = (
    <>
      {/* Live GPU Task Progress */}
      {isBusy && activeTask && (
        <Card className="studio-card" size="small">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Space size={6}>
                <ExperimentOutlined style={{ color: "var(--studio-accent)" }} />
                <Text strong style={{ fontSize: 13 }}>
                  {activeTask.status === "queued"
                    ? `排队等待中（#${activeTask.queue_position || 1}）`
                    : "SeedVR2 正在执行超分细节重建"}
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
              {activeTask.stage || "正在调度 Tiled VAE 与 SeedVR2 扩散模型..."}
            </Text>
          </div>
        </Card>
      )}

      {/* Primary Preview & A/B Reference Stage */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            {displayedEntry?.result.media_type === "image" ? (
              <PictureOutlined style={{ color: "var(--studio-accent)" }} />
            ) : (
              <VideoCameraOutlined style={{ color: "var(--studio-accent)" }} />
            )}
            <span>超分前后 A/B 对比检视台</span>
          </Space>
        }
        extra={
          displayedEntry?.result.mock ? (
            <Tag color="warning" style={{ marginInlineEnd: 0 }}>
              本地 Mock 预览
            </Tag>
          ) : displayedEntry?.result ? (
            <Tag color="success" style={{ marginInlineEnd: 0 }}>
              GPU 真实超分
            </Tag>
          ) : null
        }
      >
        {!displayedEntry || !stageOutputUrl ? (
          <div
            style={{
              padding: "3rem 1.5rem",
              textAlign: "center",
              borderRadius: "0.7rem",
              background: "var(--studio-surface-subtle)",
              border: "1px dashed var(--studio-border-strong)",
            }}
          >
            {params.mode === "video" ? (
              <VideoCameraOutlined style={{ fontSize: 36, color: "#94a3b8", marginBlockEnd: 10 }} />
            ) : (
              <PictureOutlined style={{ fontSize: 36, color: "#94a3b8", marginBlockEnd: 10 }} />
            )}
            <div
              style={{
                fontWeight: 600,
                fontSize: 14.5,
                color: "var(--studio-text)",
                marginBlockEnd: 4,
              }}
            >
              等待超分任务完成
            </div>
            <Text type="secondary" style={{ fontSize: 12.5 }}>
              在左侧上传视频或图片并选择放大策略后，点击底部主按钮或按 <code>⌘/Ctrl + Enter</code>。完成后可在此拖拽卷帘实时对比原片与超分细节。
            </Text>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            {displayedEntry.result.media_type === "video" ? (
              <VideoCompareStage
                result={displayedEntry.result}
                outputUrl={stageOutputUrl}
                downloadUrl={stageDownloadUrl}
                inputUrl={stageInputUrl || undefined}
                referenceFit={displayedEntry.params.sizing_mode === "dimensions"
                  ? displayedEntry.params.crop_mode === "center" ? "cover" : "fill"
                  : "contain"}
                onUseAsInput={() => {
                  const outRef = `output:${displayedEntry.result.filename}`;
                  setVideoFileRef(outRef);
                  setVideoSourceMeta({
                    w: displayedEntry.result.width,
                    h: displayedEntry.result.height,
                    dur: displayedEntry.result.duration_sec || 0,
                  });
                  handleModeSwitch("video");
                  message.success("已将该超分视频挂载为新的源视频");
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
                referenceLabel={`超分前原图 (${displayedEntry.result.input_width}×${displayedEntry.result.input_height})`}
                resultLabel={`SeedVR2 超分 (${displayedEntry.result.width}×${displayedEntry.result.height})`}
                useAsReferenceLabel="设为源图继续放大"
                onUseAsReference={(img) => {
                  const outRef = `output:${img.filename}`;
                  setImageFileRef(outRef);
                  setImageSourceDims({ w: img.width, h: img.height });
                  handleModeSwitch("image");
                  message.success("已将该超分图挂载为新的源图片");
                }}
              />
            )}

            {displayedEntry.result.warnings?.map((w, idx) => (
              <Alert key={idx} type="info" showIcon icon={<InfoCircleOutlined />} message={w} />
            ))}

            {/* Metadata & Seed Lock Footer */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "0.5rem",
                padding: "0.6rem 0.75rem",
                borderRadius: "0.6rem",
                background: "var(--studio-surface-subtle)",
                border: "1px solid var(--studio-border)",
              }}
            >
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
                  追色: {displayedEntry.result.color_correction.toUpperCase()}
                </Tag>
                {displayedEntry.result.media_type === "video" && (
                  <Tag
                    color={displayedEntry.result.has_audio ? "success" : "default"}
                    style={{ marginInlineEnd: 0 }}
                  >
                    {displayedEntry.result.has_audio ? "原声保留" : "无音轨"}
                  </Tag>
                )}
                {displayedEntry.result.split_latent && (
                  <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                    Split Latent
                  </Tag>
                )}
                <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                  {displayedEntry.result.steps} 步 · CFG {displayedEntry.result.cfg}
                </Tag>
              </div>

              <Button
                htmlType="button"
                size="small"
                icon={<LockOutlined />}
                onClick={() => {
                  setSeedLocked(true);
                  updateParam("seed", displayedEntry.result.used_seed);
                  message.success(`已锁定种子：${displayedEntry.result.used_seed}`);
                }}
              >
                锁定 Seed <span className="studio-tabular">{displayedEntry.result.used_seed}</span>
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Session History List */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <HistoryOutlined style={{ color: "var(--studio-accent)" }} />
            <span>本次会话超分历史（{historyItems.length}）</span>
          </Space>
        }
        extra={
          historyItems.length > 0 && (
            <Popconfirm
              title="清空当前会话超分记录？"
              okText="清空"
              cancelText="取消"
              onConfirm={() => {
                clearAll();
                setSelectedTakeId(null);
              }}
            >
              <Button htmlType="button" size="small" type="text" danger icon={<DeleteOutlined />}>
                清空
              </Button>
            </Popconfirm>
          )
        }
      >
        {historyItems.length === 0 ? (
          <Text type="secondary" style={{ fontSize: 12.5 }}>
            本次会话完成的视频与图片超分记录会自动保存在此，支持随时切换对比或一键回填全部参数。
          </Text>
        ) : (
          <div className="studio-scroll-panel">
            <div className="studio-video-history-list">
              {historyItems.map((item) => {
                const isSelected = displayedEntry?.id === item.id;
                const mediaSrc = resolveApiUrl(item.result.output_url, true);
                const isVideo = item.result.media_type === "video";
                const titleText = `${isVideo ? "视频超分" : "图片超分"} · ${
                  item.result.model_variant === "7b_sharp" ? "7B Sharp" : "3B Fast"
                } (×${item.result.effective_scale})`;

                return (
                  <div
                    key={item.id}
                    className="studio-video-history-card"
                    data-active={isSelected ? "true" : "false"}
                    onClick={() => setSelectedTakeId(item.id)}
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
                          background: "#0f172a",
                        }}
                        onClick={(e) => e.stopPropagation()}
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
                          background: "#ffffff",
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
                      <div
                        style={{
                          fontSize: 12.5,
                          fontWeight: 600,
                          color: "var(--studio-text)",
                        }}
                      >
                        {titleText}
                      </div>

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
                          onClick={(e) => {
                            e.stopPropagation();
                            setParams(item.params);
                            setSeedLocked(item.params.seed > 0);
                            if (item.params.mode === "video") {
                              setVideoFileRef(item.params.input_file);
                              setVideoSourceMeta({ w: item.result.input_width, h: item.result.input_height, dur: 0 });
                            } else {
                              setImageFileRef(item.params.input_file);
                              setImageSourceDims({ w: item.result.input_width, h: item.result.input_height });
                            }
                            message.info("已回填该条记录的全部超分参数");
                          }}
                        >
                          回填参数
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>
    </>
  );

  return (
    <StudioShell
      brandBadge="VR2"
      defaultTitle="SeedVR2 视频与图片 4K 超分工作台"
      defaultSubtitle="7B Sharp 旗舰锐化 · 3B Fast 长视频极速 · 1 步对抗扩散修复 · CIELAB 追色与原声无损继承"
      apiEndpointPath="/api/v1/generate"
      mediaKind={params.mode === "image" ? "image" : "video"}
      sampleRequestBody={effectivePayload as unknown as Record<string, unknown>}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
