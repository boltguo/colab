import React, { useEffect, useId, useRef, useState } from "react";
import {
  Button,
  ColumnWidthOutlined,
  DownloadOutlined,
  ExpandOutlined,
  PictureOutlined,
  Segmented,
  Space,
  Tag,
  Text,
} from "../ui/primitives";

import { ImageLightbox, imageDownloadUrl } from "./ImageLightbox";

export interface StageImageEntry {
  url: string;
  filename: string;
  width: number;
  height: number;
  sizeBytes: number;
  format: string;
}

export interface ImageCompareStageProps {
  images: StageImageEntry[];
  referenceUrl?: string;
  referenceLabel?: string;
  resultLabel?: string;
  useAsReferenceLabel?: string;
  onUseAsReference?: (imageEntry: StageImageEntry) => void;
}

export function ImageCompareStage({
  images,
  referenceUrl,
  referenceLabel = "参考原图 <image1>",
  resultLabel = "Qwen-Image 2.1 生成结果",
  useAsReferenceLabel = "设为 <image1> 继续精修",
  onUseAsReference,
}: ImageCompareStageProps) {
  const sliderId = useId();
  const sliderRef = useRef<HTMLInputElement | null>(null);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const [activeIdx, setActiveIdx] = useState(0);
  const [viewMode, setViewMode] = useState<"result" | "split" | "ref">("result");
  const [splitPct, setSplitPct] = useState(50);

  const safeIdx = activeIdx < images.length ? activeIdx : 0;
  const current = images[safeIdx];
  const hasRef = Boolean(referenceUrl);

  useEffect(() => {
    setActiveIdx(0);
    setViewMode(referenceUrl ? "split" : "result");
  }, [images, referenceUrl]);

  // Sync CSS custom properties on the native range slider for cross-browser active track fill
  useEffect(() => {
    const el = sliderRef.current;
    if (!el) return;
    el.style.setProperty("--attr-min", el.min || "0");
    el.style.setProperty("--attr-max", el.max || "100");
    el.style.setProperty("--control-value", String(splitPct));
  }, [splitPct, viewMode]);

  if (!current) {
    return null;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {/* Top Toolbar: View Switcher + Actions */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        {hasRef ? (
          <Segmented
            size="small"
            value={viewMode}
            onChange={(val) => setViewMode(val as "result" | "split" | "ref")}
            options={[
              { label: "生成结果", value: "result" },
              { label: "A/B 卷帘对比", value: "split", icon: <ColumnWidthOutlined /> },
              { label: "仅看参考图", value: "ref" },
            ]}
          />
        ) : (
          <Tag icon={<PictureOutlined />} color="processing" className="studio-tabular" style={{ marginInlineEnd: 0 }}>
            {current.width} × {current.height} · {current.format.toUpperCase()} · {(current.sizeBytes / 1024).toFixed(0)} KB
          </Tag>
        )}

        <Space size={6} wrap>
          {onUseAsReference && (
            <Button
              htmlType="button"
              size="small"
              type="primary"
              ghost
              onClick={() => onUseAsReference(current)}
            >
              {useAsReferenceLabel}
            </Button>
          )}
          <Button
            htmlType="button"
            size="small"
            icon={<ExpandOutlined />}
            onClick={() => setLightboxOpen(true)}
          >
            放大检视细节
          </Button>
          <a href={imageDownloadUrl(current.url)} download={current.filename}>
            <Button htmlType="button" size="small" type="primary" icon={<DownloadOutlined />}>
              下载原图
            </Button>
          </a>
        </Space>
      </div>

      {/* Main Viewport */}
      <div className="studio-compare-viewport">
        {viewMode === "ref" && referenceUrl ? (
          <>
            <img
              src={referenceUrl}
              alt={referenceLabel}
              className="studio-compare-img-full"
            />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              {referenceLabel}
            </span>
          </>
        ) : viewMode === "split" && referenceUrl ? (
          <>
            <img
              src={current.url}
              alt={current.filename}
              className="studio-compare-img-full"
              {...({ fetchpriority: "high" } as Record<string, string>)}
            />
            <div
              className="studio-compare-before-layer"
              style={{ clipPath: `inset(0 ${100 - splitPct}% 0 0)` }}
            >
              <img
                src={referenceUrl}
                alt={referenceLabel}
                className="studio-compare-img-full"
              />
            </div>
            <div
              className="studio-compare-divider"
              style={{ insetInlineStart: `${splitPct}%` }}
            />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              {referenceLabel}
            </span>
            <span className="studio-compare-badge" style={{ insetInlineEnd: "0.75rem" }}>
              {resultLabel}
            </span>
          </>
        ) : (
          <img
            src={current.url}
            alt={current.filename}
            className="studio-compare-img-full"
            style={{ cursor: "zoom-in" }}
            onClick={() => setLightboxOpen(true)}
            {...({ fetchpriority: "high" } as Record<string, string>)}
          />
        )}
      </div>

      {/* Accessible Native Range Slider for Split View */}
      {viewMode === "split" && referenceUrl && (
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <label
            htmlFor={sliderId}
            style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)", whiteSpace: "nowrap" }}
          >
            卷帘对比位置
          </label>
          <input
            ref={sliderRef}
            id={sliderId}
            type="range"
            min="0"
            max="100"
            step="0.5"
            value={splitPct}
            aria-valuetext={`左侧原图占比 ${Math.round(splitPct)}%`}
            className="studio-compare-range"
            onChange={(e) => setSplitPct(Number(e.target.value))}
          />
          <Text className="studio-tabular" type="secondary" style={{ fontSize: 12, minInlineSize: 42, textAlign: "end" }}>
            {Math.round(splitPct)}%
          </Text>
        </div>
      )}

      {/* Batch Output Strip (when batch_size > 1) */}
      {images.length > 1 && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            本批生成 ({images.length} 张)：
          </Text>
          {images.map((item, idx) => (
            <button
              key={item.filename}
              type="button"
              onClick={() => setActiveIdx(idx)}
              style={{
                padding: 2,
                borderRadius: 8,
                border: idx === safeIdx ? "2px solid var(--studio-accent)" : "1px solid var(--studio-border)",
                background: "var(--m3e-color-surface-container-lowest)",
                cursor: "pointer",
              }}
            >
              <img
                src={item.url}
                alt={`批次 #${idx + 1}`}
                style={{ inlineSize: 54, blockSize: 54, objectFit: "contain", borderRadius: 5 }}
              />
            </button>
          ))}
        </div>
      )}

      <ImageLightbox images={[current]} open={lightboxOpen} onClose={() => setLightboxOpen(false)} />
    </div>
  );
}
