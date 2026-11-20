import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  Button,
  ColumnWidthOutlined,
  DownloadOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  Segmented,
  Slider,
  Space,
  Text,
  useStudioLocale,
} from "@colab/shared";
import type { H3CharacterSwapResult } from "./types";

export interface VideoCompareStageProps {
  result: H3CharacterSwapResult;
  outputUrl: string;
  downloadUrl: string;
  inputUrl?: string;
}

export function VideoCompareStage({
  result,
  outputUrl,
  downloadUrl,
  inputUrl,
}: VideoCompareStageProps) {
  const { t } = useStudioLocale();
  const splitSliderId = useId();
  const scrubSliderId = useId();

  const afterVideoRef = useRef<HTMLVideoElement | null>(null);
  const beforeVideoRef = useRef<HTMLVideoElement | null>(null);

  const hasInput = Boolean(inputUrl);
  const [viewMode, setViewMode] = useState<"result" | "split" | "ref">(
    hasInput ? "split" : "result"
  );
  const [splitPct, setSplitPct] = useState(50);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(result.duration_sec || 0);
  const referenceStart = Math.max(0, result.input_start_time || 0);
  const referenceRate = result.input_fps && result.fps ? result.fps / result.input_fps : 1;

  const syncReference = useCallback(
    (outputTime: number, force = false) => {
      const before = beforeVideoRef.current;
      if (!before || before.readyState < 1) return;
      const target = Math.min(
        referenceStart + outputTime * referenceRate,
        Number.isFinite(before.duration) ? Math.max(0, before.duration - 0.001) : Infinity
      );
      if (force || Math.abs(before.currentTime - target) > 0.14) before.currentTime = target;
      try {
        before.playbackRate = referenceRate;
      } catch {
        // Browsers may reject extreme playback rates.
      }
    },
    [referenceStart, referenceRate]
  );

  useEffect(() => {
    setViewMode(inputUrl ? "split" : "result");
    setPlaying(false);
    setCurrentTime(0);
    setDuration(result.duration_sec || 0);
  }, [outputUrl, inputUrl, result.duration_sec]);

  const toggleSplitPlay = async () => {
    const afterV = afterVideoRef.current;
    const beforeV = beforeVideoRef.current;
    if (!afterV) return;

    if (!afterV.paused) {
      afterV.pause();
      beforeV?.pause();
      setPlaying(false);
      return;
    }

    syncReference(afterV.currentTime, true);
    try {
      await Promise.all([
        afterV.play(),
        beforeV ? beforeV.play().catch(() => undefined) : Promise.resolve(),
      ]);
      setPlaying(true);
    } catch {
      setPlaying(false);
    }
  };

  const handleScrub = (nextSec: number) => {
    setCurrentTime(nextSec);
    if (afterVideoRef.current) {
      afterVideoRef.current.currentTime = nextSec;
    }
    syncReference(nextSec, true);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
        }}
      >
        {hasInput ? (
          <Segmented
            size="small"
            value={viewMode}
            onChange={(val) => {
              afterVideoRef.current?.pause();
              beforeVideoRef.current?.pause();
              setPlaying(false);
              setViewMode(val as "result" | "split" | "ref");
            }}
            options={[
              { label: t("Swapped Video", "替换成片"), value: "result" },
              { label: t("A/B Split", "A/B 卷帘对比"), value: "split", icon: <ColumnWidthOutlined /> },
              { label: t("Source Video", "原始视频"), value: "ref" },
            ]}
          />
        ) : (
          <Text strong className="studio-tabular" style={{ fontSize: 12.5 }}>
            {result.width} × {result.height} ({result.format.toUpperCase()})
          </Text>
        )}

        <Space size={6} wrap>
          <Button
            size="small"
            type="primary"
            href={downloadUrl}
            download={result.filename}
            icon={<DownloadOutlined />}
          >
            {t("Download", "下载")} {result.format.toUpperCase()} ({(result.size_bytes / (1024 * 1024)).toFixed(2)} MB)
          </Button>
        </Space>
      </div>

      <div
        className="studio-video-stage"
        style={{
          aspectRatio: `${result.width} / ${result.height}`,
          inlineSize: "100%",
          maxInlineSize: (540 * result.width) / result.height,
          marginInline: "auto",
        }}
      >
        {viewMode === "ref" && inputUrl ? (
          <>
            <video
              key={`ref-${inputUrl}`}
              className="studio-video-player"
              controls
              playsInline
              preload="metadata"
              width={result.input_width || result.width}
              height={result.input_height || result.height}
              src={inputUrl}
              onLoadedMetadata={(e) => {
                e.currentTarget.currentTime = referenceStart;
              }}
              style={{ position: "absolute", inset: 0, blockSize: "100%" }}
            />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              {t(`Source (${result.input_width}×${result.input_height})`, `原始视频（${result.input_width}×${result.input_height}）`)}
            </span>
          </>
        ) : viewMode === "split" && inputUrl ? (
          <>
            <video
              key={`split-after-${outputUrl}`}
              ref={afterVideoRef}
              className="studio-video-player"
              playsInline
              preload="metadata"
              width={result.width}
              height={result.height}
              src={outputUrl}
              onClick={() => void toggleSplitPlay()}
              onLoadedMetadata={(e) => {
                const dur = e.currentTarget.duration;
                if (Number.isFinite(dur) && dur > 0) {
                  setDuration(dur);
                }
              }}
              onTimeUpdate={(e) => {
                const tSec = e.currentTarget.currentTime;
                setCurrentTime(tSec);
                syncReference(tSec);
              }}
              onPlay={() => {
                setPlaying(true);
                void beforeVideoRef.current?.play().catch(() => undefined);
              }}
              onPause={() => {
                setPlaying(false);
                beforeVideoRef.current?.pause();
              }}
              onEnded={() => {
                setPlaying(false);
                beforeVideoRef.current?.pause();
              }}
              style={{ position: "absolute", inset: 0, blockSize: "100%", cursor: "pointer" }}
            />
            <div
              className="studio-compare-before-layer"
              style={{ clipPath: `inset(0 ${100 - splitPct}% 0 0)` }}
            >
              <video
                key={`split-before-${inputUrl}`}
                ref={beforeVideoRef}
                className="studio-video-player"
                muted
                playsInline
                preload="metadata"
                aria-hidden="true"
                width={result.width}
                height={result.height}
                src={inputUrl}
                onLoadedMetadata={() => syncReference(afterVideoRef.current?.currentTime || 0, true)}
                style={{ position: "absolute", inset: 0, blockSize: "100%", objectFit: "cover" }}
              />
            </div>
            <div className="studio-compare-divider" style={{ insetInlineStart: `${splitPct}%` }} />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              {t("Source", "原视频")}
            </span>
            <span className="studio-compare-badge" style={{ insetInlineEnd: "0.75rem" }}>
              {t(`Swapped ${result.width}×${result.height}`, `替换后 ${result.width}×${result.height}`)}
            </span>
          </>
        ) : (
          <video
            key={`res-${outputUrl}`}
            className="studio-video-player"
            controls
            playsInline
            preload="metadata"
            width={result.width}
            height={result.height}
            src={outputUrl}
            style={{ position: "absolute", inset: 0, blockSize: "100%" }}
          />
        )}
      </div>

      {viewMode === "split" && inputUrl && (
        <div className="studio-compare-controls">
          <div className="studio-compare-slider-row" style={{ flexWrap: "wrap" }}>
            <Button
              htmlType="button"
              size="small"
              type={playing ? "default" : "primary"}
              icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              onClick={() => void toggleSplitPlay()}
            >
              {playing ? t("Pause", "暂停对比") : t("Sync Play", "同步播放对比")}
            </Button>
            <Button
              htmlType="button"
              size="small"
              icon={<ReloadOutlined />}
              aria-label={t("Replay comparison from start", "从头重播对比")}
              onClick={() => {
                handleScrub(0);
                if (!playing) {
                  void toggleSplitPlay();
                }
              }}
            >
              {t("Replay", "重播")}
            </Button>

            <Slider
              id={scrubSliderId}
              aria-label={t("Comparison timeline", "对比播放时间轴")}
              min={0}
              max={Math.max(0.1, duration || 1)}
              step={0.02}
              value={Math.min(currentTime, Math.max(0.1, duration || 1))}
              onChange={handleScrub}
              tooltip={{ formatter: (v) => `${(v ?? 0).toFixed(1)}s` }}
            />
            <Text type="secondary" className="studio-tabular" style={{ fontSize: 11.5, whiteSpace: "nowrap" }}>
              {currentTime.toFixed(1)}s / {(duration || 0).toFixed(1)}s
            </Text>
          </div>

          <div className="studio-compare-slider-row">
            <label
              htmlFor={splitSliderId}
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--studio-text-secondary)",
                whiteSpace: "nowrap",
              }}
            >
              {t("Split Position", "卷帘分界位置")}
            </label>
            <Slider
              id={splitSliderId}
              aria-label={t("Split Position", "卷帘分界位置")}
              min={0}
              max={100}
              step={0.5}
              value={splitPct}
              onChange={setSplitPct}
              tooltip={{ formatter: (v) => `${Math.round(v ?? 0)}%` }}
            />
            <Text
              className="studio-tabular"
              type="secondary"
              style={{ fontSize: 12, minInlineSize: 40, textAlign: "end" }}
            >
              {Math.round(splitPct)}%
            </Text>
          </div>
        </div>
      )}
    </div>
  );
}
