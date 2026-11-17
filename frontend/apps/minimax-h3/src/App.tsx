import {
Alert,
AudioOutlined,
Button,
Card,
ChoiceButton,
ClearOutlined,
DeleteOutlined,
DownloadOutlined,
ExperimentOutlined,
GenerateDock,
HistoryOutlined,
ImageSourceField,
InfoCircleOutlined,
Input,
InputNumber,
LockOutlined,
LoraManagerPanel,
PlusOutlined,
Popconfirm,
Progress,
QuestionCircleOutlined,
SeedControl,
Segmented,
Slider,
SoundOutlined,
Space,
StudioShell,
SwapOutlined,
Switch,
Tag,
Text,
TextArea,
Tooltip,
VideoCameraOutlined,
resolveApiUrl,
useHistoryStore,
useStudioFeedback,
useTaskRunner
} from "@colab/shared";
import { useCallback,useId,useMemo,useRef,useState } from "react";
import { AudioSlotCard,VideoSlotCard } from "./MediaSlotFields";
import { buildVideoStudioRequest,type MiniMaxStudioRequest } from "./request";
import type {
H3AspectRatio,
H3Mode,
H3ResolutionTier,
MiniMaxH3Params,
MiniMaxH3Result,
VideoOutputFormat
} from "./types";
import {
ASPECT_RATIO_OPTIONS,
DEFAULT_MINIMAX_H3_PARAMS,
DURATION_PRESETS,
H3_REFERENCE_LIMITS,
NATIVE_FPS,
SYMMETRIC_RATIO_SWAP,
alignH3Frames,
calcH3Dimensions,
calcRefMatchedDimensions,
durationToH3Frames,
snap32,
} from "./types";

interface ImageSlotState {
  id: string;
  fileRef: string;
}

interface VideoSlotState {
  id: string;
  fileRef: string;
  useVideoAudio: boolean;
}

interface AudioSlotState {
  id: string;
  fileRef: string;
}

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

function defaultTurboStepsForMode(mode: H3Mode): number {
  return mode === "r2v" ? 4 : 8;
}

export function MiniMaxH3StudioApp() {
  const promptInputId = useId();
  const negPromptInputId = useId();
  const widthInputId = useId();
  const heightInputId = useId();
  const fpsInputId = useId();
  const exactFramesInputId = useId();
  const promptRef = useRef<HTMLTextAreaElement | null>(null);
  const { message } = useStudioFeedback();

  const nextSlotSeqRef = useRef(2);
  const nextId = useCallback((prefix: string) => {
    const id = `${prefix}-${nextSlotSeqRef.current}`;
    nextSlotSeqRef.current += 1;
    return id;
  }, []);

  const [params, setParams] = useState<MiniMaxH3Params>(DEFAULT_MINIMAX_H3_PARAMS);
  const [refImageSlots, setRefImageSlots] = useState<ImageSlotState[]>([
    { id: "img-1", fileRef: "" },
  ]);
  const [refVideoSlots, setRefVideoSlots] = useState<VideoSlotState[]>([]);
  const [refAudioSlots, setRefAudioSlots] = useState<AudioSlotState[]>([]);

  const [fl2vPrimaryDims, setFl2vPrimaryDims] = useState<{ w: number; h: number } | null>(null);
  const [r2vPrimaryDims, setR2vPrimaryDims] = useState<{ w: number; h: number } | null>(null);

  const [seedLocked, setSeedLocked] = useState(false);
  const [showNegPrompt, setShowNegPrompt] = useState(false);
  const [selectedTakeId, setSelectedTakeId] = useState<string | null>(null);
  const [stageViewMode, setStageViewMode] = useState<"video" | "reference">("video");

  const { items: historyItems, addEntry, clearAll } = useHistoryStore<
    MiniMaxH3Result,
    MiniMaxH3Params
  >("minimax-h3", 20);

  const { activeTask, isBusy, runTask, cancelActive } = useTaskRunner<
    MiniMaxH3Result,
    MiniMaxStudioRequest
  >({
    endpointPath: "/api/v1/generate",
    onSuccess: (finishedTask) => {
      if (finishedTask.result) {
        addEntry({
          id: finishedTask.task_id,
          feature: "minimax-h3",
          createdAt: finishedTask.finished_at || new Date().toISOString(),
          elapsedSec: finishedTask.elapsed_sec,
          params: { ...DEFAULT_MINIMAX_H3_PARAMS, ...finishedTask.params },
          result: finishedTask.result,
        });
        setSelectedTakeId(finishedTask.task_id);
        setStageViewMode("video");
        if (seedLocked && finishedTask.result.used_seed) {
          setParams((prev) => ({ ...prev, seed: finishedTask.result!.used_seed }));
        }
        message.success(
          `视频生成完成（${finishedTask.result.width}×${finishedTask.result.height} · ${finishedTask.result.duration_sec}s）`
        );
      }
    },
    onError: (errMsg) => {
      message.error(errMsg);
    },
  });

  const activePrimaryDims =
    params.mode === "fl2v" ? fl2vPrimaryDims : params.mode === "r2v" ? r2vPrimaryDims : null;

  const updateParam = <K extends keyof MiniMaxH3Params>(key: K, val: MiniMaxH3Params[K]) => {
    setParams((prev) => ({ ...prev, [key]: val }));
  };

  // Switch between T2V, First-Last Frame I2V, and Multimodal R2V cleanly
  const handleModeSwitch = (nextMode: H3Mode) => {
    const nextRefDims =
      nextMode === "fl2v" ? fl2vPrimaryDims : nextMode === "r2v" ? r2vPrimaryDims : null;

    setParams((prev) => {
      const prevDefaultTurbo = defaultTurboStepsForMode(prev.mode);
      const nextDefaultTurbo = defaultTurboStepsForMode(nextMode);
      const nextSteps =
        prev.turbo_enabled && prev.steps === prevDefaultTurbo ? nextDefaultTurbo : prev.steps;

      if (nextMode === "t2v") {
        const nextTier: H3ResolutionTier =
          prev.resolution_tier === "custom" ? "768p" : prev.resolution_tier;
        const nextAspect: H3AspectRatio =
          prev.aspect_ratio === "match_input" ? "16:9" : prev.aspect_ratio;
        const dims =
          nextAspect === "custom"
            ? { width: prev.width, height: prev.height }
            : calcH3Dimensions(nextTier, nextAspect);
        return {
          ...prev,
          mode: "t2v",
          resolution_tier: nextTier,
          aspect_ratio: nextAspect,
          width: dims.width,
          height: dims.height,
          steps: nextSteps,
        };
      }

      if (nextMode === "fl2v") {
        const nextAspect: H3AspectRatio =
          prev.aspect_ratio === "custom" ? "custom" : nextRefDims ? "match_input" : prev.aspect_ratio;
        const dims =
          nextAspect === "match_input"
            ? calcRefMatchedDimensions(prev.resolution_tier, nextRefDims)
            : nextAspect === "custom"
              ? { width: prev.width, height: prev.height }
              : calcH3Dimensions(prev.resolution_tier, nextAspect);
        return {
          ...prev,
          mode: "fl2v",
          aspect_ratio: nextAspect,
          width: dims.width,
          height: dims.height,
          steps: nextSteps,
        };
      }

      // r2v mode
      const nextAspect: H3AspectRatio =
        prev.aspect_ratio === "match_input" && !nextRefDims ? "16:9" : prev.aspect_ratio;
      const dims =
        nextAspect === "match_input"
          ? calcRefMatchedDimensions(prev.resolution_tier, nextRefDims)
          : nextAspect === "custom"
            ? { width: prev.width, height: prev.height }
            : calcH3Dimensions(prev.resolution_tier, nextAspect);
      return {
        ...prev,
        mode: "r2v",
        aspect_ratio: nextAspect,
        width: dims.width,
        height: dims.height,
        steps: nextSteps,
      };
    });
  };

  const handleResolutionChange = (nextTier: H3ResolutionTier) => {
    setParams((prev) => {
      if (prev.aspect_ratio === "custom") {
        return { ...prev, resolution_tier: nextTier };
      }
      if (prev.aspect_ratio === "match_input") {
        const matched = calcRefMatchedDimensions(nextTier, activePrimaryDims);
        return {
          ...prev,
          resolution_tier: nextTier,
          width: matched.width,
          height: matched.height,
        };
      }
      const dims = calcH3Dimensions(nextTier, prev.aspect_ratio);
      return {
        ...prev,
        resolution_tier: nextTier,
        width: dims.width,
        height: dims.height,
      };
    });
  };

  const handleAspectChange = (nextAspect: H3AspectRatio) => {
    setParams((prev) => {
      if (nextAspect === "custom") {
        return { ...prev, aspect_ratio: "custom" };
      }
      if (nextAspect === "match_input") {
        const matched = calcRefMatchedDimensions(prev.resolution_tier, activePrimaryDims);
        return {
          ...prev,
          aspect_ratio: "match_input",
          width: matched.width,
          height: matched.height,
        };
      }
      const effectiveTier: H3ResolutionTier =
        prev.resolution_tier === "custom" ? "768p" : prev.resolution_tier;
      const dims = calcH3Dimensions(effectiveTier, nextAspect);
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
      let nextAspect: H3AspectRatio = prev.aspect_ratio;
      if (prev.aspect_ratio !== "custom" && prev.aspect_ratio !== "match_input") {
        const swapped = SYMMETRIC_RATIO_SWAP[prev.aspect_ratio];
        nextAspect = swapped || (prev.aspect_ratio === "1:1" ? "1:1" : "custom");
      } else if (prev.aspect_ratio === "match_input") {
        nextAspect = "custom";
      }
      return {
        ...prev,
        aspect_ratio: nextAspect,
        width: nextW,
        height: nextH,
      };
    });
  };

  const handleToggleTurbo = (enabled: boolean) => {
    setParams((prev) => {
      const targetTurboSteps = defaultTurboStepsForMode(prev.mode);
      let nextSteps = prev.steps;
      if (enabled) {
        if (prev.steps === 20 || prev.steps === 8 || prev.steps === 4) {
          nextSteps = targetTurboSteps;
        }
      } else if (prev.steps === 8 || prev.steps === 4) {
        nextSteps = 20;
      }
      return {
        ...prev,
        turbo_enabled: enabled,
        steps: nextSteps,
      };
    });
  };

  const handleFl2vPrimaryDimsDetected = useCallback((dims: { w: number; h: number } | null) => {
    setFl2vPrimaryDims(dims);
    if (dims) {
      setParams((prev) => {
        if (prev.mode === "fl2v") {
          const useMatch = prev.aspect_ratio === "match_input" || prev.aspect_ratio === "16:9";
          if (useMatch) {
            const matched = calcRefMatchedDimensions(prev.resolution_tier, dims);
            return {
              ...prev,
              aspect_ratio: "match_input",
              width: matched.width,
              height: matched.height,
            };
          }
        }
        return prev;
      });
    }
  }, []);

  const handleR2vPrimaryDimsDetected = useCallback((dims: { w: number; h: number } | null) => {
    setR2vPrimaryDims(dims);
    if (dims) {
      setParams((prev) => {
        if (prev.mode === "r2v" && prev.aspect_ratio === "match_input") {
          const matched = calcRefMatchedDimensions(prev.resolution_tier, dims);
          return { ...prev, width: matched.width, height: matched.height };
        }
        return prev;
      });
    }
  }, []);

  const resetAllDefaults = () => {
    setSeedLocked(false);
    setRefImageSlots([{ id: nextId("img"), fileRef: "" }]);
    setRefVideoSlots([]);
    setRefAudioSlots([]);
    setFl2vPrimaryDims(null);
    setR2vPrimaryDims(null);
    setParams(DEFAULT_MINIMAX_H3_PARAMS);
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

  // Compute exact 1-based H3 modality tags matching MiniMaxH3ReferenceToVideo:
  // Images -> <Picture 1..N>, Videos -> <Video 1..K>, Video Audios (use_video_audio) -> <Audio 1..J>, Standalone Audios -> <Audio J+1..M>
  const r2vTagMapping = useMemo(() => {
    const imageTags = refImageSlots.map((slot, idx) => ({
      id: slot.id,
      tag: `<Picture ${idx + 1}>`,
      filled: Boolean(slot.fileRef.trim()),
    }));
    const videoTags = refVideoSlots.map((slot, idx) => ({
      id: slot.id,
      videoTag: `<Video ${idx + 1}>`,
      audioTag: null as string | null,
      filled: Boolean(slot.fileRef.trim()),
    }));
    let audioCursor = 1;
    for (let i = 0; i < refVideoSlots.length; i += 1) {
      if (refVideoSlots[i].useVideoAudio) {
        videoTags[i].audioTag = `<Audio ${audioCursor}>`;
        audioCursor += 1;
      }
    }
    const standaloneAudioTags = refAudioSlots.map((slot) => {
      const tag = `<Audio ${audioCursor}>`;
      audioCursor += 1;
      return {
        id: slot.id,
        tag,
        filled: Boolean(slot.fileRef.trim()),
      };
    });

    const allPromptChips: Array<{ key: string; tag: string; hint: string }> = [
      ...imageTags.map((it, idx) => ({
        key: `pic-${it.id}`,
        tag: it.tag,
        hint: `参考图 ${idx + 1}`,
      })),
      ...videoTags.map((vt, idx) => ({
        key: `vid-${vt.id}`,
        tag: vt.videoTag,
        hint: `参考视频 ${idx + 1}`,
      })),
      ...videoTags
        .filter((vt) => Boolean(vt.audioTag))
        .map((vt, idx) => ({
          key: `vidaud-${vt.id}`,
          tag: vt.audioTag as string,
          hint: `视频原声 ${idx + 1}`,
        })),
      ...standaloneAudioTags.map((at, idx) => ({
        key: `aud-${at.id}`,
        tag: at.tag,
        hint: `参考音频 ${idx + 1}`,
      })),
    ];

    return { imageTags, videoTags, standaloneAudioTags, allPromptChips };
  }, [refAudioSlots, refImageSlots, refVideoSlots]);

  const uploadedImgCount = useMemo(
    () => refImageSlots.filter((s) => Boolean(s.fileRef.trim())).length,
    [refImageSlots]
  );
  const uploadedVidCount = useMemo(
    () => refVideoSlots.filter((s) => Boolean(s.fileRef.trim())).length,
    [refVideoSlots]
  );
  const uploadedAudCount = useMemo(
    () => refAudioSlots.filter((s) => Boolean(s.fileRef.trim())).length,
    [refAudioSlots]
  );
  const referenceSlotCount = refImageSlots.length + refVideoSlots.length + refAudioSlots.length;

  const alignedFrames = useMemo(
    () =>
      params.frame_count !== null
        ? alignH3Frames(params.frame_count)
        : durationToH3Frames(params.duration_sec),
    [params.duration_sec, params.frame_count]
  );
  const actualDurationSec = useMemo(
    () => (alignedFrames / Math.max(1, params.fps)).toFixed(2),
    [alignedFrames, params.fps]
  );

  const buildCleanedPayload = useCallback((): MiniMaxStudioRequest => {
    const cleanRefImages =
      params.mode === "r2v"
        ? refImageSlots.map((s) => s.fileRef.trim()).filter(Boolean)
        : [];
    const cleanRefVideos =
      params.mode === "r2v"
        ? refVideoSlots
            .filter((s) => Boolean(s.fileRef.trim()))
            .map((s) => ({
              file_id: s.fileRef.trim(),
              use_video_audio: s.useVideoAudio,
            }))
        : [];
    const cleanRefAudios =
      params.mode === "r2v"
        ? refAudioSlots.map((s) => s.fileRef.trim()).filter(Boolean)
        : [];

    return buildVideoStudioRequest({
      ...params,
      first_frame: params.mode === "fl2v" ? (params.first_frame || "").trim() || null : null,
      last_frame: params.mode === "fl2v" ? (params.last_frame || "").trim() || null : null,
      guide_audio: params.mode !== "r2v" ? (params.guide_audio || "").trim() || null : null,
      guide_image: params.mode !== "r2v" ? (params.guide_image || "").trim() || null : null,
      ref_images: cleanRefImages,
      ref_videos: cleanRefVideos,
      ref_audios: cleanRefAudios,
      width: snap32(params.width),
      height: snap32(params.height),
    });
  }, [params, refAudioSlots, refImageSlots, refVideoSlots]);

  const handleGenerate = useCallback(async () => {
    if (isBusy) return;
    if (!params.prompt.trim()) {
      message.warning("请先输入视频画面与声音描述 (Prompt)。");
      return;
    }
    if (params.mode === "fl2v") {
      if (!(params.first_frame || "").trim() && !(params.last_frame || "").trim()) {
        message.warning("首尾帧图生视频模式请至少上传「首帧图片」（或尾帧图片）。");
        return;
      }
    } else if (params.mode === "r2v") {
      if (uploadedImgCount + uploadedVidCount + uploadedAudCount > H3_REFERENCE_LIMITS.total) {
        message.warning("参考图片、视频与独立音频合计最多 12 个文件；视频自带原声不另计。");
        return;
      }
      if (uploadedImgCount + uploadedVidCount + uploadedAudCount < 1) {
        message.warning("多模态参考生视频模式请至少上传 1 项参考素材（图片 / 视频 / 音频）。");
        return;
      }
      // Guard against non-trailing empty slots shifting <Picture>/<Video>/<Audio> ordinals
      const firstEmptyImg = refImageSlots.findIndex((s) => !s.fileRef.trim());
      if (
        firstEmptyImg >= 0 &&
        refImageSlots.slice(firstEmptyImg + 1).some((s) => Boolean(s.fileRef.trim()))
      ) {
        message.warning(
          `参考图 ${firstEmptyImg + 1} 尚未上传文件，请上传或点击卡片右上角「删除」移除空槽位，避免 <Picture> 编号错位。`
        );
        return;
      }
      const emptyVidIdx = refVideoSlots.findIndex((s) => !s.fileRef.trim());
      if (emptyVidIdx >= 0) {
        message.warning(
          `参考视频 ${emptyVidIdx + 1} 尚未上传文件，请上传或点击卡片右上角「删除」移除空卡片。`
        );
        return;
      }
      const emptyAudIdx = refAudioSlots.findIndex((s) => !s.fileRef.trim());
      if (emptyAudIdx >= 0) {
        message.warning(
          `参考音频 ${emptyAudIdx + 1} 尚未上传文件，请上传或点击卡片右上角「删除」移除空卡片。`
        );
        return;
      }
    }
    await runTask(buildCleanedPayload());
  }, [
    buildCleanedPayload,
    isBusy,
    message,
    params.first_frame,
    params.last_frame,
    params.mode,
    params.prompt,
    refAudioSlots,
    refImageSlots,
    refVideoSlots,
    runTask,
    uploadedAudCount,
    uploadedImgCount,
    uploadedVidCount,
  ]);

  const displayedEntry = useMemo(() => {
    if (selectedTakeId) {
      const fromHist = historyItems.find((h) => h.id === selectedTakeId);
      if (fromHist) return fromHist;
    }
    if (activeTask?.status === "succeeded" && activeTask.result) {
      return {
        id: activeTask.task_id,
        feature: "minimax-h3",
        createdAt: activeTask.finished_at || activeTask.created_at,
        elapsedSec: activeTask.elapsed_sec,
        params: { ...DEFAULT_MINIMAX_H3_PARAMS, ...activeTask.params },
        result: activeTask.result,
      };
    }
    return historyItems[0] || null;
  }, [activeTask, historyItems, selectedTakeId]);

  const stageVideoUrl = useMemo(() => {
    if (!displayedEntry?.result?.video_url) return "";
    return resolveApiUrl(displayedEntry.result.video_url, true);
  }, [displayedEntry]);

  const stageDownloadUrl = useMemo(() => {
    if (!displayedEntry?.result?.video_url) return "";
    const raw = displayedEntry.result.video_url;
    const withDl = raw.includes("?") ? `${raw}&download=true` : `${raw}?download=true`;
    return resolveApiUrl(withDl, true);
  }, [displayedEntry]);

  const stageRefImageUrl = useMemo(() => {
    if (!displayedEntry?.result?.primary_ref_image_url) return "";
    return resolveApiUrl(displayedEntry.result.primary_ref_image_url, true);
  }, [displayedEntry]);

  const sampleRequestBody = useMemo(
    () => buildCleanedPayload() as unknown as Record<string, unknown>,
    [buildCleanedPayload]
  );

  const negPromptNeedsCfgHint = Boolean(params.negative_prompt.trim()) && params.cfg <= 1.01;
  const megapixels = ((snap32(params.width) * snap32(params.height)) / (1024 * 1024)).toFixed(2);
  const canFollowRefAspect = params.mode !== "t2v";

  const leftPane = (
    <>
      {/* 1. Unified Creation Mode + Multimodal Reference Slots + Prompt */}
      <Card
        className="studio-card"
        title={
          <Space size={10} wrap>
            <Segmented
              value={params.mode}
              onChange={(val) => handleModeSwitch(val as H3Mode)}
              options={[
                { label: "文生视频", value: "t2v" },
                { label: "首尾帧图生视频", value: "fl2v" },
                { label: "多模态参考生视频", value: "r2v" },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12.5, fontWeight: 400 }}>
              {params.mode === "t2v"
                ? "直接用文字描述画面镜头与对白音效，同步生成音画视频"
                : params.mode === "fl2v"
                  ? "上传首帧起始图（可选添加尾帧结束图），精准控制运镜与首尾过渡"
                  : "自由组合参考图、参考视频与参考音频，通过 <Picture> / <Video> / <Audio> 编排"}
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
          {/* Mode B: First-Last Frame Slots */}
          {params.mode === "fl2v" && (
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
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <Text strong style={{ fontSize: 13 }}>
                  首尾关键帧画面（仅上传首帧即为标准单图生视频，同时上传尾帧则做首尾过渡）
                </Text>
              </div>

              <div className="studio-image-slot-grid">
                <ImageSourceField
                  label="首帧图片（起始画面）"
                  badgeText="Frame 0"
                  value={params.first_frame || ""}
                  allowClear={Boolean(params.first_frame)}
                  onDimensionsChange={handleFl2vPrimaryDimsDetected}
                  onChange={(nextRef) => updateParam("first_frame", nextRef || null)}
                />
                <ImageSourceField
                  label="尾帧图片（可选 · 结束画面）"
                  badgeText="End Frame"
                  value={params.last_frame || ""}
                  allowClear={Boolean(params.last_frame)}
                  onChange={(nextRef) => updateParam("last_frame", nextRef || null)}
                />
              </div>
            </div>
          )}

          {/* Mode C: Multimodal Reference Slots (Single Top-Right Add Bar, Unified Card Grid) */}
          {params.mode === "r2v" && (
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
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "6px 10px",
                  minBlockSize: 28,
                }}
              >
                <Text strong style={{ fontSize: 13 }}>
                  参考素材（已上传{" "}
                  <span className="studio-tabular">
                    {uploadedImgCount + uploadedVidCount + uploadedAudCount}
                  </span>{" "}
                  / {H3_REFERENCE_LIMITS.total} 个文件）
                </Text>

                <Space size={6} wrap>
                  {refImageSlots.length < H3_REFERENCE_LIMITS.images && (
                    <Button
                      htmlType="button"
                      size="small"
                      type="dashed"
                      icon={<PlusOutlined />}
                      disabled={referenceSlotCount >= H3_REFERENCE_LIMITS.total}
                      onClick={() =>
                        setRefImageSlots((prev) => [...prev, { id: nextId("img"), fileRef: "" }])
                      }
                    >
                      添加参考图
                    </Button>
                  )}
                  {refVideoSlots.length < H3_REFERENCE_LIMITS.videos && (
                    <Button
                      htmlType="button"
                      size="small"
                      type="dashed"
                      icon={<VideoCameraOutlined />}
                      disabled={referenceSlotCount >= H3_REFERENCE_LIMITS.total}
                      onClick={() =>
                        setRefVideoSlots((prev) => [
                          ...prev,
                          { id: nextId("vid"), fileRef: "", useVideoAudio: true },
                        ])
                      }
                    >
                      添加参考视频
                    </Button>
                  )}
                  {refAudioSlots.length < H3_REFERENCE_LIMITS.audios && (
                    <Button
                      htmlType="button"
                      size="small"
                      type="dashed"
                      icon={<AudioOutlined />}
                      disabled={referenceSlotCount >= H3_REFERENCE_LIMITS.total}
                      onClick={() =>
                        setRefAudioSlots((prev) => [...prev, { id: nextId("aud"), fileRef: "" }])
                      }
                    >
                      添加参考音频
                    </Button>
                  )}
                </Space>
              </div>

              <Text type="secondary" style={{ fontSize: 12 }}>
                最多 9 张图片、3 段视频、3 段独立音频，合计不超过 12 个文件；视频原声不另计。
                已添加 {referenceSlotCount} 个素材槽位（含待上传），移除空槽位后可继续添加其他类型。
              </Text>

              <div
                className="studio-image-slot-grid"
                data-single={
                  refImageSlots.length + refVideoSlots.length + refAudioSlots.length <= 1
                    ? "true"
                    : "false"
                }
              >
                {refImageSlots.map((slot, idx) => {
                  const canDeleteImg =
                    refImageSlots.length > 1 ||
                    refVideoSlots.length > 0 ||
                    refAudioSlots.length > 0;
                  return (
                    <ImageSourceField
                      key={slot.id}
                      label={`参考图 ${idx + 1}`}
                      badgeText={`<Picture ${idx + 1}>`}
                      value={slot.fileRef}
                      allowClear={Boolean(slot.fileRef)}
                      onDimensionsChange={idx === 0 ? handleR2vPrimaryDimsDetected : undefined}
                      onRemoveSlot={
                        canDeleteImg
                          ? () => {
                              setRefImageSlots((prev) =>
                                prev.filter((item) => item.id !== slot.id)
                              );
                            }
                          : undefined
                      }
                      onChange={(nextRef) => {
                        setRefImageSlots((prev) =>
                          prev.map((item) =>
                            item.id === slot.id ? { ...item, fileRef: nextRef } : item
                          )
                        );
                      }}
                    />
                  );
                })}

                {refVideoSlots.map((slot, idx) => {
                  const vTag = r2vTagMapping.videoTags[idx];
                  return (
                    <VideoSlotCard
                      key={slot.id}
                      label={`参考视频 ${idx + 1}`}
                      videoBadgeText={vTag?.videoTag || `<Video ${idx + 1}>`}
                      audioBadgeText={vTag?.audioTag || null}
                      value={slot.fileRef}
                      useVideoAudio={slot.useVideoAudio}
                      onUseVideoAudioChange={(checked) => {
                        setRefVideoSlots((prev) =>
                          prev.map((item) =>
                            item.id === slot.id ? { ...item, useVideoAudio: checked } : item
                          )
                        );
                      }}
                      onRemoveSlot={() => {
                        setRefVideoSlots((prev) => prev.filter((item) => item.id !== slot.id));
                      }}
                      onChange={(nextRef) => {
                        setRefVideoSlots((prev) =>
                          prev.map((item) =>
                            item.id === slot.id ? { ...item, fileRef: nextRef } : item
                          )
                        );
                      }}
                    />
                  );
                })}

                {refAudioSlots.map((slot, idx) => {
                  const aTag = r2vTagMapping.standaloneAudioTags[idx];
                  return (
                    <AudioSlotCard
                      key={slot.id}
                      label={`参考音频 ${idx + 1}`}
                      badgeText={aTag?.tag || `<Audio ${idx + 1}>`}
                      value={slot.fileRef}
                      onRemoveSlot={() => {
                        setRefAudioSlots((prev) => prev.filter((item) => item.id !== slot.id));
                      }}
                      onChange={(nextRef) => {
                        setRefAudioSlots((prev) =>
                          prev.map((item) =>
                            item.id === slot.id ? { ...item, fileRef: nextRef } : item
                          )
                        );
                      }}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* Prompt Input + Single Clean Tag Insertion Row */}
          <div className="studio-field-group">
            <div className="studio-field-label">
              <label htmlFor={promptInputId}>音画场景与动作提示词 (Prompt)</label>
              <Space size={8} wrap>
                {params.mode === "r2v" && r2vTagMapping.allPromptChips.length > 0 && (
                  <Space size={4} wrap>
                    <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                      点击插入引用：
                    </Text>
                    {r2vTagMapping.allPromptChips.map((chip) => (
                      <Tooltip key={chip.key} title={`在光标处插入 ${chip.hint} 标签`}>
                        <button
                          type="button"
                          className="studio-token-chip"
                          onClick={() => insertTokenAtCursor(chip.tag)}
                        >
                          {chip.tag}
                        </button>
                      </Tooltip>
                    ))}
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
              onValueChange={(value) => updateParam("prompt", value)}
              onKeyDown={(e) => {
                if (
                  (e.metaKey || e.ctrlKey) &&
                  e.key === "Enter" &&
                  !e.nativeEvent.isComposing &&
                  e.keyCode !== 229
                ) {
                  e.preventDefault();
                  void handleGenerate();
                }
              }}
              placeholder={
                params.mode === "r2v"
                  ? "描述参考主体的互动与声音，例如：让 <Picture 1> 中的主角在雨夜街道奔跑，镜头跟随 <Video 1> 的运镜节奏，并用 <Audio 1> 的音色说出对白..."
                  : params.mode === "fl2v"
                    ? "描述从首帧画面开始的人物动作、镜头推进方式以及伴随的环境音效或人物台词..."
                    : "描述画面主体、运镜轨迹、光影氛围，以及伴随的对白台词、环境音效或背景配乐..."
              }
            />

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 12,
                color: "var(--studio-text-muted)",
              }}
            >
              <span>
                快捷键 <code>⌘/Ctrl + Enter</code> 直接生成 · 可直接在提示词中写台词与音效描述
              </span>
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
                onValueChange={(value) => updateParam("negative_prompt", value)}
                placeholder="排除不需要的画面或杂音，例如：画面闪烁、肢体畸变、低画质、电流底噪..."
              />
              {negPromptNeedsCfgHint && (
                <Alert
                  type="warning"
                  showIcon
                  message={
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 8,
                      }}
                    >
                      <span>
                        当前 CFG 为 <strong>1.0</strong>（单路高速模式），反向提示词不会生效；调至{" "}
                        <strong>2.5 ~ 3.5</strong> 可启用双路负向抑制。
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

      {/* 2. Independent Resolution, Aspect Ratio, Dimensions & Duration / Audio Track */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <VideoCameraOutlined style={{ color: "var(--studio-accent)" }} />
            <span>分辨率、宽高比与时长</span>
          </Space>
        }
        extra={
          <span
            className="studio-tabular"
            style={{ fontSize: 12.5, color: "var(--studio-text-secondary)", fontWeight: 600 }}
          >
            {snap32(params.width)}×{snap32(params.height)} · {alignedFrames} 帧（{actualDurationSec}s）
          </span>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.95rem" }}>
          {/* Row 1: Independent Resolution Tier + Soundtrack Switch */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              alignItems: "flex-end",
              justifyContent: "space-between",
              gap: "0.75rem 1.25rem",
            }}
          >
            <div className="studio-field-group" style={{ flex: "1 1 300px" }}>
              <FieldLabel
                label="分辨率档位 (Resolution)"
                tooltip="当前接入 H3-Base，原生档位为 768p（如 1344×768）；540p 为低分辨率试跑。自定义宽高仅改变推理画布，未接入高分辨率再生成或超分流程。"
              />
              <Segmented
                block
                value={params.resolution_tier === "custom" ? "768p" : params.resolution_tier}
                onChange={(val) => handleResolutionChange(val as H3ResolutionTier)}
                options={[
                  { label: "540p 低清试跑", value: "540p" },
                  { label: "768p 原生标准", value: "768p" },
                ]}
              />
            </div>

            <div className="studio-field-group" style={{ flex: "0 1 250px" }}>
              <FieldLabel
                label="音轨合成 (Audio Track)"
                tooltip="开启后通过 Audio VAE 同步解码 32kHz 立体声对白、环境音效与音乐并封装入视频"
              />
              <Segmented
                block
                value={params.soundtrack_enabled ? "on" : "off"}
                onChange={(val) => {
                  const enabled = val === "on";
                  if (enabled && params.fps !== NATIVE_FPS) {
                    message.info("已恢复 24 fps，保持画面与生成音轨同步。");
                  }
                  setParams((prev) => ({ ...prev, soundtrack_enabled: enabled, fps: enabled ? NATIVE_FPS : prev.fps }));
                }}
                options={[
                  {
                    label: (
                      <span>
                        <SoundOutlined style={{ marginInlineEnd: 4 }} />
                        音画同生
                      </span>
                    ),
                    value: "on",
                  },
                  { label: "纯画面静音", value: "off" },
                ]}
              />
            </div>
          </div>

          {/* Row 2: Independent Aspect Ratio Selector */}
          <div className="studio-field-group">
            <FieldLabel
              label="宽高比 (Aspect Ratio)"
              tooltip="点选比例会自动按当前分辨率档位计算 32px 对齐像素尺寸；也可在下方自由输入宽高"
            />
            <div className="studio-aspect-grid">
              {canFollowRefAspect && (
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
                  <span style={{ fontSize: 12, fontWeight: 600 }}>跟随参考图</span>
                  <span style={{ fontSize: 10.5, opacity: 0.75 }}>
                    {activePrimaryDims
                      ? `${activePrimaryDims.w}:${activePrimaryDims.h}`
                      : "保持原比例"}
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
                    <span style={{ fontSize: 10.5, opacity: 0.75 }}>{opt.sub}</span>
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
                <span style={{ fontSize: 12, fontWeight: 600 }}>自定义</span>
                <span style={{ fontSize: 10.5, opacity: 0.75 }}>自由宽高</span>
              </ChoiceButton>
            </div>
          </div>

          {/* Row 3: Editable Width x Height + FPS */}
          <div className="studio-dim-bar">
            <div className="studio-dimension-fields">
              <div className="studio-field-group">
                <label
                  htmlFor={widthInputId}
                  style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)" }}
                >
                  宽度 W (px)
                </label>
                <InputNumber
                  id={widthInputId}
                  style={{ inlineSize: "100%" }}
                  min={256}
                  max={2560}
                  step={32}
                  value={params.width}
                  onChange={(v) => {
                    const nextW = Number(v || 1344);
                    setParams((prev) => ({
                      ...prev,
                      aspect_ratio: "custom",
                      width: nextW,
                    }));
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

              <div className="studio-field-group">
                <label
                  htmlFor={heightInputId}
                  style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)" }}
                >
                  高度 H (px)
                </label>
                <InputNumber
                  id={heightInputId}
                  style={{ inlineSize: "100%" }}
                  min={256}
                  max={2560}
                  step={32}
                  value={params.height}
                  onChange={(v) => {
                    const nextH = Number(v || 768);
                    setParams((prev) => ({
                      ...prev,
                      aspect_ratio: "custom",
                      height: nextH,
                    }));
                  }}
                  onBlur={() => updateParam("height", snap32(params.height))}
                />
              </div>

              <div className="studio-field-group">
                <label
                  htmlFor={fpsInputId}
                  style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)" }}
                >
                  帧率 (FPS)
                </label>
                <InputNumber
                  id={fpsInputId}
                  style={{ inlineSize: "100%" }}
                  min={12}
                  max={60}
                  step={1}
                  value={params.fps}
                  disabled={params.soundtrack_enabled}
                  onChange={(v) => updateParam("fps", Math.max(12, Math.min(60, Number(v || 24))))}
                />
              </div>
            </div>

            <Text
              type="secondary"
              className="studio-tabular"
              style={{ fontSize: 12, paddingBlockEnd: 6 }}
            >
              {snap32(params.width)} × {snap32(params.height)} px（{megapixels} MP · 32px 对齐）
              {params.soundtrack_enabled
                ? " · 音画同生固定 24 fps"
                : " · 调整帧率会改变播放速度与成片时长，不进行插帧"}
            </Text>
          </div>

          <Text type="secondary" style={{ fontSize: 12 }}>
            H3-Base 原生为 768p。手动宽高属于实验性画布尺寸，不执行高分辨率再生成或超分。
          </Text>

          {/* Row 4: Video Duration Presets + Slider + 17k+5 Frame Grid Readout */}
          <div
            style={{
              padding: "0.7rem 0.85rem",
              borderRadius: "0.65rem",
              background: "var(--studio-surface-subtle)",
              border: "1px solid var(--studio-border)",
              display: "flex",
              flexDirection: "column",
              gap: "0.55rem",
            }}
          >
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "6px 12px",
              }}
            >
              <Space size={8} wrap>
                <FieldLabel
                  label="视频时长 (Duration)"
                  tooltip={`MiniMax-H3 时间潜空间按 17k+5 帧网格对齐（原生 ${NATIVE_FPS}fps 甜点为 5~15 秒，即 124~362 帧）`}
                />
                <Space size={4} wrap>
                  {DURATION_PRESETS.map((preset) => {
                    const isCurrent =
                      params.frame_count === null &&
                      Math.abs(params.duration_sec - preset.sec) < 0.05;
                    return (
                      <button
                        key={preset.sec}
                        type="button"
                        className="studio-recipe-pill"
                        data-active={isCurrent ? "true" : "false"}
                        onClick={() =>
                          setParams((prev) => ({
                            ...prev,
                            duration_sec: preset.sec,
                            frame_count: null,
                          }))
                        }
                      >
                        {preset.label}
                      </button>
                    );
                  })}
                </Space>
              </Space>

              <Space size={8} className="studio-tabular">
                <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                  实际对齐：{alignedFrames} 帧 ≈ {actualDurationSec} 秒
                </Tag>
              </Space>
            </div>

            <Slider aria-label="视频时长" min={1} max={15} step={0.5} value={params.duration_sec}
              onChange={(value) => setParams((previous) => ({ ...previous, duration_sec: value, frame_count: null }))} />
          </div>
        </div>
      </Card>

      <Card className="studio-card" title="生成设置" extra={<Space size={10}><span>极速模式</span><Switch checked={params.turbo_enabled} onChange={handleToggleTurbo} aria-label="极速模式" /></Space>}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="studio-settings-grid">
            <div className="studio-field-group">
              <div className="studio-field-label"><span>步数</span><span className="studio-tabular">{params.steps} 步</span></div>
              <Slider aria-label="生成步数" min={2} max={50} step={1} value={params.steps} onChange={(value) => updateParam("steps", value)} />
            </div>
            <div className="studio-field-group">
              <div className="studio-field-label"><span>引导强度（CFG）</span><span className="studio-tabular">{params.cfg.toFixed(1)}</span></div>
              <Slider aria-label="引导强度" min={1} max={8} step={0.1} value={params.cfg} onChange={(value) => updateParam("cfg", value)} />
            </div>
            <SeedControl value={params.seed}
              onChange={(value) => updateParam("seed", value)} onLockedChange={setSeedLocked} />
          </div>
        </div>
      </Card>

      <details className="studio-native-details">
        <summary>风格模型（LoRA，可选）</summary>
        <div className="studio-details-body"><LoraManagerPanel
          slots={params.loras}
          maxSlots={4}
          excludeIds={["fl2v_turbo_8step", "ref2v_turbo_4step"]}
          onChange={(nextSlots) => updateParam("loras", nextSlots)}
        /></div>
      </details>

      <GenerateDock format={params.output_format}
        formats={[{ label: "MP4", value: "mp4" }, { label: "WebM", value: "webm" }, { label: "MKV", value: "mkv" }]}
        onFormatChange={(value) => { const format = value as VideoOutputFormat; setParams((previous) => ({ ...previous,
          output_format: format, video_codec: format === "webm" && previous.video_codec === "h264" ? "av1" : previous.video_codec })); }}
        busy={isBusy} queued={activeTask?.status === "queued"} onCancel={() => void cancelActive()} onGenerate={() => void handleGenerate()} />
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
                    : "正在渲染音画视频"}
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
              {activeTask.stage || "正在初始化扩散管线..."}
            </Text>
          </div>
        </Card>
      )}

      {/* Primary Video Preview & A/B Reference Stage */}
      <Card
        className="studio-card"
        title={
          <Space size={8}>
            <VideoCameraOutlined style={{ color: "var(--studio-accent)" }} />
            <span>音画成片预览</span>
          </Space>
        }
        extra={
          <Space size={6}>
            {displayedEntry?.result && stageRefImageUrl && (
              <Segmented
                size="small"
                value={stageViewMode}
                onChange={(val) => setStageViewMode(val as "video" | "reference")}
                options={[
                  { label: "成片视频", value: "video" },
                  { label: "原参考图", value: "reference" },
                ]}
              />
            )}
            {displayedEntry?.result?.mock ? (
              <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                本地 Mock 预览
              </Tag>
            ) : displayedEntry?.result ? (
              <Tag color="success" style={{ marginInlineEnd: 0 }}>
                GPU 渲染
              </Tag>
            ) : null}
          </Space>
        }
      >
        {!displayedEntry || !stageVideoUrl ? (
          <div
            style={{
              padding: "3rem 1.5rem",
              textAlign: "center",
              borderRadius: "0.7rem",
              background: "var(--studio-surface-subtle)",
              border: "1px dashed var(--studio-border-strong)",
            }}
          >
            <VideoCameraOutlined style={{ fontSize: 36, color: "var(--m3e-color-outline)", marginBlockEnd: 10 }} />
            <div
              style={{
                fontWeight: 600,
                fontSize: 14.5,
                color: "var(--studio-text)",
                marginBlockEnd: 4,
              }}
            >
              等待视频生成
            </div>
            <Text type="secondary" style={{ fontSize: 12.5 }}>
              选择模式、画幅比例与时长后，点击生成或按 <code>⌘/Ctrl + Enter</code>。成片支持在线音画同步播放、原参考图一键切换对比与下载。
            </Text>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
            <div
              className="studio-video-stage"
              style={{
                aspectRatio: `${displayedEntry.result.width} / ${displayedEntry.result.height}`,
                maxBlockSize: 540,
              }}
            >
              {stageViewMode === "reference" && stageRefImageUrl ? (
                <img
                  src={stageRefImageUrl}
                  alt="原始参考画面"
                  width={displayedEntry.result.width}
                  height={displayedEntry.result.height}
                  style={{
                    inlineSize: "100%",
                    blockSize: "100%",
                    objectFit: "contain",
                    background: "var(--m3e-color-on-surface)",
                  }}
                />
              ) : (
                <video
                  key={stageVideoUrl}
                  className="studio-video-player"
                  controls
                  playsInline
                  preload="metadata"
                  width={displayedEntry.result.width}
                  height={displayedEntry.result.height}
                  src={stageVideoUrl}
                />
              )}
            </div>

            {/* Action Bar under Player */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
              }}
            >
              <Space wrap size={8}>
                <Button
                  htmlType="button"
                  size="small"
                  type="primary"
                  ghost
                  icon={<DownloadOutlined />}
                  href={stageDownloadUrl}
                  download={displayedEntry.result.filename}
                >
                  下载 {displayedEntry.result.format.toUpperCase()}（
                  {(displayedEntry.result.size_bytes / (1024 * 1024)).toFixed(2)} MB）
                </Button>

                <Button
                  htmlType="button"
                  size="small"
                  icon={<VideoCameraOutlined />}
                  onClick={() => {
                    const outRef = `output:${displayedEntry.result.filename}`;
                    setRefVideoSlots((prev) => [
                      {
                        id: nextId("vid"),
                        fileRef: outRef,
                        useVideoAudio: displayedEntry.result.has_audio,
                      },
                      ...prev.slice(0, 1),
                    ]);
                    handleModeSwitch("r2v");
                    message.success("已将该成片挂载为多模态参考视频 <Video 1>");
                  }}
                >
                  设为参考视频 &lt;Video 1&gt;
                </Button>
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
                使用此种子
              </Button>
            </div>

            {displayedEntry.result.warnings?.map((w, idx) => (
              <Alert key={idx} type="info" showIcon icon={<InfoCircleOutlined />} message={w} />
            ))}

            {/* Metadata Tags */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: "0.4rem",
                padding: "0.6rem 0.75rem",
                borderRadius: "0.6rem",
                background: "var(--studio-surface-subtle)",
                border: "1px solid var(--studio-border)",
              }}
            >
              <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                {displayedEntry.result.model_variant}
              </Tag>
              <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                {displayedEntry.result.width}×{displayedEntry.result.height}
              </Tag>
              <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                {displayedEntry.result.frame_count} 帧 · {displayedEntry.result.duration_sec}s @{" "}
                {displayedEntry.result.fps}fps
              </Tag>
              <Tag
                color={displayedEntry.result.has_audio ? "success" : "default"}
                style={{ marginInlineEnd: 0 }}
              >
                {displayedEntry.result.has_audio ? "32kHz 立体声音轨" : "静音画面"}
              </Tag>
              <Tag className="studio-tabular" style={{ marginInlineEnd: 0 }}>
                {displayedEntry.result.steps} 步 · CFG {displayedEntry.result.cfg}
              </Tag>
              {displayedEntry.result.active_loras?.map((l) => (
                <Tag key={l.filename} color="blue" style={{ marginInlineEnd: 0 }}>
                  {l.builtin_turbo ? `Turbo (${l.strength_model})` : `LoRA: ${l.label} (${l.strength_model})`}
                </Tag>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Session Video History List */}
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
              title="清空本地会话视频记录？"
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
            当前会话生成的音画视频会自动记录在此，点击可切换播放或一键回填全部参数。
          </Text>
        ) : (
          <div className="studio-scroll-panel">
            <div className="studio-video-history-list">
              {historyItems.map((item) => {
                const isSelected = displayedEntry?.id === item.id;
                const videoSrc = resolveApiUrl(item.result.video_url, true);
                const promptTitle = item.params.prompt || "MiniMax-H3 音画视频";
                return (
                  <div
                    key={item.id}
                    className="studio-video-history-card"
                    data-active={isSelected ? "true" : "false"}
                    onClick={() => {
                      setSelectedTakeId(item.id);
                      setStageViewMode("video");
                    }}
                  >
                    <video
                      src={videoSrc}
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
                      onClick={(e) => e.stopPropagation()}
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
                      <div
                        style={{
                          fontSize: 12.5,
                          fontWeight: 600,
                          color: "var(--studio-text)",
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {promptTitle}
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
                          {item.result.width}×{item.result.height} · {item.result.duration_sec}s
                          {item.result.turbo_enabled ? " · Turbo" : ""}
                        </span>

                        <Button
                          htmlType="button"
                          size="small"
                          type="link"
                          style={{ padding: 0, blockSize: "auto", fontSize: 12 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setParams({
                              ...DEFAULT_MINIMAX_H3_PARAMS,
                              ...buildVideoStudioRequest(item.params),
                              seed: item.result.used_seed,
                              fps: item.params.soundtrack_enabled ? NATIVE_FPS : item.params.fps,
                            });
                            setSeedLocked(true);
                            setShowNegPrompt(Boolean(item.params.negative_prompt));
                            setFl2vPrimaryDims(null);
                            setR2vPrimaryDims(null);
                            setRefImageSlots(
                              item.params.ref_images?.length
                                ? item.params.ref_images.map((ref) => ({
                                    id: nextId("img"),
                                    fileRef: ref,
                                  }))
                                : [{ id: nextId("img"), fileRef: "" }]
                            );
                            setRefVideoSlots(
                              (item.params.ref_videos || []).map((v) => ({
                                id: nextId("vid"),
                                fileRef: v.file_id,
                                useVideoAudio: v.use_video_audio,
                              }))
                            );
                            setRefAudioSlots(
                              (item.params.ref_audios || []).map((a) => ({
                                id: nextId("aud"),
                                fileRef: a,
                              }))
                            );
                            message.info("已恢复常用生成设置");
                          }}
                        >
                          再次使用
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
      brandBadge="H3"
      defaultTitle="MiniMax-H3"
      defaultSubtitle="文生视频 · 首尾帧 · 多模态参考"
      apiEndpointPath="/api/v1/generate"
      mediaKind="video"
      sampleRequestBody={sampleRequestBody}
      leftPane={leftPane}
      rightPane={rightPane}
    />
  );
}
