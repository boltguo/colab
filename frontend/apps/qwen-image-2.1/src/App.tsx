import React, { useCallback, useId, useMemo, useRef, useState } from "react";
import {
  Alert,
  Badge,
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
  Input,
  InputNumber,
  LockOutlined,
  LoraManagerPanel,
  PictureOutlined,
  PlusOutlined,
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
  SwapOutlined,
  Switch,
  Tag,
  Text,
  TextArea,
  Tooltip,
  UnlockOutlined,
  resolveApiUrl,
  triggerModelRelease,
  useHistoryStore,
  useStudioFeedback,
  useTaskRunner,
} from "@colab/shared";
import type { StageImageEntry } from "@colab/shared";
import {
  ASPECT_RATIO_OPTIONS,
  DEFAULT_QWEN_IMAGE_PARAMS,
  SYMMETRIC_RATIO_SWAP,
  calcPresetDimensions,
  calcRefMatchedDimensions,
  editImageGeometry,
  snap32,
} from "./types";
import type {
  AspectRatioChoice,
  ClipDevice,
  ImageOutputFormat,
  KvCacheDevice,
  KvCacheDtype,
  QwenImageParams,
  QwenImageResult,
  ReferenceConditioningMode,
  ResolutionTier,
  SamplerName,
  SchedulerName,
  StandardAspectRatio,
  UnetWeightDtype,
} from "./types";

function FieldLabel({ label, tooltip }: { label: string; tooltip?: string }) {
  return (
    <div className="studio-field-label">
      <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
        {label}
        {tooltip && (
          <Tooltip title={tooltip}>
            <QuestionCircleOutlined style={{ color: "var(--studio-text-muted)", fontSize: 13 }} />
          </Tooltip>
        )}
      </span>
    </div>
  );
}

export function QwenImageStudioApp() {
  const promptInputId = useId();
  const negPromptInputId = useId();
  const widthInputId = useId();
  const heightInputId = useId();
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const { message } = useStudioFeedback();

  const nextSlotSeqRef = useRef(2);
  const createRefSlot = useCallback((fileRef = "") => {
    const id = `slot-${nextSlotSeqRef.current}`;
    nextSlotSeqRef.current += 1;
    return { id, fileRef };
  }, []);

  const [params, setParams] = useState<QwenImageParams>(DEFAULT_QWEN_IMAGE_PARAMS);
  const [refSlots, setRefSlots] = useState<Array<{ id: string; fileRef: string }>>([
    { id: "slot-1", fileRef: "" },
  ]);
  const [primaryRefDims, setPrimaryRefDims] = useState<{ w: number; h: number } | null>(null);
  const [seedLocked, setSeedLocked] = useState(false);
  const [showNegPrompt, setShowNegPrompt] = useState(false);
  const [selectedTakeId, setSelectedTakeId] = useState<string | null>(null);

  const { items: historyItems, addEntry, clearAll } = useHistoryStore<
    QwenImageResult,
    QwenImageParams
  >("qwen-image-2.1", 24);

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<
    QwenImageResult,
    QwenImageParams
  >({
    endpointPath: "/api/v1/generate",
    onSuccess: (finishedTask) => {
      if (finishedTask.result) {
        addEntry({
          id: finishedTask.task_id,
          feature: "qwen-image-2.1",
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
          `生成完成（${finishedTask.result.width}×${finishedTask.result.height}${
            finishedTask.elapsed_sec ? ` · ${finishedTask.elapsed_sec}s` : ""
          }）`
        );
      }
    },
    onError: (errMsg) => {
      message.error(errMsg);
    },
  });

  const isImg2Img = params.mode !== "t2i";

  const updateParam = <K extends keyof QwenImageParams>(key: K, val: QwenImageParams[K]) => {
    setParams((prev) => ({ ...prev, [key]: val }));
  };

  // Switch between T2I and Img2Img cleanly
  const handleModeSwitch = (nextMode: "t2i" | "img2img") => {
    setParams((prev) => {
      if (nextMode === "img2img") {
        const nextAspect: AspectRatioChoice =
          prev.aspect_ratio === "custom" ? "custom" : "match_input";
        const matched =
          nextAspect === "match_input"
            ? calcRefMatchedDimensions(prev.resolution_tier, primaryRefDims)
            : { width: prev.width, height: prev.height };
        return {
          ...prev,
          mode: "img2img",
          aspect_ratio: nextAspect,
          width: matched.width,
          height: matched.height,
        };
      }
      const nextTier: ResolutionTier = prev.resolution_tier === "original" ? "2K" : prev.resolution_tier;
      const nextAspect: AspectRatioChoice =
        prev.aspect_ratio === "match_input" ? "1:1" : prev.aspect_ratio;
      const dims =
        nextAspect === "custom"
          ? { width: prev.width, height: prev.height }
          : calcPresetDimensions(nextTier, nextAspect);
      return {
        ...prev,
        mode: "t2i",
        resolution_tier: nextTier,
        aspect_ratio: nextAspect,
        width: dims.width,
        height: dims.height,
      };
    });
  };

  // Independent Resolution Tier change -> updates W x H when on standard or match_input aspect ratio
  const handleResolutionChange = (nextTier: ResolutionTier) => {
    setParams((prev) => {
      if (nextTier === "original") {
        const matched = calcRefMatchedDimensions(nextTier, primaryRefDims);
        return { ...prev, resolution_tier: nextTier, aspect_ratio: "match_input", ...matched };
      }
      if (prev.aspect_ratio === "custom") {
        return { ...prev, resolution_tier: nextTier };
      }
      if (prev.aspect_ratio === "match_input") {
        const matched = calcRefMatchedDimensions(nextTier, primaryRefDims);
        return {
          ...prev,
          resolution_tier: nextTier,
          width: matched.width,
          height: matched.height,
        };
      }
      const dims = calcPresetDimensions(nextTier, prev.aspect_ratio);
      return {
        ...prev,
        resolution_tier: nextTier,
        width: dims.width,
        height: dims.height,
      };
    });
  };

  // Independent Aspect Ratio change -> updates W x H at current Resolution Tier
  const handleAspectChange = (nextAspect: AspectRatioChoice) => {
    setParams((prev) => {
      if (nextAspect === "custom") {
        return editImageGeometry(prev, prev.width, prev.height);
      }
      if (nextAspect === "match_input") {
        const matched = calcRefMatchedDimensions(prev.resolution_tier, primaryRefDims);
        return {
          ...prev,
          aspect_ratio: "match_input",
          width: matched.width,
          height: matched.height,
        };
      }
      const effectiveTier: ResolutionTier =
        prev.resolution_tier === "original" ? "2K" : prev.resolution_tier;
      const dims = calcPresetDimensions(effectiveTier, nextAspect);
      return {
        ...prev,
        resolution_tier: effectiveTier,
        aspect_ratio: nextAspect,
        width: dims.width,
        height: dims.height,
      };
    });
  };

  // Swap Width <-> Height
  const handleSwapDimensions = () => {
    setParams((prev) => {
      const nextW = prev.height;
      const nextH = prev.width;
      let nextAspect: AspectRatioChoice = prev.aspect_ratio;
      if (prev.aspect_ratio !== "custom" && prev.aspect_ratio !== "match_input") {
        const swapped = SYMMETRIC_RATIO_SWAP[prev.aspect_ratio];
        nextAspect = swapped || (prev.aspect_ratio === "1:1" ? "1:1" : "custom");
      } else if (prev.aspect_ratio === "match_input") {
        nextAspect = "custom";
      }
      return editImageGeometry(prev, nextW, nextH, nextAspect);
    });
  };

  // Sync primary reference natural dimensions when uploaded
  const handlePrimaryDimsDetected = useCallback(
    (dims: { w: number; h: number } | null) => {
      setPrimaryRefDims(dims);
      if (dims) {
        setParams((prev) => {
          if (prev.mode !== "t2i" && prev.aspect_ratio === "match_input") {
            const matched = calcRefMatchedDimensions(prev.resolution_tier, dims);
            return { ...prev, width: matched.width, height: matched.height };
          }
          return prev;
        });
      }
    },
    []
  );

  const resetAllDefaults = () => {
    setSeedLocked(false);
    setRefSlots([createRefSlot("")]);
    setPrimaryRefDims(null);
    setParams(DEFAULT_QWEN_IMAGE_PARAMS);
    setShowNegPrompt(false);
    message.success("已恢复默认参数");
  };

  const insertTokenAtCursor = (token: string) => {
    const el = promptRef.current;
    if (!el) {
      updateParam("prompt", `${params.prompt} ${token}`.trim());
      return;
    }
    const start = el.selectionStart ?? params.prompt.length;
    const end = el.selectionEnd ?? params.prompt.length;
    const before = params.prompt.slice(0, start);
    const after = params.prompt.slice(end);
    const needLeadSpace = before.length > 0 && !/\s$/.test(before);
    const needTrailSpace = after.length > 0 && !/^\s/.test(after);
    const piece = `${needLeadSpace ? " " : ""}${token}${needTrailSpace ? " " : ""}`;
    const nextText = `${before}${piece}${after}`;
    updateParam("prompt", nextText);
    requestAnimationFrame(() => {
      el.focus();
      const pos = before.length + piece.length;
      el.setSelectionRange(pos, pos);
    });
  };

  const cleanUploadedRefs = useMemo(
    () => refSlots.map((r) => r.fileRef.trim()).filter(Boolean),
    [refSlots]
  );

  const buildCleanedPayload = useCallback((): QwenImageParams => {
    return {
      ...params,
      mode: isImg2Img ? "img2img" : "t2i",
      reference_images: isImg2Img ? cleanUploadedRefs : [],
      width: snap32(params.width),
      height: snap32(params.height),
    };
  }, [cleanUploadedRefs, isImg2Img, params]);

  const handleGenerate = useCallback(async () => {
    if (isBusy) return;
    if (!params.prompt.trim()) {
      message.warning("请先输入画面描述或图像编辑指令。");
      return;
    }
    if (isImg2Img && cleanUploadedRefs.length < 1) {
      message.warning("图生图模式请先上传至少 1 张参考图片 (<image1>)。");
      return;
    }
    if (isImg2Img) {
      const firstEmpty = refSlots.findIndex((slot) => !slot.fileRef.trim());
      if (firstEmpty >= 0 && refSlots.slice(firstEmpty + 1).some((slot) => slot.fileRef.trim())) {
        message.warning(`参考图 ${firstEmpty + 1} 尚未上传，请补充图片或删除这张空卡片，让图片与 <imageN> 编号保持一致。`);
        return;
      }
    }
    await runTask(buildCleanedPayload());
  }, [buildCleanedPayload, cleanUploadedRefs.length, isBusy, isImg2Img, message, params.prompt, refSlots, runTask]);

  const displayedEntry = useMemo(() => {
    if (selectedTakeId) {
      const fromHist = historyItems.find((h) => h.id === selectedTakeId);
      if (fromHist) return fromHist;
    }
    if (activeTask?.status === "succeeded" && activeTask.result) {
      return {
        id: activeTask.task_id,
        feature: "qwen-image-2.1",
        createdAt: activeTask.finished_at || activeTask.created_at,
        elapsedSec: activeTask.elapsed_sec,
        params: activeTask.params,
        result: activeTask.result,
      };
    }
    return historyItems[0] || null;
  }, [activeTask, historyItems, selectedTakeId]);

  const stageImages: StageImageEntry[] = useMemo(() => {
    if (!displayedEntry?.result) return [];
    const list = displayedEntry.result.images?.length
      ? displayedEntry.result.images
      : [
          {
            url: displayedEntry.result.image_url,
            filename: displayedEntry.result.filename,
            width: displayedEntry.result.width,
            height: displayedEntry.result.height,
            size_bytes: displayedEntry.result.size_bytes,
            format: displayedEntry.result.format,
          },
        ];
    return list.map((it) => ({
      url: resolveApiUrl(it.url, true),
      filename: it.filename,
      width: it.width,
      height: it.height,
      sizeBytes: it.size_bytes,
      format: it.format,
    }));
  }, [displayedEntry]);

  const stagePrimaryRefUrl = useMemo(() => {
    const r0 = displayedEntry?.result?.reference_urls?.[0];
    return r0 ? resolveApiUrl(r0, true) : undefined;
  }, [displayedEntry]);

  const sampleRequestBody = useMemo(
    () => buildCleanedPayload() as unknown as Record<string, unknown>,
    [buildCleanedPayload]
  );

  const enabledLoraCount = params.loras.filter((l) => l.enabled && l.lora.trim()).length;
  const negPromptNeedsCfgHint = Boolean(params.negative_prompt.trim()) && params.cfg <= 1.01;
  const megapixels = ((snap32(params.width) * snap32(params.height)) / (1024 * 1024)).toFixed(2);

  const leftPane = (
    <>
      {/* 1. Mode (T2I vs Img2Img) + Reference Upload + Prompt */}
      <Card
        className="studio-card"
        title={
          <Space size={10} wrap>
            <Segmented
              value={isImg2Img ? "img2img" : "t2i"}
              onChange={(val) => handleModeSwitch(val as "t2i" | "img2img")}
              options={[
                { label: "文生图", value: "t2i" },
                { label: "图生图 / 编辑", value: "img2img" },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12.5, fontWeight: 400 }}>
              {isImg2Img
                ? "上传 1 张主参考图，可按需添加多张图片进行融合参考"
                : "输入中英文描述直接生成 1K / 2K 高清图像"}
            </Text>
          </Space>
        }
        extra={
          <Button
            htmlType="button"
            size="small"
            type="text"
            icon={<ClearOutlined />}
            onClick={resetAllDefaults}
          >
            恢复默认
          </Button>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.95rem" }}>
          {/* User-Uploaded Reference Image Slots (Img2Img only, optional 2..4 images) */}
          {isImg2Img && (
            <div
              style={{
                padding: "0.75rem 0.85rem",
                borderRadius: "0.65rem",
                background: "var(--studio-surface-subtle)",
                border: "1px solid var(--studio-border)",
                display: "flex",
                flexDirection: "column",
                gap: "0.65rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, minBlockSize: 24 }}>
                <Text strong style={{ fontSize: 13 }}>
                  参考图片（已上传 <span className="studio-tabular">{cleanUploadedRefs.length}</span> / {refSlots.length}）
                </Text>

                {refSlots.length < 4 && (
                  <Button
                    htmlType="button"
                    size="small"
                    type="dashed"
                    icon={<PlusOutlined />}
                    onClick={() => setRefSlots((prev) => [...prev, createRefSlot("")])}
                  >
                    添加参考图
                  </Button>
                )}
              </div>

              <div
                className="studio-image-slot-grid"
                data-single={refSlots.length === 1 ? "true" : "false"}
              >
                {refSlots.map((slot, idx) => (
                  <ImageSourceField
                    key={slot.id}
                    label={idx === 0 ? "主参考图" : `参考图 ${idx + 1}`}
                    badgeText={`<image${idx + 1}>`}
                    value={slot.fileRef}
                    allowClear={Boolean(slot.fileRef)}
                    onDimensionsChange={idx === 0 ? handlePrimaryDimsDetected : undefined}
                    onRemoveSlot={
                      refSlots.length > 1
                        ? () => {
                            setRefSlots((prev) => {
                              const next = prev.filter((item) => item.id !== slot.id);
                              return next.length > 0 ? next : [createRefSlot("")];
                            });
                          }
                        : undefined
                    }
                    onChange={(nextRef) => {
                      setRefSlots((prev) =>
                        prev.map((item) =>
                          item.id === slot.id ? { ...item, fileRef: nextRef } : item
                        )
                      );
                    }}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Prompt Input */}
          <div className="studio-field-group">
            <div className="studio-field-label">
              <label htmlFor={promptInputId}>
                {isImg2Img ? "编辑 / 图生图指令 (Prompt)" : "提示词 (Prompt)"}
              </label>
              <Space size={8} wrap>
                {isImg2Img && (
                  <Space size={4} wrap>
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                      点击插入引用：
                    </Text>
                    {refSlots.map((slot, i) => {
                      const tok = `<image${i + 1}>`;
                      return (
                        <button
                          key={slot.id}
                          type="button"
                          className="studio-token-chip"
                          onClick={() => insertTokenAtCursor(tok)}
                        >
                          {tok}
                        </button>
                      );
                    })}
                  </Space>
                )}
                <Button
                  htmlType="button"
                  size="small"
                  type="link"
                  style={{ padding: 0, blockSize: "auto" }}
                  onClick={() => setShowNegPrompt((v) => !v)}
                >
                  {showNegPrompt || params.negative_prompt ? "收起反向提示词" : "+ 反向提示词"}
                </Button>
              </Space>
            </div>

            <TextArea
              ref={promptRef}
              id={promptInputId}
              rows={4}
              maxLength={8000}
              value={params.prompt}
              onChange={(e) => updateParam("prompt", e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void handleGenerate();
                }
              }}
              placeholder={
                isImg2Img
                  ? "输入修改要求，例如：保留 <image1> 中的人物，将背景替换为海边落日（如上传了第 2 张图可写：融合到 <image2> 的场景中）..."
                  : "描述画面主体、场景环境、构图视角、光影风格或需要渲染的文字内容..."
              }
            />

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--studio-text-muted)" }}>
              <span>快捷键 <code>⌘/Ctrl + Enter</code> 直接生成</span>
              <span className="studio-tabular">{params.prompt.length} / 8000</span>
            </div>
          </div>

          {(showNegPrompt || Boolean(params.negative_prompt)) && (
            <div className="studio-field-group">
              <div className="studio-field-label">
                <label htmlFor={negPromptInputId}>反向提示词 (Negative Prompt)</label>
              </div>
              <Input
                id={negPromptInputId}
                value={params.negative_prompt}
                onChange={(e) => updateParam("negative_prompt", e.target.value)}
                placeholder="排除不需要的元素，例如：模糊、低画质、多余手指、水印..."
              />
              {negPromptNeedsCfgHint && (
                <Alert
                  type="warning"
                  showIcon
                  message={
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <span>
                        当前 CFG 为 <strong>1.0</strong>，反向提示词不会生效；调至 <strong>3.0</strong> 左右可启用负向抑制。
                      </span>
                      <Button
                        htmlType="button"
                        size="small"
                        type="primary"
                        ghost
                        onClick={() => updateParam("cfg", 3.0)}
                      >
                        设为 CFG 3.0
                      </Button>
                    </div>
                  }
                />
              )}
            </div>
          )}
        </div>
      </Card>

      {/* 2. Independent Resolution, Aspect Ratio & Pixel Dimensions (Laid Out Flat) */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <PictureOutlined style={{ color: "var(--studio-accent)" }} />
            <span>画幅比例、分辨率与尺寸</span>
          </Space>
        }
        extra={
          <span className="studio-tabular" style={{ fontSize: 12.5, color: "var(--studio-text-secondary)", fontWeight: 600 }}>
            {snap32(params.width)} × {snap32(params.height)} px（{megapixels} MP）
          </span>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
          {/* Row 1: Independent Resolution Tier + Batch Count */}
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: "0.75rem 1.25rem" }}>
            <div className="studio-field-group" style={{ flex: "1 1 260px" }}>
              <FieldLabel
                label="分辨率档位 (Resolution)"
                tooltip="独立控制清晰度基准：1K 约 100 万像素（快速出图），2K 约 400 万像素（原生超清细节）"
              />
              <Segmented
                block
                value={params.resolution_tier}
                onChange={(val) => handleResolutionChange(val as ResolutionTier)}
                options={[
                  { label: "1K 标清", value: "1K" },
                  { label: "2K 超清", value: "2K" },
                  ...(isImg2Img ? [{ label: "原图分辨率", value: "original" }] : []),
                ]}
              />
            </div>

            <div className="studio-field-group" style={{ flex: "0 1 220px" }}>
              <FieldLabel
                label="生成张数 (Batch)"
                tooltip="单次并行生成的图片数量（2K 下建议 1~2 张）"
              />
              <Segmented
                block
                value={params.batch_size}
                onChange={(val) => updateParam("batch_size", Number(val))}
                options={[
                  { label: "1 张", value: 1 },
                  { label: "2 张", value: 2 },
                  { label: "3 张", value: 3 },
                  { label: "4 张", value: 4 },
                ]}
              />
            </div>
          </div>

          {/* Row 2: Independent Visual Aspect Ratio Selector */}
          <div className="studio-field-group">
            <FieldLabel
              label="宽高比 (Aspect Ratio)"
              tooltip="点选比例会自动按当前分辨率换算像素宽高；也可直接在下方输入任意自定义宽高"
            />
            <div className="studio-aspect-grid">
              {isImg2Img && (
                <button
                  type="button"
                  className="studio-aspect-pill"
                  data-active={params.aspect_ratio === "match_input" ? "true" : "false"}
                  onClick={() => handleAspectChange("match_input")}
                >
                  <span
                    className="studio-aspect-frame"
                    style={{ inlineSize: 18, blockSize: 18, borderStyle: "dashed" }}
                  />
                  <span style={{ fontSize: 12, fontWeight: 600 }}>跟随参考图</span>
                  <span style={{ fontSize: 10.5, opacity: 0.75 }}>
                    {primaryRefDims ? `${primaryRefDims.w}:${primaryRefDims.h}` : "保持比例"}
                  </span>
                </button>
              )}

              {ASPECT_RATIO_OPTIONS.map((opt) => {
                const maxSide = 20;
                const fw =
                  opt.rw >= opt.rh
                    ? maxSide
                    : Math.max(9, Math.round((maxSide * opt.rw) / opt.rh));
                const fh =
                  opt.rh > opt.rw
                    ? maxSide
                    : Math.max(9, Math.round((maxSide * opt.rh) / opt.rw));
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className="studio-aspect-pill"
                    data-active={params.aspect_ratio === opt.value ? "true" : "false"}
                    onClick={() => handleAspectChange(opt.value)}
                  >
                    <span
                      className="studio-aspect-frame"
                      style={{ inlineSize: fw, blockSize: fh }}
                    />
                    <span style={{ fontSize: 12.5, fontWeight: 600 }}>{opt.label}</span>
                    <span style={{ fontSize: 10.5, opacity: 0.75 }}>{opt.sub}</span>
                  </button>
                );
              })}

              <button
                type="button"
                className="studio-aspect-pill"
                data-active={params.aspect_ratio === "custom" ? "true" : "false"}
                onClick={() => handleAspectChange("custom")}
              >
                <span
                  className="studio-aspect-frame"
                  style={{ inlineSize: 19, blockSize: 15, borderRadius: 2 }}
                />
                <span style={{ fontSize: 12, fontWeight: 600 }}>自定义</span>
                <span style={{ fontSize: 10.5, opacity: 0.75 }}>自由宽高</span>
              </button>
            </div>
          </div>

          {/* Row 3: Independent Editable Width x Height Inputs */}
          <div className="studio-dim-bar">
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8 }}>
              <div className="studio-field-group" style={{ inlineSize: 136 }}>
                <label htmlFor={widthInputId} style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)" }}>
                  宽度 W (px)
                </label>
                <InputNumber
                  id={widthInputId}
                  style={{ inlineSize: "100%" }}
                  min={256}
                  max={4096}
                  step={32}
                  value={params.width}
                  onChange={(v) => {
                    const nextW = Number(v || 1024);
                    setParams((prev) => editImageGeometry(prev, nextW, prev.height));
                  }}
                  onBlur={() => updateParam("width", snap32(params.width))}
                />
              </div>

              <Tooltip title="互换宽度与高度">
                <Button
                  htmlType="button"
                  icon={<SwapOutlined />}
                  onClick={handleSwapDimensions}
                  aria-label="互换宽度与高度"
                />
              </Tooltip>

              <div className="studio-field-group" style={{ inlineSize: 136 }}>
                <label htmlFor={heightInputId} style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)" }}>
                  高度 H (px)
                </label>
                <InputNumber
                  id={heightInputId}
                  style={{ inlineSize: "100%" }}
                  min={256}
                  max={4096}
                  step={32}
                  value={params.height}
                  onChange={(v) => {
                    const nextH = Number(v || 1024);
                    setParams((prev) => editImageGeometry(prev, prev.width, nextH));
                  }}
                  onBlur={() => updateParam("height", snap32(params.height))}
                />
              </div>
            </div>

            <Text type="secondary" className="studio-tabular" style={{ fontSize: 12, paddingBlockEnd: 6 }}>
              {params.aspect_ratio === "match_input" && !primaryRefDims
                ? "上传参考图后自动按原图比例匹配像素尺寸（32px 对齐）"
                : `实际输出尺寸：${snap32(params.width)} × ${snap32(params.height)} px（自动 32px 对齐）`}
            </Text>
          </div>
        </div>
      </Card>

      {/* 3. Flat LoRA Mounting & Online Downloader */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <span>LoRA 模型挂载（可选）</span>
            {enabledLoraCount > 0 && <Badge count={enabledLoraCount} color="#2563eb" />}
          </Space>
        }
      >
        <LoraManagerPanel
          slots={params.loras}
          onChange={(nextSlots) => updateParam("loras", nextSlots)}
        />
      </Card>

      {/* 4. Flat Sampling Controls + Collapsible Low-Level Engine Flags */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <ControlOutlined style={{ color: "var(--studio-accent)" }} />
            <span>采样与引擎参数</span>
          </Space>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.95rem" }}>
          <div className="studio-param-grid">
            <div className="studio-field-group">
              <div className="studio-field-label">
                <span>采样步数 (Steps)</span>
                <span className="studio-tabular">{params.steps} 步</span>
              </div>
              <Slider
                min={8}
                max={80}
                step={1}
                value={params.steps}
                onChange={(v) => updateParam("steps", Number(v))}
              />
            </div>

            <div className="studio-field-group">
              <div className="studio-field-label">
                <span>引导系数 (CFG)</span>
                <span className="studio-tabular">{params.cfg.toFixed(1)}</span>
              </div>
              <Slider
                min={1.0}
                max={10.0}
                step={0.1}
                value={params.cfg}
                onChange={(v) => updateParam("cfg", Number(v))}
              />
            </div>

            <div className="studio-field-group">
              <FieldLabel label="采样器 (Sampler)" />
              <Select
                value={params.sampler_name}
                onChange={(v) => updateParam("sampler_name", v as SamplerName)}
                options={[
                  { label: "euler（默认推荐）", value: "euler" },
                  { label: "euler_ancestral", value: "euler_ancestral" },
                  { label: "uni_pc", value: "uni_pc" },
                  { label: "dpmpp_2m", value: "dpmpp_2m" },
                  { label: "dpmpp_2m_sde", value: "dpmpp_2m_sde" },
                  { label: "dpmpp_3m_sde", value: "dpmpp_3m_sde" },
                  { label: "heun", value: "heun" },
                  { label: "res_multistep", value: "res_multistep" },
                  { label: "lms", value: "lms" },
                ]}
              />
            </div>

            <div className="studio-field-group">
              <FieldLabel label="调度器 (Scheduler)" />
              <Select
                value={params.scheduler}
                onChange={(v) => updateParam("scheduler", v as SchedulerName)}
                options={[
                  { label: "simple（默认推荐）", value: "simple" },
                  { label: "normal", value: "normal" },
                  { label: "beta", value: "beta" },
                  { label: "sgm_uniform", value: "sgm_uniform" },
                  { label: "karras", value: "karras" },
                  { label: "exponential", value: "exponential" },
                  { label: "ddim_uniform", value: "ddim_uniform" },
                ]}
              />
            </div>

            <div className="studio-field-group">
              <div className="studio-field-label">
                <span>重绘去噪幅度 (Denoise)</span>
                <span className="studio-tabular">{params.denoise.toFixed(2)}</span>
              </div>
              <Slider
                min={0.1}
                max={1.0}
                step={0.01}
                value={params.denoise}
                onChange={(v) => updateParam("denoise", Number(v))}
              />
            </div>
          </div>

          {/* Native <details> Disclosure for Low-Level Engine / Precision / VRAM Flags */}
          <details className="studio-native-details">
            <summary>高级引擎与显存控制（KV 缓存 / 推理精度 / 参考特征注入 / 显存释放）</summary>
            <div className="studio-details-body">
              <div className="studio-param-grid">
                {isImg2Img && (
                  <div className="studio-field-group">
                    <FieldLabel
                      label="参考图特征注入方式"
                      tooltip="VAE + 视觉双注入适合保主体精修；仅视觉语义适合提取画风自由重绘"
                    />
                    <Select
                      value={params.reference_conditioning_mode}
                      onChange={(val) =>
                        updateParam("reference_conditioning_mode", val as ReferenceConditioningMode)
                      }
                      options={[
                        { label: "VAE 潜空间 + 视觉双注入（保主体推荐）", value: "vae_and_vision" },
                        { label: "仅 Qwen3-VL 视觉语义参考", value: "vision_only" },
                      ]}
                    />
                  </div>
                )}

                <div className="studio-field-group">
                  <FieldLabel
                    label="时间步偏移 (AuraFlow Shift)"
                    tooltip="留空使用模型默认动态 Shift"
                  />
                  <InputNumber
                    style={{ inlineSize: "100%" }}
                    min={0.5}
                    max={10.0}
                    step={0.25}
                    placeholder="默认自动"
                    value={params.auraflow_shift}
                    onChange={(v) =>
                      updateParam("auraflow_shift", v === null || v === undefined ? null : Number(v))
                    }
                  />
                </div>

                <div className="studio-field-group">
                  <FieldLabel
                    label="KV 缓存位置 (QwenImage21Cache)"
                    tooltip="smart 模式在文生图使用 auto，图生图自动切 cpu 异步预取省显存"
                  />
                  <Select
                    value={params.kv_cache_device}
                    onChange={(v) => updateParam("kv_cache_device", v as KvCacheDevice)}
                    options={[
                      { label: "smart（智能自动）", value: "smart" },
                      { label: "auto（优先空闲显存）", value: "auto" },
                      { label: "cpu（主机内存预取省显存）", value: "cpu" },
                      { label: "gpu（常驻显存）", value: "gpu" },
                      { label: "off（关闭缓存）", value: "off" },
                    ]}
                  />
                </div>

                <div className="studio-field-group">
                  <FieldLabel label="KV 缓存量化精度" />
                  <Select
                    value={params.kv_cache_dtype}
                    onChange={(v) => updateParam("kv_cache_dtype", v as KvCacheDtype)}
                    options={[
                      { label: "default（BF16 无损）", value: "default" },
                      { label: "int8（体积减半）", value: "int8" },
                      { label: "int4（体积降至 1/4）", value: "int4" },
                    ]}
                  />
                </div>

                <div className="studio-field-group">
                  <FieldLabel label="UNet 权重推理精度" />
                  <Select
                    value={params.unet_weight_dtype}
                    onChange={(v) => updateParam("unet_weight_dtype", v as UnetWeightDtype)}
                    options={[
                      { label: "default（原生 BF16）", value: "default" },
                      { label: "fp8_e4m3fn（FP8 省显存）", value: "fp8_e4m3fn" },
                      { label: "fp8_e4m3fn_fast", value: "fp8_e4m3fn_fast" },
                      { label: "fp8_e5m2", value: "fp8_e5m2" },
                    ]}
                  />
                </div>

                <div className="studio-field-group">
                  <FieldLabel label="Qwen3-VL 编码器设备" />
                  <Select
                    value={params.clip_device}
                    onChange={(v) => updateParam("clip_device", v as ClipDevice)}
                    options={[
                      { label: "default（GPU 加速）", value: "default" },
                      { label: "cpu（省显存模式）", value: "cpu" },
                    ]}
                  />
                </div>

                <div className="studio-field-group">
                  <div className="studio-field-label">
                    <span>WebP / JPEG 压缩品质</span>
                    <span className="studio-tabular">{params.output_quality}</span>
                  </div>
                  <Slider
                    min={60}
                    max={100}
                    step={1}
                    disabled={params.output_format === "png"}
                    value={params.output_quality}
                    onChange={(v) => updateParam("output_quality", Number(v))}
                  />
                </div>

                <div className="studio-field-group">
                  <FieldLabel label="显存回收管理" />
                  <Space size={10} style={{ minBlockSize: 34 }}>
                    <Switch
                      size="small"
                      checked={params.release_vram_after}
                      onChange={(v) => updateParam("release_vram_after", v)}
                    />
                    <Text type="secondary" style={{ fontSize: 12 }}>任务后自动卸载</Text>
                    <Button
                      htmlType="button"
                      size="small"
                      onClick={async () => {
                        try {
                          await triggerModelRelease();
                          message.success("已发送显存释放指令");
                        } catch (err) {
                          message.error(err instanceof Error ? err.message : "释放显存失败");
                        }
                      }}
                    >
                      立即释放显存
                    </Button>
                  </Space>
                </div>
              </div>
            </div>
          </details>
        </div>
      </Card>

      {/* Sticky Primary Action Dock */}
      <div className="studio-action-dock">
        <Space wrap size={[10, 8]}>
          <Space size={6}>
            <Text style={{ fontSize: 13, fontWeight: 600 }}>种子：</Text>
            <InputNumber
              size="small"
              style={{ inlineSize: 136 }}
              min={0}
              max={Number.MAX_SAFE_INTEGER}
              step={1}
              value={params.seed}
              onChange={(v) => {
                const nextSeed = Math.max(0, Math.floor(Number(v || 0)));
                updateParam("seed", nextSeed);
                setSeedLocked(nextSeed > 0);
              }}
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
                onClick={() => {
                  if (seedLocked) updateParam("seed", 0);
                  else if (!params.seed && displayedEntry) updateParam("seed", displayedEntry.result.used_seed);
                  setSeedLocked((v) => !v);
                }}
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

          <Select
            size="small"
            style={{ inlineSize: 112 }}
            value={params.output_format}
            onChange={(v) => updateParam("output_format", v as ImageOutputFormat)}
            options={[
              { label: "PNG 无损", value: "png" },
              { label: "WebP 高清", value: "webp" },
              { label: "JPEG 通用", value: "jpeg" },
            ]}
          />
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
            onClick={() => void handleGenerate()}
          >
            {isBusy
              ? `生成中 ${Math.round((activeTask?.progress || 0.04) * 100)}%`
              : isImg2Img
                ? "立即生成（图生图）"
                : `立即生成（${snap32(params.width)}×${snap32(params.height)}）`}
          </Button>
        </Space>
      </div>
    </>
  );

  const rightPane = (
    <>
      {/* Live GPU Task Progress Card */}
      {isBusy && activeTask && (
        <Card className="studio-card" size="small">
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Space size={6}>
                <ExperimentOutlined style={{ color: "var(--studio-accent)" }} />
                <Text strong style={{ fontSize: 13 }}>
                  {activeTask.status === "queued"
                    ? `排队等待中（#${activeTask.queue_position || 1}）`
                    : "正在生成图像"}
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
              {activeTask.stage || "准备推理中..."}
            </Text>
          </div>
        </Card>
      )}

      {/* Primary Preview & A/B Comparison Stage */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <PictureOutlined style={{ color: "var(--studio-accent)" }} />
            <span>生成结果预览</span>
          </Space>
        }
        extra={
          displayedEntry?.result?.mock ? (
            <Tag color="warning" style={{ marginInlineEnd: 0 }}>本地 Mock 预览</Tag>
          ) : displayedEntry?.result ? (
            <Tag color="success" style={{ marginInlineEnd: 0 }}>GPU 渲染</Tag>
          ) : null
        }
      >
        {!displayedEntry || stageImages.length === 0 ? (
          <div
            style={{
              padding: "3rem 1.5rem",
              textAlign: "center",
              borderRadius: "0.7rem",
              background: "var(--studio-surface-subtle)",
              border: "1px dashed var(--studio-border-strong)",
            }}
          >
            <PictureOutlined style={{ fontSize: 36, color: "#94a3b8", marginBlockEnd: 10 }} />
            <div style={{ fontWeight: 600, fontSize: 14.5, color: "var(--studio-text)", marginBlockEnd: 4 }}>
              等待图像生成
            </div>
            <Text type="secondary" style={{ fontSize: 12.5 }}>
              输入提示词并选择画幅尺寸后，点击生成或按 <code>⌘/Ctrl + Enter</code>。图生图结果会自动支持原图卷帘对比。
            </Text>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            <ImageCompareStage
              images={stageImages}
              referenceUrl={stagePrimaryRefUrl}
              referenceLabel="参考图 <image1>"
              onUseAsReference={(chosen) => {
                setRefSlots((prev) => [
                  createRefSlot(`output:${chosen.filename}`),
                  ...prev.slice(1),
                ]);
                setPrimaryRefDims({ w: chosen.width, h: chosen.height });
                setParams((prev) => ({
                  ...prev,
                  mode: "img2img",
                  aspect_ratio: "match_input",
                  width: chosen.width,
                  height: chosen.height,
                }));
                message.success("已将该结果设为参考图 <image1>，可继续输入修改指令！");
              }}
            />

            {displayedEntry.result.warnings?.map((w, idx) => (
              <Alert key={idx} type="info" showIcon icon={<InfoCircleOutlined />} message={w} />
            ))}

            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "0.45rem 0.65rem",
                padding: "0.6rem 0.75rem",
                borderRadius: "0.6rem",
                background: "var(--studio-surface-subtle)",
                border: "1px solid var(--studio-border)",
              }}
            >
              <Space wrap size={[6, 6]}>
                <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                  {displayedEntry.result.width}×{displayedEntry.result.height}
                </Tag>
                <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                  {displayedEntry.result.steps} 步 · CFG {displayedEntry.result.cfg}
                </Tag>
                <Tag style={{ marginInlineEnd: 0 }}>
                  {displayedEntry.result.sampler_name}/{displayedEntry.result.scheduler}
                </Tag>
                {displayedEntry.result.active_loras?.map((l) => (
                  <Tag key={l.filename} color="blue" style={{ marginInlineEnd: 0 }}>
                    LoRA: {l.label} ({l.strength_model})
                  </Tag>
                ))}
              </Space>

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

      {/* Session Generation History Gallery */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <HistoryOutlined style={{ color: "var(--studio-accent)" }} />
            <span>本次会话历史（{historyItems.length}）</span>
          </Space>
        }
        extra={
          historyItems.length > 0 && (
            <Popconfirm
              title="清空本地会话历史记录？"
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
            当前会话生成的图片会自动保存在此，可点击切换预览或一键回填参数。
          </Text>
        ) : (
          <div className="studio-scroll-panel">
            <div className="studio-gallery-grid">
              {historyItems.map((item) => {
                const isSelected = displayedEntry?.id === item.id;
                const thumbUrl = resolveApiUrl(item.result.image_url, true);
                const promptTitle = item.params.prompt || "Qwen-Image 2.1 生成作品";
                return (
                  <div
                    key={item.id}
                    className="studio-gallery-card"
                    data-active={isSelected ? "true" : "false"}
                    onClick={() => setSelectedTakeId(item.id)}
                  >
                    <img
                      src={thumbUrl}
                      alt={promptTitle}
                      loading="lazy"
                      style={{
                        inlineSize: "100%",
                        aspectRatio: "1 / 1",
                        objectFit: "cover",
                        background: "#e2e8f0",
                      }}
                    />
                    <div style={{ padding: "0.45rem 0.55rem", display: "flex", flexDirection: "column", gap: 4 }}>
                      <div
                        style={{
                          fontSize: 11.5,
                          fontWeight: 500,
                          color: "var(--studio-text)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {promptTitle}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
                        <span className="studio-tabular" style={{ fontSize: 10.5, color: "var(--studio-text-muted)" }}>
                          {item.result.width}×{item.result.height}
                        </span>
                        <Button
                          htmlType="button"
                          size="small"
                          type="link"
                          style={{ padding: 0, blockSize: "auto", fontSize: 11.5 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setParams({ ...item.params, seed: item.result.used_seed });
                            setSeedLocked(true);
                            setShowNegPrompt(Boolean(item.params.negative_prompt));
                            setPrimaryRefDims(null);
                            setRefSlots(item.params.reference_images?.length
                              ? item.params.reference_images.map((ref) => createRefSlot(ref))
                              : [createRefSlot("")]);
                            message.info("已回填该作品的生成参数");
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
      brandBadge="QW"
      defaultTitle="Qwen-Image 2.1 图像生成工作台"
      defaultSubtitle="原生 2K 文生图 · 图生图（支持可选多图参考） · 在线 LoRA 挂载"
      apiEndpointPath="/api/v1/generate"
      mediaKind="image"
      sampleRequestBody={sampleRequestBody}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
