import React, { useCallback, useEffect, useId, useRef, useState } from "react";
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
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const unsubRef = useRef<(() => void) | null>(null);
  const { message } = useStudioFeedback();

  const [catalog, setCatalog] = useState<LoraListResponse | null>(null);
  const [remoteSource, setRemoteSource] = useState("");
  const [customFilename, setCustomFilename] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [showAdvancedDl, setShowAdvancedDl] = useState(false);

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
        message.info(`已启用 LoRA：${entry.label}`);
        return;
      }
      if (slots.length >= maxSlots) {
        message.warning(`最多支持同时叠加 ${maxSlots} 个 LoRA。`);
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
      message.success(`已挂载 LoRA：${entry.label}`);
    },
    [maxSlots, message, onChange, slots]
  );

  const triggerDownloadAndAttach = async (
    source: string,
    opts?: { filename?: string; token?: string }
  ) => {
    const cleanSrc = source.trim();
    if (!cleanSrc) {
      message.warning("请输入 Hugging Face 仓库名（如 owner/repo）或 .safetensors 链接。");
      return;
    }
    unsubRef.current?.();
    setDlState({ busy: true, progress: 0.04, stage: "正在后台下载并校验..." });
    try {
      const task = await submitLoraDownloadTask({
        source: cleanSrc,
        filename: opts?.filename?.trim() || undefined,
        token: opts?.token?.trim() || undefined,
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
            setCustomFilename("");
            void refreshCatalog();
            attachLoraToStack(downloaded);
          } else if (snap.status === "failed") {
            message.error(snap.error || "LoRA 下载校验失败");
          }
        },
        (err) => {
          setDlState({ busy: false, progress: 0, stage: "" });
          message.error(err.message);
        }
      );
    } catch (err) {
      setDlState({ busy: false, progress: 0, stage: "" });
      message.error(err instanceof Error ? err.message : "提交 LoRA 下载失败");
    }
  };

  const handleLocalLoraUpload = async (file: File) => {
    setUploadingLocal(true);
    try {
      const entry = await uploadLoraSafetensors(file);
      await refreshCatalog();
      attachLoraToStack(entry);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "本地 LoRA 上传失败");
    } finally {
      setUploadingLocal(false);
    }
  };

  const handleDeleteCached = async (filename: string) => {
    try {
      const res = await deleteCachedLora(filename);
      onChange(slots.filter((s) => s.lora !== filename));
      await refreshCatalog();
      message.success(`已删除 ${res.deleted}（释放 ${(res.freed_bytes / 1024 ** 2).toFixed(1)} MB）`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : "删除 LoRA 失败");
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
                    <Tooltip title="默认仅作用于 UNet 扩散主干；点击可切换是否同时作用于文本编码器">
                      <Tag
                        color={slot.apply_to_clip ? "processing" : "default"}
                        style={{ cursor: "pointer", marginInlineEnd: 0 }}
                        onClick={() => {
                          const next = [...slots];
                          next[idx] = { ...slot, apply_to_clip: !slot.apply_to_clip };
                          onChange(next);
                        }}
                      >
                        CLIP: {slot.apply_to_clip ? "开" : "仅 UNet"}
                      </Tag>
                    </Tooltip>
                    <Button
                      htmlType="button"
                      size="small"
                      type="text"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => onChange(slots.filter((_, i) => i !== idx))}
                    >
                      移除
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
                  <Text strong className="studio-tabular" style={{ minInlineSize: 62, textAlign: "end", fontSize: 12.5 }}>
                    强度 {slot.strength_model.toFixed(2)}
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
          输入 Hugging Face 仓库或 .safetensors 下载链接
        </label>
        <Input
          id={sourceInputId}
          style={{ flex: "1 1 260px" }}
          value={remoteSource}
          onChange={(e) => setRemoteSource(e.target.value)}
          placeholder="粘贴 Hugging Face 仓库（owner/repo）或 Civitai .safetensors 直链自动后台下载挂载..."
          onPressEnter={() =>
            void triggerDownloadAndAttach(remoteSource, {
              filename: customFilename,
              token: authToken,
            })
          }
        />
        <Button
          htmlType="button"
          type="primary"
          ghost
          icon={dlState.busy ? <LoadingOutlined /> : <DownloadOutlined />}
          loading={dlState.busy}
          onClick={() =>
            void triggerDownloadAndAttach(remoteSource, {
              filename: customFilename,
              token: authToken,
            })
          }
        >
          拉取挂载
        </Button>

        <input
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
          本地上传
        </Button>
      </div>

      {/* Optional Token / Custom Filename Row + Disk Readout + Quick-Mount Chips */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "6px 12px" }}>
        <Space size={[6, 6]} wrap>
          {catalog && catalog.items.some((it) => !excludeIds.includes(it.id)) && (
            <>
              <Text type="secondary" style={{ fontSize: 12 }}>快速挂载：</Text>
              {catalog.items
                .filter((it) => !excludeIds.includes(it.id))
                .map((item) => {
                  const isMounted = slots.some(
                    (s) => s.lora === item.filename || s.lora === item.id
                  );
                  return (
                    <Space key={item.id} size={2}>
                      <Tooltip title={`${item.description}（${item.filename}${item.size_bytes ? ` · ${formatSizeMb(item.size_bytes)}` : ""}）`}>
                        <Button
                          htmlType="button"
                          size="small"
                          type={isMounted ? "default" : "dashed"}
                          icon={
                            isMounted ? (
                              <CheckCircleFilled style={{ color: "#16a34a" }} />
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
                          title={`从磁盘删除缓存 ${item.filename}？`}
                          okText="删除"
                          cancelText="取消"
                          onConfirm={() => void handleDeleteCached(item.filename)}
                        >
                          <Button
                            htmlType="button"
                            size="small"
                            type="text"
                            danger
                            icon={<DeleteOutlined />}
                            aria-label={`删除 ${item.filename}`}
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
              可用磁盘 {catalog.free_disk_gb.toFixed(1)} GiB
            </span>
          )}
          <Button
            htmlType="button"
            size="small"
            type="link"
            style={{ padding: 0, blockSize: "auto", fontSize: 12 }}
            onClick={() => setShowAdvancedDl((v) => !v)}
          >
            {showAdvancedDl ? "收起鉴权/重命名" : "鉴权 Token / 重命名"}
          </Button>
        </Space>
      </div>

      {showAdvancedDl && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 8 }}>
          <Input
            size="small"
            value={customFilename}
            onChange={(e) => setCustomFilename(e.target.value)}
            placeholder="可选：保存文件名（如 my_style.safetensors）"
          />
          <Input.Password
            size="small"
            value={authToken}
            onChange={(e) => setAuthToken(e.target.value)}
            placeholder="可选：HF_TOKEN 或 Civitai API Key（不落盘）"
          />
        </div>
      )}

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
