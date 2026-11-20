import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { useStudioLocale } from "../i18n";
import {
  deleteCachedLora,
  fetchLoraCatalog,
  submitLoraDownloadTask,
  subscribeTaskProgress,
  uploadLoraSafetensors,
} from "../api/client";
import type { LoraCatalogEntry, LoraListResponse, LoraSlotConfig } from "../api/types";
import {
  Button,
  CheckCircleFilled,
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  HddOutlined,
  Input,
  LoadingOutlined,
  PlusOutlined,
  Popconfirm,
  Progress,
  Slider,
  Space,
  Switch,
  Tag,
  Text,
  Tooltip,
  useStudioFeedback,
} from "../ui/primitives";

export interface LoraManagerPanelProps {
  slots: LoraSlotConfig[];
  onChange: (nextSlots: LoraSlotConfig[]) => void;
  maxSlots?: number;
  excludeIds?: string[];
}

function splitSafetensorsName(name: string): { stem: string; ext: string } {
  const lower = name.toLowerCase();
  if (lower.endsWith(".safetensors")) {
    return {
      stem: name.slice(0, -".safetensors".length),
      ext: ".safetensors",
    };
  }
  return { stem: name, ext: "" };
}

function formatSizeMb(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(0)} MB`;
}

export function LoraManagerPanel({
  slots,
  onChange,
  maxSlots = 6,
  excludeIds = [],
}: LoraManagerPanelProps) {
  const sourceInputId = useId();
  const uploadInputId = useId();
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);
  const { t } = useStudioLocale();
  const { message } = useStudioFeedback();

  const [catalog, setCatalog] = useState<LoraListResponse | null>(null);
  const [remoteSource, setRemoteSource] = useState("");

  const [dlState, setDlState] = useState<{
    busy: boolean;
    progress: number;
    stage: string;
  }>({ busy: false, progress: 0, stage: "" });
  const [uploadingLocal, setUploadingLocal] = useState(false);

  const refreshCatalog = useCallback(async () => {
    try {
      const data = await fetchLoraCatalog();
      setCatalog(data);
    } catch {
      // silent during initial boot
    }
  }, []);

  useEffect(() => {
    void refreshCatalog();
    return () => {
      unsubRef.current?.();
    };
  }, [refreshCatalog]);

  const attachLoraToStack = useCallback(
    (entry: LoraCatalogEntry) => {
      const existingIdx = slots.findIndex(
        (s) => s.lora === entry.filename || s.lora === entry.id
      );
      if (existingIdx >= 0) {
        const updated = slots.map((s, idx) =>
          idx === existingIdx ? { ...s, lora: entry.filename, enabled: true } : s
        );
        onChange(updated);
        message.info(t(`Enabled LoRA: ${entry.label}`, `已启用 LoRA：${entry.label}`));
        return;
      }
      if (slots.length >= maxSlots) {
        message.warning(t(`Up to ${maxSlots} LoRAs can be stacked at once.`, `最多支持同时叠加 ${maxSlots} 个 LoRA。`));
        return;
      }
      onChange([
        ...slots,
        {
          lora: entry.filename,
          strength_model: entry.recommended_strength ?? 0.85,
          apply_to_clip: false,
          strength_clip: 1.0,
          enabled: true,
        },
      ]);
      message.success(t(`Mounted LoRA: ${entry.label}`, `已挂载 LoRA：${entry.label}`));
    },
    [maxSlots, message, onChange, slots, t]
  );

  const triggerDownloadAndAttach = async (
    source: string
  ) => {
    const cleanSrc = source.trim();
    if (!cleanSrc) {
      message.warning(t("Enter a Hugging Face repo (e.g. owner/repo) or a .safetensors URL.", "请输入 Hugging Face 仓库名（如 owner/repo）或 .safetensors 链接。"));
      return;
    }
    unsubRef.current?.();
    setDlState({ busy: true, progress: 0.04, stage: t("Downloading and verifying in background...", "正在后台下载并校验...") });
    try {
      const task = await submitLoraDownloadTask({
        source: cleanSrc,
      });

      unsubRef.current = subscribeTaskProgress<{ kind: string; lora: LoraCatalogEntry }>(
        task.task_id,
        (snap) => {
          setDlState({
            busy: snap.status === "queued" || snap.status === "running",
            progress: snap.progress,
            stage: snap.stage,
          });
          if (snap.status === "succeeded" && snap.result?.lora) {
            const downloaded = snap.result.lora;
            setRemoteSource("");
            void refreshCatalog();
            attachLoraToStack(downloaded);
          } else if (snap.status === "failed") {
            message.error(snap.error || t("LoRA download or verification failed", "LoRA 下载校验失败"));
          }
        },
        (err) => {
          setDlState({ busy: false, progress: 0, stage: "" });
          message.error(err.message);
        }
      );
    } catch (err) {
      setDlState({ busy: false, progress: 0, stage: "" });
      message.error(err instanceof Error ? err.message : t("Failed to queue LoRA download", "提交 LoRA 下载失败"));
    }
  };

  const handleLocalLoraUpload = async (file: File) => {
    setUploadingLocal(true);
    try {
      const entry = await uploadLoraSafetensors(file);
      await refreshCatalog();
      attachLoraToStack(entry);
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("Failed to upload local LoRA", "本地 LoRA 上传失败"));
    } finally {
      setUploadingLocal(false);
    }
  };

  const handleDeleteCached = async (filename: string) => {
    try {
      const res = await deleteCachedLora(filename);
      onChange(slots.filter((s) => s.lora !== filename));
      await refreshCatalog();
      message.success(
        t(
          `Deleted ${res.deleted} (freed ${(res.freed_bytes / 1024 ** 2).toFixed(1)} MB)`,
          `已删除 ${res.deleted}（释放 ${(res.freed_bytes / 1024 ** 2).toFixed(1)} MB）`,
        ),
      );
    } catch (err) {
      message.error(err instanceof Error ? err.message : t("Failed to delete LoRA", "删除 LoRA 失败"));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
      {/* 1. Active Mounted LoRA Stack (only rendered when non-empty) */}
      {slots.length > 0 && (
        <div className="studio-lora-stack">
          {slots.map((slot, idx) => {
            const matched = catalog?.items.find(
              (it) => it.filename === slot.lora || it.id === slot.lora
            );
            const { stem, ext } = splitSafetensorsName(matched?.filename || slot.lora);
            return (
              <div
                key={`${slot.lora}-${idx}`}
                className="studio-lora-card"
                data-enabled={slot.enabled ? "true" : "false"}
              >
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <Space size={8} style={{ minInlineSize: 0, flex: "1 1 200px" }}>
                    <Switch
                      size="small"
                      checked={slot.enabled}
                      onChange={(checked) => {
                        const next = [...slots];
                        next[idx] = { ...slot, enabled: checked };
                        onChange(next);
                      }}
                    />
                    <div style={{ minInlineSize: 0 }}>
                      <Text strong style={{ fontSize: 13 }}>
                        {matched?.label || stem}
                      </Text>
                      <span
                        className="studio-filename"
                        style={{ marginInlineStart: 6, fontSize: 11.5, color: "var(--studio-text-muted)", maxInlineSize: 220 }}
                      >
                        <span>{stem}</span>
                        {ext}
                      </span>
                    </div>
                  </Space>

                  <Space size={6}>
                    <Button
                      htmlType="button"
                      size="small"
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => onChange(slots.filter((_, i) => i !== idx))}
                    >
                      {t("Remove", "移除")}
                    </Button>
                  </Space>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr auto", alignItems: "center", gap: 12 }}>
                  <Slider
                    min={-1.5}
                    max={2.0}
                    step={0.05}
                    disabled={!slot.enabled}
                    value={slot.strength_model}
                    onChange={(val) => {
                      const next = [...slots];
                      next[idx] = { ...slot, strength_model: Number(val) };
                      onChange(next);
                    }}
                  />
                  <Text strong className="studio-tabular" style={{ minInlineSize: 82, textAlign: "end", fontSize: 12.5 }}>
                    {t(`Strength ${slot.strength_model.toFixed(2)}`, `强度 ${slot.strength_model.toFixed(2)}`)}
                  </Text>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 2. Compact Single-Row Online Puller + Upload */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <label htmlFor={sourceInputId} className="studio-visually-hidden">
          {t("Enter Hugging Face repo or .safetensors download URL", "输入 Hugging Face 仓库或 .safetensors 下载链接")}
        </label>
        <Input
          id={sourceInputId}
          style={{ flex: "1 1 260px" }}
          value={remoteSource}
          onValueChange={(value) => setRemoteSource(value)}
          placeholder={t("Paste .safetensors URL or Hugging Face repo", "粘贴模型下载链接或 Hugging Face 仓库名")}
          onPressEnter={() =>
            void triggerDownloadAndAttach(remoteSource)
          }
        />
        <Button
          htmlType="button"
          type="primary"
          ghost
          icon={dlState.busy ? <LoadingOutlined /> : <DownloadOutlined />}
          loading={dlState.busy}
          onClick={() =>
            void triggerDownloadAndAttach(remoteSource)
          }
        >
          {t("Add Model", "添加模型")}
        </Button>

        <input
          id={uploadInputId}
          name="lora_file"
          ref={uploadInputRef}
          type="file"
          accept=".safetensors"
          className="studio-visually-hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) {
              void handleLocalLoraUpload(f);
            }
            e.target.value = "";
          }}
        />
        <Button
          htmlType="button"
          icon={<CloudUploadOutlined />}
          loading={uploadingLocal}
          onClick={() => uploadInputRef.current?.click()}
        >
          {t("Upload Model", "上传模型")}
        </Button>
      </div>

      {/* Available models and download space. */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "6px 12px" }}>
        <Space size={[6, 6]} wrap>
          {catalog && catalog.items.some((it) => !excludeIds.includes(it.id)) && (
            <>
              <Text type="secondary" style={{ fontSize: 12 }}>{t("Available:", "可用模型：")}</Text>
              {catalog.items
                .filter((it) => !excludeIds.includes(it.id))
                .map((item) => {
                  const isMounted = slots.some(
                    (s) => s.lora === item.filename || s.lora === item.id
                  );
                  return (
                    <Space key={item.id} size={2}>
                      <Tooltip title={`${item.description} (${item.filename}${item.size_bytes ? ` · ${formatSizeMb(item.size_bytes)}` : ""})`}>
                        <Button
                          htmlType="button"
                          size="small"
                          type={isMounted ? "default" : "dashed"}
                          icon={
                            isMounted ? (
                              <CheckCircleFilled style={{ color: "var(--m3e-color-success)" }} />
                            ) : item.installed ? (
                              <PlusOutlined />
                            ) : (
                              <DownloadOutlined />
                            )
                          }
                          disabled={isMounted || dlState.busy}
                          onClick={() =>
                            item.installed
                              ? attachLoraToStack(item)
                              : void triggerDownloadAndAttach(item.id)
                          }
                        >
                          {item.label}
                        </Button>
                      </Tooltip>
                      {item.installed && (
                        <Popconfirm
                          title={t(`Delete cached ${item.filename} from disk?`, `从磁盘删除缓存 ${item.filename}？`)}
                          okText={t("Delete", "删除")}
                          cancelText={t("Cancel", "取消")}
                          onConfirm={() => void handleDeleteCached(item.filename)}
                        >
                          <Button
                            htmlType="button"
                            size="small"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            aria-label={t(`Delete ${item.filename}`, `删除 ${item.filename}`)}
                          />
                        </Popconfirm>
                      )}
                    </Space>
                  );
                })}
            </>
          )}
        </Space>

        <Space size={10}>
          {catalog && (
            <span className="studio-tabular" style={{ fontSize: 11.5, color: "var(--studio-text-muted)" }}>
              <HddOutlined style={{ marginInlineEnd: 4 }} />
              {t(`Free disk ${catalog.free_disk_gb.toFixed(1)} GiB`, `可用磁盘 ${catalog.free_disk_gb.toFixed(1)} GiB`)}
            </span>
          )}

        </Space>
      </div>

      {dlState.busy && (
        <div>
          <Progress percent={Math.round(dlState.progress * 100)} status="active" size="small" />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {dlState.stage}
          </Text>
        </div>
      )}
    </div>
  );
}
