import React, { useEffect, useId, useRef, useState } from "react";
import { resolveApiUrl, uploadMediaFile } from "../api/client";
import type { PresetItem } from "../api/types";
import {
  AudioOutlined,
  Button,
  CheckCircleFilled,
  CloudUploadOutlined,
  LoadingOutlined,
  Segmented,
  Space,
  StopOutlined,
  Tag,
  Text,
  useStudioFeedback,
} from "../ui/primitives";

export interface AudioSourceFieldProps {
  label: string;
  hint?: string;
  value: string;
  onChange: (fileRef: string) => void;
  presets?: PresetItem[];
  allowPreset?: boolean;
  extraRight?: React.ReactNode;
}

type SourceTab = "preset" | "upload" | "record";

export function AudioSourceField({
  label,
  hint,
  value,
  onChange,
  presets = [],
  allowPreset = true,
  extraRight,
}: AudioSourceFieldProps) {
  const inputId = useId();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const mountedRef = useRef(true);
  const uploadingRef = useRef(false);
  const startingRef = useRef(false);
  const { message } = useStudioFeedback();

  const hasPresets = allowPreset && presets.length > 0;
  const initialTab: SourceTab =
    hasPresets && (!value || value.startsWith("preset:")) ? "preset" : "upload";

  const [tab, setTab] = useState<SourceTab>(initialTab);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [recording, setRecording] = useState(false);
  const [starting, setStarting] = useState(false);
  const [uploadedMeta, setUploadedMeta] = useState<{
    fileId: string;
    name: string;
    url: string;
  } | null>(null);

  const activePreset = presets.find((p) => p.id === value) || presets[0];

  useEffect(() => {
    if (recording || starting) return;
    if (hasPresets && value.startsWith("preset:")) setTab("preset");
    else if (!hasPresets || (value && !value.startsWith("preset:"))) {
      setTab((current) => current === "preset" ? "upload" : current);
    }
  }, [hasPresets, value, recording, starting]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const recorder = recorderRef.current;
      if (recorder) {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        if (recorder.state !== "inactive") recorder.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const handleFileUpload = async (file: File) => {
    if (uploadingRef.current) return;
    if (!/\.(wav|mp3|flac|ogg|m4a|aac|webm)$/i.test(file.name)) {
      message.warning("请选择 WAV、MP3、FLAC、OGG、M4A、AAC 或 WebM 音频。");
      return;
    }
    if (!file.size || file.size > 512 * 1024 * 1024) {
      message.warning("音频不能为空，大小需在 512 MB 以内。");
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
      });
      onChange(res.file_id);
      message.success(`已载入参考音频：${res.filename}`);
    } catch (err) {
      if (mountedRef.current) message.error(err instanceof Error ? err.message : "上传音频失败");
    } finally {
      uploadingRef.current = false;
      if (mountedRef.current) setUploading(false);
    }
  };

  const startRecording = async () => {
    if (startingRef.current || recording || uploadingRef.current) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      message.error("当前浏览器不支持麦克风采集，请切换至文件上传。");
      return;
    }
    startingRef.current = true;
    setStarting(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (!mountedRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunks.push(e.data);
        }
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        recorderRef.current = null;
        if (!mountedRef.current) return;
        setRecording(false);
        const blob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        const ext = (recorder.mimeType || "").includes("mp4") ? "m4a" : "webm";
        const file = new File([blob], `mic_record_${Date.now()}.${ext}`, {
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
      if (mountedRef.current) message.error("无法访问麦克风，请检查浏览器权限。");
    } finally {
      startingRef.current = false;
      if (mountedRef.current) setStarting(false);
    }
  };

  const stopRecording = () => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
  };

  const previewUrl = (() => {
    if (!value) return "";
    if (value.startsWith("preset:")) {
      const found = presets.find((p) => p.id === value);
      return found ? resolveApiUrl(found.url, true) : "";
    }
    if (uploadedMeta && uploadedMeta.fileId === value) {
      return resolveApiUrl(uploadedMeta.url, true);
    }
    return resolveApiUrl(`/api/v1/files/${encodeURIComponent(value)}`, true);
  })();

  const activeSourceTitle = (() => {
    if (!value) return "尚未选择音频";
    if (value.startsWith("preset:")) {
      const found = presets.find((p) => p.id === value);
      return found ? found.label : value;
    }
    return uploadedMeta?.fileId === value ? uploadedMeta.name : `已上传音频 (${value})`;
  })();

  const modeOptions = [
    ...(hasPresets ? [{ label: "内置示例音色", value: "preset" }] : []),
    { label: "上传本地音频", value: "upload" },
    { label: "麦克风现录", value: "record" },
  ];

  return (
    <div className="studio-field-group" style={{ gap: "0.55rem" }}>
      <div className="studio-field-label">
        <div>
          <label htmlFor={inputId}>{label}</label>
          {hint && (
            <span className="studio-field-hint" style={{ marginInlineStart: 8 }}>
              {hint}
            </span>
          )}
        </div>
        {extraRight}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <Segmented
          size="small"
          disabled={recording || starting || uploading}
          options={modeOptions}
          value={tab}
          onChange={(val) => {
            const next = val as SourceTab;
            setTab(next);
            if (next === "preset" && activePreset && !value.startsWith("preset:")) {
              onChange(activePreset.id);
            }
          }}
        />
        {value && (
          <Tag icon={<CheckCircleFilled />} color="processing" style={{ marginInlineEnd: 0 }}>
            当前生效：{activeSourceTitle}
          </Tag>
        )}
      </div>

      {tab === "preset" && activePreset && (
        <div className="studio-dropzone" style={{ borderStyle: "solid", borderColor: "var(--studio-border)" }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <Space size={6} wrap>
              <Text strong style={{ fontSize: 13 }}>{activePreset.label}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {activePreset.description}
              </Text>
            </Space>
            {value !== activePreset.id && (
              <Button
                htmlType="button"
                size="small"
                type="primary"
                ghost
                onClick={() => onChange(activePreset.id)}
              >
                切换为此示例音色
              </Button>
            )}
          </div>
        </div>
      )}

      {tab === "upload" && (
        <div
          className="studio-dropzone"
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
          <Space wrap size={[10, 6]}>
            <Button
              htmlType="button"
              type="primary"
              ghost
              icon={uploading ? <LoadingOutlined /> : <CloudUploadOutlined />}
              loading={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              点击选择或拖拽音频至此
            </Button>
            <Text type="secondary" style={{ fontSize: 12 }}>
              支持 WAV / MP3 / FLAC / M4A · 推荐 3~15 秒无背景音乐清晰干声
            </Text>
          </Space>
        </div>
      )}

      {tab === "record" && (
        <div className="studio-dropzone">
          <Space wrap size={[10, 6]}>
            {!recording ? (
              <Button
                htmlType="button"
                type="primary"
                ghost
                icon={<AudioOutlined />}
                loading={uploading || starting}
                onClick={() => void startRecording()}
              >
                开始麦克风录音
              </Button>
            ) : (
              <Button
                htmlType="button"
                danger
                type="primary"
                icon={<StopOutlined />}
                onClick={stopRecording}
              >
                停止录音并上传
              </Button>
            )}
            <Text type="secondary" style={{ fontSize: 12 }}>
              {recording
                ? "正在采集麦克风声音... 请自然朗读 5~10 秒后点击停止"
                : "直接用浏览器麦克风录制一段你的声音完成克隆"}
            </Text>
          </Space>
        </div>
      )}

      {/* Persistent Active Reference Audio Preview */}
      {previewUrl && (
        <div className="studio-active-voice-bar">
          <Text style={{ fontSize: 12, fontWeight: 500, color: "var(--studio-text-secondary)" }}>
            参考音频试听：
          </Text>
          <audio
            className="studio-audio-player"
            style={{ flex: "1 1 260px", maxInlineSize: "100%" }}
            controls
            preload="metadata"
            src={previewUrl}
          />
        </div>
      )}
    </div>
  );
}
