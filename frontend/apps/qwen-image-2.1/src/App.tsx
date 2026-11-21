import type { StageImageEntry } from "@colab/shared";
import {
  Alert,
  Button,
  Card,
  ChoiceButton,
  ClearOutlined,
  CollapsibleSection,
  DeleteOutlined,
  DownloadOutlined,
  Empty,
  ExperimentOutlined,
  FieldLabel,
  GenerateButton,
  HistoryOutlined,
  ImageCompareStage,
  ImageLightbox,
  ImageSourceField,
  InfoCircleOutlined,
  Input,
  InputNumber,
  Kbd,
  LockOutlined,
  LoraManagerPanel,
  PictureOutlined,
  PlusOutlined,
  Popconfirm,
  Progress,
  ScrollArea,
  SeedControl,
  Segmented,
  Select,
  Slider,
  Space,
  StudioShell,
  SwapOutlined,
  Tag,
  Text,
  TextArea,
  TokenChip,
  Tooltip,
  imageDownloadUrl,
  resolveApiUrl,
  useHistoryStore,
  useStudioFeedback,
  useStudioLocale,
  useTaskRunner,
} from "@colab/shared";
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { buildStudioImageRequest, type QwenImageStudioRequest } from "./request";
import type {
  AspectRatioChoice,
  ImageOutputFormat,
  QwenImageParams,
  QwenImageResult,
  ResolutionTier,
  StandardAspectRatio,
} from "./types";
import {
  ASPECT_RATIO_OPTIONS,
  DEFAULT_QWEN_IMAGE_PARAMS,
  MAX_REFERENCE_IMAGES,
  SYMMETRIC_RATIO_SWAP,
  calcPresetDimensions,
  calcRefMatchedDimensions,
  editImageGeometry,
  snap32,
} from "./types";

const EN_ASPECT_SUBLABELS: Record<StandardAspectRatio, string> = {
  "1:1": "Square",
  "16:9": "Landscape",
  "9:16": "Portrait",
  "4:3": "Standard",
  "3:4": "Portrait",
  "3:2": "Photo",
  "2:3": "Poster",
  "21:9": "Ultrawide",
};

function resultImages(result: QwenImageResult): StageImageEntry[] {
  const list = result.images?.length
    ? result.images
    : [
        {
          url: result.image_url,
          filename: result.filename,
          width: result.width,
          height: result.height,
          size_bytes: result.size_bytes,
          format: result.format,
        },
      ];
  return list.map((it) => ({
    url: resolveApiUrl(it.url),
    filename: it.filename,
    width: it.width,
    height: it.height,
    sizeBytes: it.size_bytes,
    format: it.format,
  }));
}

export function QwenImageStudioApp() {
  const { isZh, t } = useStudioLocale();
  const promptInputId = useId();
  const negPromptInputId = useId();
  const widthInputId = useId();
  const heightInputId = useId();
  const outputFormatId = useId();
  const batchSizeId = useId();
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
  const [historyPreview, setHistoryPreview] = useState<StageImageEntry[]>([]);

  const { items: historyItems, addEntry, clearAll } = useHistoryStore<
    QwenImageResult,
    QwenImageParams
  >("qwen-image-2.1", 24);

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<
    QwenImageResult,
    QwenImageStudioRequest
  >({
    endpointPath: "/api/v1/generate",
    onSuccess: (finishedTask) => {
      if (finishedTask.result) {
        addEntry({
          id: finishedTask.task_id,
          feature: "qwen-image-2.1",
          createdAt: finishedTask.finished_at || new Date().toISOString(),
          elapsedSec: finishedTask.elapsed_sec,
          params: { ...DEFAULT_QWEN_IMAGE_PARAMS, ...finishedTask.params },
          result: finishedTask.result,
        });
        setSelectedTakeId(finishedTask.task_id);
        if (seedLocked && finishedTask.result.used_seed) {
          setParams((prev) => ({ ...prev, seed: finishedTask.result!.used_seed }));
        }
        message.success(
          t(
            `Generation completed (${finishedTask.result.width}×${finishedTask.result.height}${
              finishedTask.elapsed_sec ? ` · ${finishedTask.elapsed_sec}s` : ""
            })`,
            `生成完成（${finishedTask.result.width}×${finishedTask.result.height}${
              finishedTask.elapsed_sec ? ` · ${finishedTask.elapsed_sec}s` : ""
            }）`,
          ),
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
    message.success(t("Reset to default parameters", "已恢复默认参数"));
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

  const buildCleanedPayload = useCallback(
    (): QwenImageStudioRequest =>
      buildStudioImageRequest(params, isImg2Img ? cleanUploadedRefs : []),
    [cleanUploadedRefs, isImg2Img, params]
  );

  const handleGenerate = useCallback(async () => {
    if (isBusy) return;
    if (!params.prompt.trim()) {
      message.warning(t("Please enter a prompt or editing instruction.", "请先输入画面描述或图像编辑指令。"));
      return;
    }
    if (isImg2Img && cleanUploadedRefs.length < 1) {
      message.warning(t("Image-to-Image mode requires at least 1 reference image (<image1>).", "图生图模式请先上传至少 1 张参考图片 (<image1>)。"));
      return;
    }
    if (isImg2Img) {
      if (
        params.resolution_tier === "original" &&
        primaryRefDims &&
        (primaryRefDims.w > 4096 || primaryRefDims.h > 4096)
      ) {
        message.warning(
          t(
            "Primary reference exceeds 4096 px per side; switch to 1K or 2K since Original mode does not downscale.",
            "主参考图超过单边 4096 像素上限，请改选 1K / 2K；原图模式不会静默缩小图片。",
          ),
        );
        return;
      }
      const firstEmpty = refSlots.findIndex((slot) => !slot.fileRef.trim());
      if (firstEmpty >= 0 && refSlots.slice(firstEmpty + 1).some((slot) => slot.fileRef.trim())) {
        message.warning(
          t(
            `Reference ${firstEmpty + 1} is empty; upload an image or remove the blank card to keep <imageN> indices aligned.`,
            `参考图 ${firstEmpty + 1} 尚未上传，请补充图片或删除这张空卡片，让图片与 <imageN> 编号保持一致。`,
          ),
        );
        return;
      }
    }
    await runTask(buildCleanedPayload());
  }, [
    buildCleanedPayload,
    cleanUploadedRefs.length,
    isBusy,
    isImg2Img,
    message,
    params.prompt,
    params.resolution_tier,
    primaryRefDims,
    refSlots,
    runTask,
    t,
  ]);

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
        params: { ...DEFAULT_QWEN_IMAGE_PARAMS, ...activeTask.params },
        result: activeTask.result,
      };
    }
    return historyItems[0] || null;
  }, [activeTask, historyItems, selectedTakeId]);

  const stageImages: StageImageEntry[] = useMemo(() => {
    if (!displayedEntry?.result) return [];
    return resultImages(displayedEntry.result);
  }, [displayedEntry]);

  const stagePrimaryRefUrl = useMemo(() => {
    const r0 = displayedEntry?.result?.reference_urls?.[0];
    return r0 ? resolveApiUrl(r0) : undefined;
  }, [displayedEntry]);

  const negPromptNeedsCfgHint = Boolean(params.negative_prompt.trim()) && params.cfg <= 1.01;
  const activeLoraCount = params.loras.filter((slot) => slot.enabled).length;
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
                { label: t("Text to Image", "文生图"), value: "t2i" },
                { label: t("Image Edit / Img2Img", "图生图 / 编辑"), value: "img2img" },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12.5, fontWeight: 400 }}>
              {isImg2Img
                ? t(
                    "Upload a primary reference image and optional multi-image references",
                    "上传 1 张主参考图，可按需添加多张图片进行融合参考",
                  )
                : t(
                    "Generate crisp 1K / 2K images directly from English or Chinese prompts",
                    "输入中英文描述直接生成 1K / 2K 高清图像",
                  )}
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
            {t("Reset", "恢复默认")}
          </Button>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.95rem" }}>
          {isImg2Img && (
            <div className="studio-reference-group">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, minBlockSize: 24 }}>
                <Text strong style={{ fontSize: 13 }}>
                  {t("Reference Images (", "参考图片（已上传 ")}
                  <span className="studio-tabular">{cleanUploadedRefs.length}</span> / {MAX_REFERENCE_IMAGES}
                  {t(")", " 张）")}
                </Text>

                {refSlots.length < MAX_REFERENCE_IMAGES && (
                  <Button
                    htmlType="button"
                    size="small"
                    type="dashed"
                    icon={<PlusOutlined />}
                    onClick={() => setRefSlots((prev) => [...prev, createRefSlot("")])}
                  >
                    {t("Add Reference", "添加参考图")}
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
                    label={idx === 0 ? t("Primary Reference", "主参考图") : t(`Reference ${idx + 1}`, `参考图 ${idx + 1}`)}
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
                {isImg2Img ? t("Edit / Img2Img Prompt", "编辑 / 图生图指令 (Prompt)") : t("Prompt", "提示词 (Prompt)")}
              </label>
              <Space size={8} wrap>
                {isImg2Img && (
                  <Space size={4} wrap>
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                      {t("Insert token:", "点击插入引用：")}
                    </Text>
                    {refSlots.map((slot, i) => {
                      const tok = `<image${i + 1}>`;
                      return (
                        <TokenChip key={slot.id} onClick={() => insertTokenAtCursor(tok)}>
                          {tok}
                        </TokenChip>
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
                  {showNegPrompt || params.negative_prompt
                    ? t("Hide Negative Prompt", "收起反向提示词")
                    : t("+ Negative Prompt", "+ 反向提示词")}
                </Button>
              </Space>
            </div>

            <TextArea
              ref={promptRef}
              id={promptInputId}
              rows={4}
              maxLength={8000}
              value={params.prompt}
              onValueChange={(value) => updateParam("prompt", value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void handleGenerate();
                }
              }}
              placeholder={
                isImg2Img
                  ? t(
                      "Describe edits, e.g., keep the subject from <image1> and place them on a sunset beach (or blend with <image2>)...",
                      "输入修改要求，例如：保留 <image1> 中的人物，将背景替换为海边落日（如上传了第 2 张图可写：融合到 <image2> 的场景中）...",
                    )
                  : t(
                      "Describe subject, environment, camera framing, lighting style, or text to render...",
                      "描述画面主体、场景环境、构图视角、光影风格或需要渲染的文字内容...",
                    )
              }
            />

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12, color: "var(--studio-text-muted)" }}>
              <span className="studio-shortcut-hint">
                <Kbd keys={["mod", "enter"]} size="sm" />
                <span>{t("Generate", "生成")}</span>
              </span>
              <span className="studio-tabular">{params.prompt.length} / 8000</span>
            </div>
          </div>

          {(showNegPrompt || Boolean(params.negative_prompt)) && (
            <div className="studio-field-group">
              <div className="studio-field-label">
                <label htmlFor={negPromptInputId}>{t("Negative Prompt", "反向提示词 (Negative Prompt)")}</label>
              </div>
              <Input
                id={negPromptInputId}
                value={params.negative_prompt}
                onValueChange={(value) => updateParam("negative_prompt", value)}
                placeholder={t(
                  "Exclude unwanted artifacts, e.g., blur, low quality, extra fingers, watermark...",
                  "排除不需要的元素，例如：模糊、低画质、多余手指、水印...",
                )}
              />
              {negPromptNeedsCfgHint && (
                <Alert
                  type="warning"
                  showIcon
                  message={
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                      <span>
                        {t(
                          "Negative prompts have no effect at CFG 1.0; raise CFG to ~3.0 to enable negative guidance.",
                          "当前 CFG 为 1.0，反向提示词不会生效；调至 3.0 左右可启用负向抑制。",
                        )}
                      </span>
                      <Button
                        htmlType="button"
                        size="small"
                        type="primary"
                        ghost
                        onClick={() => updateParam("cfg", 3.0)}
                      >
                        {t("Set CFG 3.0", "设为 CFG 3.0")}
                      </Button>
                    </div>
                  }
                />
              )}
            </div>
          )}
        </div>
      </Card>

      {/* 2. Independent Resolution, Aspect Ratio & Pixel Dimensions */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <PictureOutlined style={{ color: "var(--studio-accent)" }} />
            <span>{t("Aspect Ratio, Resolution & Dimensions", "画幅比例、分辨率与尺寸")}</span>
          </Space>
        }
        extra={
          <span className="studio-tabular" style={{ fontSize: 12.5, color: "var(--studio-text-secondary)", fontWeight: 600 }}>
            {snap32(params.width)} × {snap32(params.height)} px ({megapixels} MP)
          </span>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: "0.75rem 1.25rem" }}>
            <div className="studio-field-group" style={{ flex: "1 1 260px" }}>
              <FieldLabel
                label={t("Resolution Tier", "分辨率档位 (Resolution)")}
                tooltip={t(
                  "Controls target pixel budget: 1K (~1 MP, fast) or 2K (~4 MP, ultra-sharp detail).",
                  "独立控制清晰度基准：1K 约 100 万像素（快速出图），2K 约 400 万像素（原生超清细节）",
                )}
              />
              <Segmented
                block
                value={params.resolution_tier}
                onChange={(val) => handleResolutionChange(val as ResolutionTier)}
                options={[
                  { label: t("1K Standard", "1K 标清"), value: "1K" },
                  { label: t("2K Ultra HD", "2K 超清"), value: "2K" },
                  ...(isImg2Img ? [{ label: t("Original", "原图分辨率"), value: "original" }] : []),
                ]}
              />
            </div>
          </div>

          <div className="studio-field-group">
            <FieldLabel
              label={t("Aspect Ratio", "宽高比 (Aspect Ratio)")}
              tooltip={t(
                "Selecting a preset recalculates width & height for the active resolution tier, or enter custom dimensions below.",
                "点选比例会自动按当前分辨率换算像素宽高；也可直接在下方输入任意自定义宽高",
              )}
            />
            <div className="studio-aspect-grid">
              {isImg2Img && (
                <ChoiceButton
                  type="button"
                  className="studio-aspect-pill"
                  active={params.aspect_ratio === "match_input"}
                  onClick={() => handleAspectChange("match_input")}
                >
                  <span
                    className="studio-aspect-frame"
                    style={{ inlineSize: 18, blockSize: 18, borderStyle: "dashed" }}
                  />
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{t("Match Input", "跟随参考图")}</span>
                  <span style={{ fontSize: 10.5, opacity: 0.75 }}>
                    {primaryRefDims ? `${primaryRefDims.w}:${primaryRefDims.h}` : t("Keep ratio", "保持比例")}
                  </span>
                </ChoiceButton>
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
                  <ChoiceButton
                    key={opt.value}
                    type="button"
                    className="studio-aspect-pill"
                    active={params.aspect_ratio === opt.value}
                    onClick={() => handleAspectChange(opt.value)}
                  >
                    <span
                      className="studio-aspect-frame"
                      style={{ inlineSize: fw, blockSize: fh }}
                    />
                    <span style={{ fontSize: 12.5, fontWeight: 600 }}>{opt.label}</span>
                    <span style={{ fontSize: 10.5, opacity: 0.75 }}>
                      {isZh ? opt.sub : EN_ASPECT_SUBLABELS[opt.value]}
                    </span>
                  </ChoiceButton>
                );
              })}

              <ChoiceButton
                type="button"
                className="studio-aspect-pill"
                active={params.aspect_ratio === "custom"}
                onClick={() => handleAspectChange("custom")}
              >
                <span
                  className="studio-aspect-frame"
                  style={{ inlineSize: 19, blockSize: 15, borderRadius: 2 }}
                />
                <span style={{ fontSize: 12, fontWeight: 600 }}>{t("Custom", "自定义")}</span>
                <span style={{ fontSize: 10.5, opacity: 0.75 }}>{t("Freeform", "自由宽高")}</span>
              </ChoiceButton>
            </div>
          </div>

          <div className="studio-dim-bar">
            <div className="studio-dimension-fields">
              <div className="studio-field-group">
                <label htmlFor={widthInputId} style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)" }}>
                  {t("Width W (px)", "宽度 W (px)")}
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

              <Tooltip title={t("Swap width & height", "互换宽度与高度")}>
                <Button
                  htmlType="button"
                  icon={<SwapOutlined />}
                  onClick={handleSwapDimensions}
                  aria-label={t("Swap width & height", "互换宽度与高度")}
                />
              </Tooltip>

              <div className="studio-field-group">
                <label htmlFor={heightInputId} style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)" }}>
                  {t("Height H (px)", "高度 H (px)")}
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
                ? t("Matches reference proportions after upload (32px aligned)", "上传参考图后自动按原图比例匹配像素尺寸（32px 对齐）")
                : t(
                    `Output: ${snap32(params.width)} × ${snap32(params.height)} px (32px aligned)`,
                    `实际输出尺寸：${snap32(params.width)} × ${snap32(params.height)} px（自动 32px 对齐）`,
                  )}
            </Text>
          </div>
        </div>
      </Card>

      <CollapsibleSection
        className="studio-lora-accordion"
        title={t("Style Models (LoRA, optional)", "风格模型（LoRA，可选）")}
        subtitle={t("Mount style or detail enhancement weights on demand", "按需挂载风格或细节增强权重")}
        leading={<ExperimentOutlined />}
        trailingBadge={activeLoraCount > 0 ? t(`${activeLoraCount} active`, `已启用 ${activeLoraCount} 个`) : undefined}
      >
        <LoraManagerPanel
          slots={params.loras}
          onChange={(nextSlots) => updateParam("loras", nextSlots)}
        />
      </CollapsibleSection>

      <Card className="studio-card" title={t("Generation Settings", "生成设置")}>
        <div className="studio-settings-grid">
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>{t("Steps", "步数")}</span>
              <span className="studio-tabular">{t(`${params.steps} steps`, `${params.steps} 步`)}</span>
            </div>
            <Slider aria-label={t("Steps", "生成步数")} min={8} max={80} step={1} value={params.steps} onChange={(value) => updateParam("steps", value)} />
          </div>
          <div className="studio-field-group">
            <div className="studio-field-label">
              <span>{t("Guidance (CFG)", "引导强度（CFG）")}</span>
              <span className="studio-tabular">{params.cfg.toFixed(1)}</span>
            </div>
            <Slider aria-label={t("Guidance (CFG)", "引导强度")} min={1} max={10} step={0.1} value={params.cfg} onChange={(value) => updateParam("cfg", value)} />
          </div>
          {isImg2Img && (
            <div className="studio-field-group">
              <div className="studio-field-label">
                <span>{t("Denoise Strength", "重绘强度")}</span>
                <span className="studio-tabular">{params.denoise.toFixed(2)}</span>
              </div>
              <Slider aria-label={t("Denoise strength", "重绘强度")} min={0.1} max={1} step={0.01} value={params.denoise} onChange={(value) => updateParam("denoise", value)} />
            </div>
          )}
          <div className="studio-field-group">
            <label htmlFor={outputFormatId} className="studio-field-label">
              <span>{t("Output Format", "输出格式")}</span>
            </label>
            <Select
              id={outputFormatId}
              aria-label={t("Output format", "输出格式")}
              value={params.output_format}
              onChange={(value) => updateParam("output_format", value as ImageOutputFormat)}
              options={[
                { label: "PNG", value: "png" },
                { label: "WebP", value: "webp" },
                { label: "JPEG", value: "jpeg" },
              ]}
            />
          </div>
          <div className="studio-field-group">
            <label htmlFor={batchSizeId} className="studio-field-label">
              <span>{t("Batch Size", "生成数量")}</span>
            </label>
            <Select
              id={batchSizeId}
              aria-label={t("Batch size", "生成数量")}
              value={String(params.batch_size)}
              onChange={(value) => updateParam("batch_size", Number(value))}
              options={[1, 2, 3, 4].map((count) => ({
                label: t(`${count}`, `${count} 张`),
                value: String(count),
              }))}
            />
          </div>
          <SeedControl
            value={params.seed}
            onChange={(value) => updateParam("seed", value)}
            onLockedChange={setSeedLocked}
          />
        </div>
      </Card>

      <GenerateButton
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
                    : t("Generating image", "正在生成图像")}
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
              {activeTask.stage || t("Preparing inference...", "准备推理中...")}
            </Text>
          </div>
        </Card>
      )}

      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <PictureOutlined style={{ color: "var(--studio-accent)" }} />
            <span>{t("Generated Result", "生成结果预览")}</span>
          </Space>
        }
        extra={
          displayedEntry?.result?.mock ? (
            <Tag color="warning" style={{ marginInlineEnd: 0 }}>{t("Mock Preview", "本地 Mock 预览")}</Tag>
          ) : displayedEntry?.result ? (
            <Tag color="success" style={{ marginInlineEnd: 0 }}>{t("GPU Render", "GPU 渲染")}</Tag>
          ) : null
        }
      >
        {!displayedEntry || stageImages.length === 0 ? (
          <Empty
            title={t("Ready to Generate", "等待图像生成")}
            description={t(
              "Enter a prompt, pick your aspect ratio, and click Generate. Img2Img results automatically support split comparison.",
              "输入提示词并选择画幅尺寸后点击生成；图生图结果会自动支持原图卷帘对比。",
            )}
            icon={<PictureOutlined />}
            shape="clover4Leaf"
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            <ImageCompareStage
              images={stageImages}
              referenceUrl={stagePrimaryRefUrl}
              referenceLabel={t("Reference <image1>", "参考图 <image1>")}
              resultLabel={t("Qwen-Image 2.1 Result", "Qwen-Image 2.1 生成结果")}
              useAsReferenceLabel={t("Use as <image1>", "设为 <image1> 继续精修")}
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
                message.success(t("Set as <image1> reference for follow-up edits", "已将该结果设为参考图 <image1>，可继续输入修改指令！"));
              }}
            />

            {displayedEntry.result.warnings?.map((w, idx) => (
              <Alert key={idx} type="info" showIcon icon={<InfoCircleOutlined />} message={w} />
            ))}

            <div className="studio-meta-bar">
              <Space wrap size={[6, 6]}>
                <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                  {displayedEntry.result.width}×{displayedEntry.result.height}
                </Tag>
                <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                  {t(`${displayedEntry.result.steps} steps`, `${displayedEntry.result.steps} 步`)} · CFG {displayedEntry.result.cfg}
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
                  message.success(t(`Locked seed: ${displayedEntry.result.used_seed}`, `已锁定种子：${displayedEntry.result.used_seed}`));
                }}
              >
                {t("Use this seed", "使用此种子")}
              </Button>
            </div>
          </div>
        )}
      </Card>

      <ImageLightbox images={historyPreview} open={historyPreview.length > 0} onClose={() => setHistoryPreview([])} />

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
              title={t("Clear current session history?", "清空本地会话历史记录？")}
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
              "Images generated in this session appear here for preview and one-click parameter reuse.",
              "当前会话生成的图片会自动保存在此，可点击切换预览或一键再次使用。",
            )}
          </Text>
        ) : (
          <ScrollArea maxHeight={420}>
            <div className="studio-gallery-grid" style={{ paddingInlineEnd: 8 }}>
              {historyItems.map((item) => {
                const isSelected = displayedEntry?.id === item.id;
                const thumbUrl = resolveApiUrl(item.result.image_url);
                const promptTitle = item.params.prompt || t("Qwen-Image 2.1 Output", "Qwen-Image 2.1 生成作品");
                return (
                  <div
                    key={item.id}
                    className="studio-gallery-card"
                    data-active={isSelected ? "true" : "false"}
                  >
                    <button
                      type="button"
                      className="studio-gallery-open"
                      aria-label={t("Inspect image", "查看历史图片")}
                      onClick={() => {
                        setSelectedTakeId(item.id);
                        setHistoryPreview(resultImages(item.result));
                      }}
                    >
                      <img
                        src={thumbUrl}
                        alt={promptTitle}
                        loading="lazy"
                        style={{
                          inlineSize: "100%",
                          aspectRatio: "1 / 1",
                          objectFit: "contain",
                          background: "var(--m3e-color-surface-container)",
                        }}
                      />
                    </button>
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
                      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
                        <span className="studio-tabular" style={{ flexBasis: "100%", fontSize: 10.5, color: "var(--studio-text-muted)" }}>
                          {item.result.width}×{item.result.height}
                        </span>
                        <Button
                          size="small"
                          type="text"
                          href={imageDownloadUrl(thumbUrl)}
                          download={item.result.filename}
                          icon={<DownloadOutlined />}
                          aria-label={t("Download image", "下载历史图片")}
                        />
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
                            setRefSlots(
                              item.params.reference_images?.length
                                ? item.params.reference_images.map((ref) => createRefSlot(ref))
                                : [createRefSlot("")],
                            );
                            message.info(t("Restored settings from history", "已回填该作品的生成参数"));
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
      brandBadge="QW"
      defaultTitle="Qwen-Image 2.1"
      defaultSubtitle={t("Text to Image · Image Editing · Multi-Reference", "文生图 · 图像编辑 · 多图参考")}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
