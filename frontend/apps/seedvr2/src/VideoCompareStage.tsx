import React, { useEffect, useId, useRef, useState } from "react";
import {
  Button,
  ColumnWidthOutlined,
  DownloadOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  Segmented,
  Space,
  Text,
  VideoCameraOutlined,
} from "@colab/shared";
import type { SeedVR2Result } from "./types";

export interface VideoCompareStageProps {
  result: SeedVR2Result;
  outputUrl: string;
  downloadUrl: string;
  inputUrl?: string;
  onUseAsInput?: () => void;
}

export function VideoCompareStage({
  result,
  outputUrl,
  downloadUrl,
  inputUrl,
  onUseAsInput,
}: VideoCompareStageProps) {
  const splitSliderId = useId();
  const scrubSliderId = useId();

  const splitSliderRef = useRef<HTMLInputElement | null>(null);
  const scrubSliderRef = useRef<HTMLInputElement | null>(null);
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

  useEffect(() => {
    setViewMode(inputUrl ? "split" : "result");
    setPlaying(false);
    setCurrentTime(0);
    setDuration(result.duration_sec || 0);
  }, [outputUrl, inputUrl, result.duration_sec]);

  // Sync CSS custom properties on the native A/B range slider for cross-browser active track fill
  useEffect(() => {
    const el = splitSliderRef.current;
    if (!el) return;
    el.style.setProperty("--attr-min", el.min || "0");
    el.style.setProperty("--attr-max", el.max || "100");
    el.style.setProperty("--control-value", String(splitPct));
  }, [splitPct, viewMode]);

  useEffect(() => {
    const el = scrubSliderRef.current;
    if (!el) return;
    const safeMax = Math.max(0.1, duration || 1);
    el.style.setProperty("--attr-min", "0");
    el.style.setProperty("--attr-max", String(safeMax));
    el.style.setProperty("--control-value", String(Math.min(currentTime, safeMax)));
  }, [currentTime, duration, viewMode]);

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

    if (beforeV && Math.abs(beforeV.currentTime - afterV.currentTime) > 0.06) {
      beforeV.currentTime = afterV.currentTime;
    }
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
    if (beforeVideoRef.current) {
      beforeVideoRef.current.currentTime = nextSec;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {/* Top Toolbar */}
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
              { label: "超分后成片", value: "result" },
              { label: "A/B 卷帘同屏对比", value: "split", icon: <ColumnWidthOutlined /> },
              { label: "超分前原片", value: "ref" },
            ]}
          />
        ) : (
          <Text strong className="studio-tabular" style={{ fontSize: 12.5 }}>
            {result.width} × {result.height} ({result.format.toUpperCase()})
          </Text>
        )}

        <Space size={6} wrap>
          {onUseAsInput && (
            <Button
              htmlType="button"
              size="small"
              icon={<VideoCameraOutlined />}
              onClick={onUseAsInput}
            >
              设为源视频继续放大
            </Button>
          )}
          <a href={downloadUrl} download={result.filename}>
            <Button htmlType="button" size="small" type="primary" icon={<DownloadOutlined />}>
              下载 {result.format.toUpperCase()}（{(result.size_bytes / (1024 * 1024)).toFixed(2)} MB）
            </Button>
          </a>
        </Space>
      </div>

      {/* Main Video Stage (Eager above-the-fold, explicit integer width & height + aspect-ratio) */}
      <div
        className="studio-video-stage"
        style={{
          aspectRatio: `${result.width} / ${result.height}`,
          maxBlockSize: 540,
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
            />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              超分前原片（{result.input_width}×{result.input_height}）
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
                const t = e.currentTarget.currentTime;
                setCurrentTime(t);
                const beforeV = beforeVideoRef.current;
                if (beforeV && Math.abs(beforeV.currentTime - t) > 0.14) {
                  beforeV.currentTime = t;
                }
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
              style={{ cursor: "pointer" }}
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
              />
            </div>
            <div
              className="studio-compare-divider"
              style={{ insetInlineStart: `${splitPct}%` }}
            />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              原片 {result.input_width}×{result.input_height}
            </span>
            <span className="studio-compare-badge" style={{ insetInlineEnd: "0.75rem" }}>
              SeedVR2 超分 {result.width}×{result.height}
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
          />
        )}
      </div>

      {/* Synchronized Playback + A/B Wipe Controls for Split View */}
      {viewMode === "split" && inputUrl && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            padding: "0.55rem 0.75rem",
            borderRadius: "0.6rem",
            background: "var(--studio-surface-subtle)",
            border: "1px solid var(--studio-border)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Button
              htmlType="button"
              size="small"
              type={playing ? "default" : "primary"}
              icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              onClick={() => void toggleSplitPlay()}
            >
              {playing ? "暂停对比" : "同步播放对比"}
            </Button>
            <Button
              htmlType="button"
              size="small"
              icon={<ReloadOutlined />}
              aria-label="从头重播对比"
              onClick={() => {
                handleScrub(0);
                if (!playing) {
                  void toggleSplitPlay();
                }
              }}
            >
              重播
            </Button>

            <label htmlFor={scrubSliderId} className="studio-visually-hidden">
              对比播放时间轴
            </label>
            <input
              ref={scrubSliderRef}
              id={scrubSliderId}
              type="range"
              min="0"
              max={Math.max(0.1, duration || 1)}
              step="0.02"
              value={Math.min(currentTime, Math.max(0.1, duration || 1))}
              aria-valuetext={`${currentTime.toFixed(1)} 秒`}
              className="studio-compare-range"
              onChange={(e) => handleScrub(Number(e.target.value))}
            />
            <Text
              type="secondary"
              className="studio-tabular"
              style={{ fontSize: 11.5, whiteSpace: "nowrap" }}
            >
              {currentTime.toFixed(1)}s / {(duration || 0).toFixed(1)}s
            </Text>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label
              htmlFor={splitSliderId}
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--studio-text-secondary)",
                whiteSpace: "nowrap",
              }}
            >
              卷帘分界位置
            </label>
            <input
              ref={splitSliderRef}
              id={splitSliderId}
              type="range"
              min="0"
              max="100"
              step="0.5"
              value={splitPct}
              aria-valuetext={`左侧原片占比 ${Math.round(splitPct)}%`}
              className="studio-compare-range"
              onChange={(e) => setSplitPct(Number(e.target.value))}
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
