import React, { useEffect, useId, useRef, useState } from "react";
import {
  AudioOutlined,
  Button,
  CloudUploadOutlined,
  DeleteOutlined,
  LoadingOutlined,
  ReloadOutlined,
  Space,
  StopOutlined,
  Switch,
  Text,
  VideoCameraOutlined,
  resolveApiUrl,
  uploadMediaFile,
  useStudioFeedback,
  useStudioLocale,
} from "@colab/shared";

function splitFilename(name: string): { stem: string; ext: string } {
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return { stem: name, ext: "" };
  return { stem: name.slice(0, dot), ext: name.slice(dot) };
}

export interface VideoSlotCardProps {
  label: string;
  videoBadgeText?: string;
  audioBadgeText?: string | null;
  value: string;
  useVideoAudio?: boolean;
  onUseVideoAudioChange?: (next: boolean) => void;
  onChange: (fileRef: string) => void;
  onRemoveSlot?: () => void;
  allowClear?: boolean;
}

export function VideoSlotCard({
  label,
  videoBadgeText,
  audioBadgeText,
  value,
  useVideoAudio,
  onUseVideoAudioChange,
  onChange,
  onRemoveSlot,
  allowClear = true,
}: VideoSlotCardProps) {
  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
  const [videoMeta, setVideoMeta] = useState<{ w: number; h: number; dur: number } | null>(null);

  const handleFileUpload = async (file: File) => {
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
      onChange(res.file_id);
      message.success(t(`Uploaded video: ${res.filename}`, `已上传视频：${res.filename}`));
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("Failed to upload reference video", "上传参考视频失败"));
    } finally {
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
          {videoBadgeText && <code className="studio-ref-badge">{videoBadgeText}</code>}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0, whiteSpace: "nowrap" }}>
          {onRemoveSlot ? (
            <Button
              htmlType="button"
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              aria-label={t(`Remove ${label}`, `删除 ${label}`)}
              style={{ paddingInline: 4, blockSize: 24, fontSize: 12 }}
              onClick={onRemoveSlot}
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
              style={{ paddingInline: 4, blockSize: 24, fontSize: 12 }}
              onClick={() => {
                setVideoMeta(null);
                onChange("");
              }}
            >
              {t("Clear", "清空")}
            </Button>
          ) : null}
        </div>
      </div>

      {previewUrl ? (
        <div className="studio-image-preview-box">
          <video
            src={previewUrl}
            controls
            playsInline
            preload="metadata"
            width={88}
            height={52}
            style={{
              inlineSize: 88,
              blockSize: 52,
              borderRadius: 6,
              objectFit: "cover",
              background: "var(--m3e-color-on-surface)",
              flex: "0 0 auto",
            }}
            onLoadedMetadata={(e) => {
              const v = e.currentTarget;
              setVideoMeta({
                w: v.videoWidth || 0,
                h: v.videoHeight || 0,
                dur: Number.isFinite(v.duration) ? v.duration : 0,
              });
            }}
          />
          <div style={{ flex: "1 1 auto", minInlineSize: 0, display: "flex", flexDirection: "column", gap: 3 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 5, minInlineSize: 0, fontSize: 12.5, fontWeight: 600 }}>
              <VideoCameraOutlined style={{ flexShrink: 0, color: "var(--studio-accent)" }} />
              <span className="studio-filename">
                <span>{stem}</span>
                {ext}
              </span>
            </div>
            <Text type="secondary" className="studio-tabular" style={{ fontSize: 11.5, whiteSpace: "nowrap" }}>
              {videoMeta && videoMeta.w > 0
                ? `${videoMeta.w}×${videoMeta.h}${videoMeta.dur > 0 ? ` · ${videoMeta.dur.toFixed(1)}s` : ""}`
                : t("Video ready", "视频已就绪")}
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
          aria-label={t(`Upload reference video ${label}`, `点击上传视频 ${label}`)}
          onClick={() => fileInputRef.current?.click()}
        >
          <span className="studio-ref-dropzone-action">
            {uploading ? <LoadingOutlined /> : <CloudUploadOutlined />}
            <span>{t("Click to upload reference video", "点击上传参考视频")}</span>
          </span>
          <span className="studio-ref-dropzone-sub">
            {t("Drag & drop MP4 / WebM / MOV (2–15s recommended)", "支持拖拽 MP4 / WebM / MOV（推荐 2~15 秒片段）")}
          </span>
        </button>
      )}

      {typeof useVideoAudio === "boolean" && onUseVideoAudioChange && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 8,
            paddingBlockStart: 6,
            borderBlockStart: "1px dashed var(--studio-border)",
          }}
        >
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6, minInlineSize: 0 }}>
            <Text type="secondary" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
              {t("Extract video audio", "提取视频原声")}
            </Text>
            {useVideoAudio && audioBadgeText ? (
              <code className="studio-ref-badge">{audioBadgeText}</code>
            ) : null}
          </span>
          <Switch
            size="small"
            checked={useVideoAudio}
            onChange={onUseVideoAudioChange}
            aria-label={t(`${label} extract video audio`, `${label} 提取视频原声`)}
          />
        </div>
      )}
    </div>
  );
}

export interface AudioSlotCardProps {
  label: string;
  badgeText?: string;
  value: string;
  onChange: (fileRef: string) => void;
  onRemoveSlot?: () => void;
  allowClear?: boolean;
}

export function AudioSlotCard({
  label,
  badgeText,
  value,
  onChange,
  onRemoveSlot,
  allowClear = true,
}: AudioSlotCardProps) {
  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mountedRef = useRef(true);
  const requestingMicRef = useRef(false);
  const { t } = useStudioLocale();
  const { message } = useStudioFeedback();

  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [recording, setRecording] = useState(false);
  const [uploadedMeta, setUploadedMeta] = useState<{
    fileId: string;
    name: string;
    url: string;
  } | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const recorder = recorderRef.current;
      if (recorder) {
        recorder.onstop = null;
        recorder.ondataavailable = null;
        if (recorder.state !== "inactive") recorder.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, []);

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = await uploadMediaFile(file);
      setUploadedMeta({
        fileId: res.file_id,
        name: res.filename,
        url: res.url,
      });
      onChange(res.file_id);
      message.success(t(`Uploaded audio: ${res.filename}`, `已上传音频：${res.filename}`));
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("Failed to upload audio", "上传音频失败"));
    } finally {
      setUploading(false);
    }
  };

  const toggleRecording = async () => {
    if (recording) {
      if (recorderRef.current && recorderRef.current.state !== "inactive") {
        recorderRef.current.stop();
      }
      setRecording(false);
      return;
    }
    if (requestingMicRef.current) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      message.error(t("Microphone recording is not supported in this browser; please upload a file.", "当前浏览器不支持麦克风录制，请直接上传音频文件。"));
      return;
    }
    requestingMicRef.current = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        recorderRef.current = null;
        if (!mountedRef.current) return;
        setRecording(false);
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const ext = (recorder.mimeType || "").includes("mp4") ? "m4a" : "webm";
        const file = new File([blob], `h3_mic_${Date.now()}.${ext}`, {
          type: blob.type || "audio/webm",
        });
        await handleFileUpload(file);
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      message.error(t("Cannot access microphone. Please check browser permissions.", "无法访问麦克风，请检查浏览器麦克风权限。"));
    } finally {
      requestingMicRef.current = false;
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
        accept=".wav,.mp3,.flac,.ogg,.m4a,.aac,.webm,audio/*"
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

        <Space size={4}>
          <Button
            htmlType="button"
            size="small"
            type={recording ? "primary" : "text"}
            danger={recording}
            icon={recording ? <StopOutlined /> : <AudioOutlined />}
            style={{ paddingInline: 6, blockSize: 24, fontSize: 12 }}
            onClick={() => void toggleRecording()}
          >
            {recording ? t("Stop Rec", "停止录音") : t("Record", "录音")}
          </Button>

          {onRemoveSlot ? (
            <Button
              htmlType="button"
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              aria-label={t(`Remove ${label}`, `删除 ${label}`)}
              style={{ paddingInline: 6, blockSize: 24, fontSize: 12 }}
              onClick={onRemoveSlot}
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
              style={{ paddingInline: 6, blockSize: 24, fontSize: 12 }}
              onClick={() => onChange("")}
            >
              {t("Clear", "清空")}
            </Button>
          ) : null}
        </Space>
      </div>

      {previewUrl ? (
        <div
          className="studio-image-preview-box"
          style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <Text strong style={{ fontSize: 12.5, minInlineSize: 0 }}>
              <AudioOutlined style={{ marginInlineEnd: 5, color: "var(--studio-accent)" }} />
              <span className="studio-filename">
                <span>{stem}</span>
                {ext}
              </span>
            </Text>
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
          <audio
            controls
            preload="metadata"
            src={previewUrl}
            style={{ inlineSize: "100%", blockSize: 34 }}
          />
        </div>
      ) : (
        <button
          type="button"
          className="studio-ref-dropzone"
          aria-label={t(`Upload reference audio ${label}`, `点击上传音频 ${label}`)}
          onClick={() => fileInputRef.current?.click()}
        >
          <span className="studio-ref-dropzone-action">
            {uploading ? <LoadingOutlined /> : <CloudUploadOutlined />}
            <span>{recording ? t("Recording from mic...", "正在录制麦克风声音...") : t("Click to upload reference audio", "点击上传参考音频")}</span>
          </span>
          <span className="studio-ref-dropzone-sub">
            {t("Supports WAV / MP3 / FLAC / M4A or click Record above", "支持 WAV / MP3 / FLAC / M4A 或点击右上角「录音」")}
          </span>
        </button>
      )}
    </div>
  );
}
