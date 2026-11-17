import React, { useId, useRef, useState } from "react";
import {
  Button,
  CloudUploadOutlined,
  DeleteOutlined,
  LoadingOutlined,
  ReloadOutlined,
  Text,
  VideoCameraOutlined,
  resolveApiUrl,
  uploadMediaFile,
  useStudioFeedback,
} from "@colab/shared";

function splitFilename(name: string): { stem: string; ext: string } {
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return { stem: name, ext: "" };
  return { stem: name.slice(0, dot), ext: name.slice(dot) };
}

export interface VideoSourceMeta {
  w: number;
  h: number;
  dur: number;
}

export interface VideoInputCardProps {
  label: string;
  badgeText?: string;
  value: string;
  onChange: (fileRef: string) => void;
  onMetadataChange?: (meta: VideoSourceMeta | null) => void;
}

export function VideoInputCard({
  label,
  badgeText,
  value,
  onChange,
  onMetadataChange,
}: VideoInputCardProps) {
  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const { message } = useStudioFeedback();

  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploadedMeta, setUploadedMeta] = useState<{
    fileId: string;
    name: string;
    url: string;
    sizeBytes: number;
  } | null>(null);
  const [videoMeta, setVideoMeta] = useState<VideoSourceMeta | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const uploadInFlight = useRef(false);

  const handleFileUpload = async (file: File) => {
    if (uploadInFlight.current) return;
    if (!/\.(mp4|webm|mov|mkv)$/i.test(file.name)) {
      message.warning("请选择 MP4、WebM、MOV 或 MKV 视频文件。");
      return;
    }
    if (!file.size || file.size > 512 * 1024 * 1024) {
      message.warning(file.size ? "视频超过 512 MB 上传限制，请先截取片段。" : "所选视频为空，请重新选择。");
      return;
    }
    uploadInFlight.current = true;
    setUploading(true);
    try {
      const res = await uploadMediaFile(file);
      setUploadedMeta({
        fileId: res.file_id,
        name: res.filename,
        url: res.url,
        sizeBytes: res.size_bytes,
      });
      setVideoMeta(null);
      setPreviewError(false);
      onMetadataChange?.(null);
      onChange(res.file_id);
      message.success(`已上传待超分视频：${res.filename}`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "上传视频失败");
    } finally {
      uploadInFlight.current = false;
      setUploading(false);
    }
  };

  const previewUrl = (() => {
    if (!value) return "";
    if (uploadedMeta && uploadedMeta.fileId === value) {
      return resolveApiUrl(uploadedMeta.url, true);
    }
    if (value.startsWith("output:")) {
      return resolveApiUrl(
        `/api/v1/outputs/${encodeURIComponent(value.slice("output:".length))}`,
        true
      );
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
        type="file"
        accept=".mp4,.webm,.mov,.mkv,video/mp4,video/webm,video/quicktime"
        className="studio-visually-hidden"
        onChange={(e) => {
          const selected = e.target.files?.[0];
          if (selected) {
            void handleFileUpload(selected);
          }
          e.target.value = "";
        }}
      />

      <div className="studio-ref-card-header">
        <div style={{ display: "flex", alignItems: "center", gap: 6, minInlineSize: 0 }}>
          <label htmlFor={inputId} className="studio-ref-card-title">
            {label}
          </label>
          {badgeText && <code className="studio-ref-badge">{badgeText}</code>}
        </div>

        {value ? (
          <Button
            htmlType="button"
            size="small"
            type="text"
            danger
            disabled={uploading}
            icon={<DeleteOutlined />}
            aria-label={`清空 ${label}`}
            style={{ paddingInline: 6, blockSize: 24, fontSize: 12 }}
            onClick={() => {
              setVideoMeta(null);
              setPreviewError(false);
              onMetadataChange?.(null);
              onChange("");
            }}
          >
            清空
          </Button>
        ) : null}
      </div>

      {previewUrl ? (
        <div className="studio-image-preview-box">
          <video
            src={previewUrl}
            controls
            playsInline
            preload="metadata"
            width={112}
            height={64}
            style={{
              inlineSize: 112,
              blockSize: 64,
              borderRadius: 6,
              objectFit: "cover",
              background: "var(--m3e-color-on-surface)",
              flex: "0 0 auto",
            }}
            onLoadedMetadata={(e) => {
              setPreviewError(false);
              const v = e.currentTarget;
              const nextMeta: VideoSourceMeta = {
                w: v.videoWidth || 0,
                h: v.videoHeight || 0,
                dur: Number.isFinite(v.duration) ? v.duration : 0,
              };
              setVideoMeta(nextMeta);
              if (nextMeta.w > 0 && nextMeta.h > 0) {
                onMetadataChange?.(nextMeta);
              }
            }}
            onError={() => {
              setPreviewError(true);
              setVideoMeta(null);
              onMetadataChange?.(null);
            }}
          />
          <div
            style={{
              flex: "1 1 auto",
              minInlineSize: 0,
              display: "flex",
              flexDirection: "column",
              gap: 3,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 5,
                minInlineSize: 0,
                fontSize: 12.5,
                fontWeight: 600,
              }}
            >
              <VideoCameraOutlined style={{ flexShrink: 0, color: "var(--studio-accent)" }} />
              <span className="studio-filename">
                <span>{stem}</span>
                {ext}
              </span>
            </div>
            <Text type="secondary" className="studio-tabular" style={{ fontSize: 11.5 }}>
              {previewError ? "当前浏览器无法预览，请确认视频可正常播放。" : videoMeta && videoMeta.w > 0
                ? `${videoMeta.w} × ${videoMeta.h} px${videoMeta.dur > 0 ? ` · ${videoMeta.dur.toFixed(1)}s` : ""}`
                : "读取原片信息中..."}
              {uploadedMeta && uploadedMeta.fileId === value
                ? ` · ${(uploadedMeta.sizeBytes / (1024 * 1024)).toFixed(2)} MB`
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
            更换
          </Button>
        </div>
      ) : (
        <button
          type="button"
          disabled={uploading}
          className="studio-ref-dropzone"
          aria-label={`点击上传待超分视频 ${label}`}
          onClick={() => fileInputRef.current?.click()}
        >
          <span className="studio-ref-dropzone-action">
            {uploading ? <LoadingOutlined /> : <CloudUploadOutlined />}
            <span>点击上传待超分视频</span>
          </span>
          <span className="studio-ref-dropzone-sub">
            支持拖拽 MP4 / WebM / MOV / MKV，自动保留原始帧率与音轨
          </span>
        </button>
      )}
    </div>
  );
}
