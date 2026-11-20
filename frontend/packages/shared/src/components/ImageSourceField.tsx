import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { resolveApiUrl, uploadMediaFile } from "../api/client";
import { useStudioLocale } from "../i18n";
import {
  Button,
  CloudUploadOutlined,
  DeleteOutlined,
  LoadingOutlined,
  PictureOutlined,
  ReloadOutlined,
  Text,
  useStudioFeedback,
} from "../ui/primitives";

export interface ImageSourceFieldProps {
  label: string;
  badgeText?: string;
  value: string;
  onChange: (fileRef: string) => void;
  /** Called when the user clicks "删除" on an optional card slot to remove the entire slot */
  onRemoveSlot?: () => void;
  allowClear?: boolean;
  onDimensionsChange?: (dims: { w: number; h: number } | null) => void;
}

function splitFilename(name: string): { stem: string; ext: string } {
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return { stem: name, ext: "" };
  return { stem: name.slice(0, dot), ext: name.slice(dot) };
}

export function ImageSourceField({
  label,
  badgeText,
  value,
  onChange,
  onRemoveSlot,
  allowClear = true,
  onDimensionsChange,
}: ImageSourceFieldProps) {
  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const uploadingRef = useRef(false);
  const mountedRef = useRef(true);
  const { t } = useStudioLocale();
  const { message } = useStudioFeedback();

  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploadedMeta, setUploadedMeta] = useState<{
    fileId: string;
    name: string;
    url: string;
    sizeBytes: number;
  } | null>(null);
  const [naturalDims, setNaturalDims] = useState<{ w: number; h: number } | null>(null);
  const [previewFailed, setPreviewFailed] = useState(false);

  useLayoutEffect(() => {
    setNaturalDims(null);
    setPreviewFailed(false);
  }, [value]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const handleFileUpload = async (file: File) => {
    if (uploadingRef.current) return;
    if (!/\.(png|jpe?g|webp)$/i.test(file.name)) {
      message.warning(t("Please select a PNG, JPG, or WebP image.", "请选择 PNG、JPG 或 WebP 图片。"));
      return;
    }
    if (!file.size || file.size > 512 * 1024 * 1024) {
      message.warning(t("Image cannot be empty and must be within 512 MB.", "图片不能为空，大小需在 512 MB 以内。"));
      return;
    }
    uploadingRef.current = true;
    setUploading(true);
    try {
      const res = await uploadMediaFile(file);
      if (!mountedRef.current) return;
      setUploadedMeta({
        fileId: res.file_id,
        name: res.filename,
        url: res.url,
        sizeBytes: res.size_bytes,
      });
      setNaturalDims(null);
      onDimensionsChange?.(null);
      onChange(res.file_id);
      message.success(t(`Uploaded: ${res.filename}`, `已上传：${res.filename}`));
    } catch (err) {
      if (mountedRef.current) message.error(err instanceof Error ? err.message : t("Failed to upload image", "上传图像失败"));
    } finally {
      uploadingRef.current = false;
      if (mountedRef.current) setUploading(false);
    }
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLDivElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i += 1) {
      const item = items[i];
      if (item.type.startsWith("image/")) {
        const pasted = item.getAsFile();
        if (pasted) {
          e.preventDefault();
          void handleFileUpload(pasted);
          break;
        }
      }
    }
  };

  const previewUrl = (() => {
    if (!value) return "";
    if (uploadedMeta && uploadedMeta.fileId === value) {
      return resolveApiUrl(uploadedMeta.url, true);
    }
    if (value.startsWith("output:")) {
      return resolveApiUrl(`/api/v1/outputs/${encodeURIComponent(value.slice("output:".length))}`, true);
    }
    return resolveApiUrl(`/api/v1/files/${encodeURIComponent(value)}`, true);
  })();

  const displayFilename = (() => {
    if (!value) return "";
    if (uploadedMeta && uploadedMeta.fileId === value) {
      return uploadedMeta.name;
    }
    if (value.startsWith("output:")) {
      return value.slice("output:".length);
    }
    return value;
  })();

  const { stem, ext } = splitFilename(displayFilename);

  return (
    <div
      className="studio-ref-card"
      data-dragging={dragging ? "true" : "false"}
      onPaste={handlePaste}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const dropped = e.dataTransfer.files?.[0];
        if (dropped) {
          void handleFileUpload(dropped);
        }
      }}
    >
      <input
        ref={fileInputRef}
        id={inputId}
        name="ref_image"
        type="file"
        accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
        className="studio-visually-hidden"
        onChange={(e) => {
          const selected = e.target.files?.[0];
          if (selected) {
            void handleFileUpload(selected);
          }
          e.target.value = "";
        }}
      />

      {/* Single-line aligned card header */}
      <div className="studio-ref-card-header">
        <div style={{ display: "flex", alignItems: "center", gap: 6, minInlineSize: 0 }}>
          <label htmlFor={inputId} className="studio-ref-card-title">
            {label}
          </label>
          {badgeText && <code className="studio-ref-badge">{badgeText}</code>}
        </div>

        {onRemoveSlot ? (
          <Button
            htmlType="button"
            size="small"
            type="text"
            danger
            icon={<DeleteOutlined />}
            aria-label={t(`Remove ${label}`, `删除 ${label}`)}
            style={{ paddingInline: 6, blockSize: 24, fontSize: 12 }}
            onClick={() => {
              setNaturalDims(null);
              onDimensionsChange?.(null);
              onRemoveSlot();
            }}
          >
            {t("Remove", "删除")}
          </Button>
        ) : value && allowClear ? (
          <Button
            htmlType="button"
            size="small"
            type="text"
            danger
            icon={<DeleteOutlined />}
            aria-label={t(`Clear ${label}`, `清空 ${label}`)}
            disabled={uploading}
            style={{ paddingInline: 6, blockSize: 24, fontSize: 12 }}
            onClick={() => {
              setNaturalDims(null);
              onDimensionsChange?.(null);
              onChange("");
            }}
          >
            {t("Clear", "清空")}
          </Button>
        ) : null}
      </div>

      {/* Uniform-height body: populated preview vs clean dropzone */}
      {previewUrl ? (
        <div className="studio-image-preview-box">
          <img
            key={previewUrl}
            src={previewUrl}
            alt={displayFilename || label}
            className="studio-image-thumb"
            onError={() => {
              setPreviewFailed(true);
              setNaturalDims(null);
              onDimensionsChange?.(null);
            }}
            onLoad={(e) => {
              const img = e.currentTarget;
              if (img.naturalWidth && img.naturalHeight) {
                const dims = { w: img.naturalWidth, h: img.naturalHeight };
                setNaturalDims(dims);
                onDimensionsChange?.(dims);
              }
            }}
          />
          <div style={{ flex: "1 1 auto", minInlineSize: 0, display: "flex", flexDirection: "column", gap: 3 }}>
            <Text strong style={{ fontSize: 12.5, display: "block", minInlineSize: 0 }}>
              <PictureOutlined style={{ marginInlineEnd: 5, color: "var(--studio-accent)" }} />
              <span className="studio-filename">
                <span>{stem}</span>
                {ext}
              </span>
            </Text>
            <Text type="secondary" className="studio-tabular" style={{ fontSize: 11.5 }}>
              {previewFailed
                ? t("Image unavailable, please re-upload", "图片已失效，请重新上传")
                : naturalDims
                  ? `${naturalDims.w} × ${naturalDims.h} px`
                  : t("Loading dimensions...", "读取尺寸中...")}
              {uploadedMeta && uploadedMeta.fileId === value
                ? ` · ${(uploadedMeta.sizeBytes / 1024).toFixed(0)} KB`
                : ""}
            </Text>
          </div>
          <Button
            htmlType="button"
            size="small"
            icon={uploading ? <LoadingOutlined /> : <ReloadOutlined />}
            loading={uploading}
            onClick={() => fileInputRef.current?.click()}
          >
            {t("Replace", "更换")}
          </Button>
        </div>
      ) : (
        <button
          type="button"
          className="studio-ref-dropzone"
          disabled={uploading}
          aria-label={t(`Upload image for ${label}`, `点击上传图片 ${label}`)}
          onClick={() => fileInputRef.current?.click()}
        >
          <span className="studio-ref-dropzone-action">
            {uploading ? <LoadingOutlined /> : <CloudUploadOutlined />}
            <span>{t("Click to upload image", "点击上传图片")}</span>
          </span>
          <span className="studio-ref-dropzone-sub">
            {t("Drag & drop or paste with ⌘/Ctrl+V", "支持拖拽或 ⌘/Ctrl+V 粘贴")}
          </span>
        </button>
      )}
    </div>
  );
}
