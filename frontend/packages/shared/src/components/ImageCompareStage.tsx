import React, { useEffect, useId, useState } from "react";
import { useStudioLocale } from "../i18n";
import {
  Button,
  ColumnWidthOutlined,
  DownloadOutlined,
  ExpandOutlined,
  PictureOutlined,
  Segmented,
  Slider,
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
  referenceLabel,
  resultLabel,
  useAsReferenceLabel,
  onUseAsReference,
}: ImageCompareStageProps) {
  const { t } = useStudioLocale();
  const sliderId = useId();
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const resolvedRefLabel = referenceLabel ?? t("Reference <image1>", "参考原图 <image1>");
  const resolvedResLabel = resultLabel ?? t("Qwen-Image 2.1 Result", "Qwen-Image 2.1 生成结果");
  const resolvedUseRefLabel = useAsReferenceLabel ?? t("Use as <image1>", "设为 <image1> 继续精修");

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
              { label: t("Result", "生成结果"), value: "result" },
              { label: t("A/B Split", "A/B 卷帘对比"), value: "split", icon: <ColumnWidthOutlined /> },
              { label: t("Reference", "仅看参考图"), value: "ref" },
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
              {resolvedUseRefLabel}
            </Button>
          )}
          <Button
            htmlType="button"
            size="small"
            icon={<ExpandOutlined />}
            onClick={() => setLightboxOpen(true)}
          >
            {t("Inspect", "放大检视细节")}
          </Button>
          <Button
            htmlType="button"
            size="small"
            type="primary"
            href={imageDownloadUrl(current.url)}
            download={current.filename}
            icon={<DownloadOutlined />}
          >
            {t("Download", "下载原图")}
          </Button>
        </Space>
      </div>

      {/* Main Viewport */}
      <div className="studio-compare-viewport">
        {viewMode === "ref" && referenceUrl ? (
          <>
            <img
              src={referenceUrl}
              alt={resolvedRefLabel}
              className="studio-compare-img-full"
            />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              {resolvedRefLabel}
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
                alt={resolvedRefLabel}
                className="studio-compare-img-full"
              />
            </div>
            <div
              className="studio-compare-divider"
              style={{ insetInlineStart: `${splitPct}%` }}
            />
            <span className="studio-compare-badge" style={{ insetInlineStart: "0.75rem" }}>
              {resolvedRefLabel}
            </span>
            <span className="studio-compare-badge" style={{ insetInlineEnd: "0.75rem" }}>
              {resolvedResLabel}
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

      {/* Split Control */}
      {viewMode === "split" && referenceUrl && (
        <div className="studio-compare-controls">
          <div className="studio-compare-slider-row">
            <label
              htmlFor={sliderId}
              style={{ fontSize: 12, fontWeight: 600, color: "var(--studio-text-secondary)", whiteSpace: "nowrap" }}
            >
              {t("Split Position", "卷帘对比位置")}
            </label>
            <Slider
              id={sliderId}
              aria-label={t("Split Position", "卷帘对比位置")}
              min={0}
              max={100}
              step={0.5}
              value={splitPct}
              onChange={setSplitPct}
              tooltip={{ formatter: (v) => `${Math.round(v ?? 0)}%` }}
            />
            <Text className="studio-tabular" type="secondary" style={{ fontSize: 12, minInlineSize: 42, textAlign: "end" }}>
              {Math.round(splitPct)}%
            </Text>
          </div>
        </div>
      )}

      {/* Batch Output Strip (when batch_size > 1) */}
      {images.length > 1 && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t(`Batch outputs (${images.length}):`, `本批生成 (${images.length} 张)：`)}
          </Text>
          {images.map((item, idx) => (
            <button
              key={item.filename}
              type="button"
              className="studio-batch-thumb-btn"
              data-active={idx === safeIdx ? "true" : undefined}
              onClick={() => setActiveIdx(idx)}
            >
              <img
                src={item.url}
                alt={t(`Batch #${idx + 1}`, `批次 #${idx + 1}`)}
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
