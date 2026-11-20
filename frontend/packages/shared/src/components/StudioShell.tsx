import React, { useCallback, useEffect, useId, useState } from "react";
import {
  fetchSystemStatus,
  configureApiKey,
  getEffectiveOrigin,
  loadApiKey,
  saveApiKey,
} from "../api/client";
import { CodeBlock } from "./CodeBlock";
import { useStudioLocale } from "../i18n";
import type { SystemStatus, TunnelMode } from "../api/types";
import {
  Alert,
  ApiOutlined,
  Badge,
  Button,
  BookOutlined,
  CloudServerOutlined,
  CodeOutlined,
  CopyOutlined,
  Dialog,
  DashboardOutlined,
  GithubOutlined,
  GlobalOutlined,
  IconButton,
  Input,
  KeyOutlined,
  MaterialShapeView,
  Meter,
  Modal,
  Popover,
  ReloadOutlined,
  ScrollArea,
  Space,
  Tabs,
  Tag,
  Text,
  Tooltip,
  useStudioFeedback,
} from "../ui/primitives";

export interface StudioCustomApiTabContext {
  origin: string;
  savedKey: string;
  authRequired: boolean;
  copyText: (text: string, tip: string) => Promise<void>;
}

export interface StudioShellProps {
  brandBadge?: string;
  defaultTitle: string;
  defaultSubtitle?: string;
  apiEndpointPath?: string;
  mediaKind?: "audio" | "image" | "video";
  layoutRatio?: "default" | "chat";
  apiModalTitle?: string;
  apiDrawerTitle?: string;
  customApiTabs?: (
    ctx: StudioCustomApiTabContext
  ) => Array<{ key: string; label: React.ReactNode; icon?: React.ReactNode; children: React.ReactNode }>;
  sampleRequestBody: Record<string, unknown>;
  headerExtra?: React.ReactNode;
  topBanner?: React.ReactNode;
  leftPane: React.ReactNode;
  rightPane: React.ReactNode;
  onAuthChanged?: () => void;
}

function detectTunnelMode(sys: SystemStatus | null): TunnelMode {
  if (sys?.tunnel_mode && sys.tunnel_mode !== "local") {
    return sys.tunnel_mode;
  }
  if (typeof window !== "undefined") {
    const host = window.location.hostname.toLowerCase();
    if (host.endsWith(".trycloudflare.com")) {
      return "quick";
    }
    if (host && host !== "127.0.0.1" && host !== "localhost" && host !== "::1") {
      return "custom";
    }
  }
  return sys?.tunnel_mode || "local";
}

function meterState(
  pct: number,
  t: <T = string>(en: T, zh: T) => T,
): { statusLabel?: string; tagColor?: "warning" | "error" } {
  if (pct >= 92) {
    return { statusLabel: t("Alert", "告警"), tagColor: "error" };
  }
  if (pct >= 78) {
    return { statusLabel: t("High", "偏高"), tagColor: "warning" };
  }
  return {};
}

function shortGpuLabel(name: string): string {
  const cleaned = name.replace(/^NVIDIA\s+/i, "").replace(/^Tesla\s+/i, "").trim();
  const token = cleaned.split(/[\s-]+/)[0];
  return token || "GPU";
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  if (mins < 60) return `${mins}m ${seconds % 60}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

interface TelemetryMeterRowProps {
  id: string;
  title: string;
  detail: string;
  percent: number;
  t: <T = string>(en: T, zh: T) => T;
}

function TelemetryMeterRow({ id, title, detail, percent, t }: TelemetryMeterRowProps) {
  const clamped = Math.min(100, Math.max(0, Number.isFinite(percent) ? percent : 0));
  const state = meterState(clamped, t);
  return (
    <Meter
      id={id}
      className="studio-tabular"
      value={Math.round(clamped * 10) / 10}
      min={0}
      max={100}
      label={
        <span className="studio-meter-label">
          <span>{title}</span>
          {state.statusLabel && state.tagColor && (
            <Tag color={state.tagColor} style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: "16px", paddingInline: 5 }}>
              {state.statusLabel}
            </Tag>
          )}
        </span>
      }
      valueText={detail}
    />
  );
}

export function StudioShell({
  brandBadge = "AI",
  defaultTitle,
  defaultSubtitle,
  apiEndpointPath = "/api/v1/generate",
  mediaKind = "audio",
  layoutRatio = "default",
  apiModalTitle,
  apiDrawerTitle,
  customApiTabs,
  sampleRequestBody,
  headerExtra,
  topBanner,
  leftPane,
  rightPane,
  onAuthChanged,
}: StudioShellProps) {
  const { locale, toggleLocale, t } = useStudioLocale();
  const { message } = useStudioFeedback();
  const gpuUtilBarId = useId();
  const vramBarId = useId();
  const cpuBarId = useId();
  const ramBarId = useId();
  const diskBarId = useId();
  const controlsId = useId();
  const resultsId = useId();

  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [refreshingSys, setRefreshingSys] = useState(false);
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  const [apiModalOpen, setApiModalOpen] = useState(false);

  const [savedKey, setSavedKey] = useState<string>(() => loadApiKey());
  const [apiKeyInput, setApiKeyInput] = useState<string>(() => loadApiKey());
  const [savingKey, setSavingKey] = useState(false);

  const refreshSystem = useCallback(async (manual = false) => {
    if (manual) setRefreshingSys(true);
    try {
      const data = await fetchSystemStatus();
      setSys(data);
    } catch {
      setSys(null);
    } finally {
      if (manual) setRefreshingSys(false);
    }
  }, []);

  useEffect(() => {
    void refreshSystem(false);
    const timer = window.setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      void refreshSystem(false);
    }, 4000);
    const onVisChange = () => {
      if (document.visibilityState === "visible") {
        void refreshSystem(false);
      }
    };
    document.addEventListener("visibilitychange", onVisChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisChange);
    };
  }, [refreshSystem]);

  const tunnelMode = detectTunnelMode(sys);
  const origin = getEffectiveOrigin(sys?.public_url);

  const authHeaderLine = savedKey
    ? `  -H "Authorization: Bearer ${savedKey}" \\\n`
    : sys?.auth_required
    ? `  -H "Authorization: Bearer <YOUR_APP_API_KEY>" \\\n`
    : "";

  const authPollSuffix = savedKey
    ? ` -H "Authorization: Bearer ${savedKey}"`
    : sys?.auth_required
    ? ` -H "Authorization: Bearer <YOUR_APP_API_KEY>"`
    : "";

  const pythonHeaders = savedKey || sys?.auth_required
    ? { Authorization: `Bearer ${savedKey || "<YOUR_APP_API_KEY>"}` }
    : {};

  const prettyJson = JSON.stringify(sampleRequestBody, null, 2);
  const sampleUploadFile =
    mediaKind === "image"
      ? "reference.png"
      : mediaKind === "video"
        ? "input.mp4"
        : "your_voice.wav";
  const sampleMediaLabel =
    mediaKind === "image"
      ? t("reference image", "参考图片")
      : mediaKind === "video"
        ? t("reference video", "参考视频")
        : t("reference audio", "参考音频");
  const resultUrlKey =
    mediaKind === "image"
      ? "image_url"
      : mediaKind === "video"
        ? "video_url"
        : "audio_url";

  const curlSnippet = `# ${t(`1. (Optional) Upload a local ${sampleMediaLabel} to obtain file_id`, `1. (可选) 上传本地${sampleMediaLabel}获取 file_id`)}
curl -X POST "${origin}/api/v1/files" \\
${authHeaderLine}  -F "file=@./${sampleUploadFile}"

# ${t("2. Submit an asynchronous generation task (synced with current Studio parameters)", "2. 异步提交生成任务 (实时同步左侧全量调优参数)")}
curl -X POST "${origin}${apiEndpointPath}" \\
  -H "Content-Type: application/json" \\
${authHeaderLine}  -d '${prettyJson.replace(/'/g, "'\\''")}'

# ${t("3. Poll task status and fetch outputs", "3. 轮询任务状态与生成结果")}
curl "${origin}/api/v1/tasks/<TASK_ID>"${authPollSuffix}`;

  const pythonSnippet = `import json
import time
import requests

BASE_URL = ${JSON.stringify(origin)}
HEADERS = json.loads(${JSON.stringify(JSON.stringify(pythonHeaders))})

# ${t(`1. (Optional) Upload custom ${sampleMediaLabel} to get file_id`, `1. 如需使用自定义${sampleMediaLabel}，先上传获取 file_id`)}
# with open("${sampleUploadFile}", "rb") as f:
#     file_id = requests.post(f"{BASE_URL}/api/v1/files", headers=HEADERS, files={"file": f}).json()["file_id"]

# ${t("2. Submit async inference task (includes current UI settings)", "2. 提交异步推理任务（包含当前页面设置）")}
payload = json.loads(${JSON.stringify(prettyJson)})
resp = requests.post(f"{BASE_URL}${apiEndpointPath}", json=payload, headers=HEADERS, timeout=30)
resp.raise_for_status()
task_id = resp.json()["task_id"]
print("${t("Submitted task:", "已提交任务:")}", task_id)

# ${t("3. Poll progress and inspect result", "3. 轮询进度并下载最终产物")}
while True:
    response = requests.get(f"{BASE_URL}/api/v1/tasks/{task_id}", headers=HEADERS, timeout=15)
    response.raise_for_status()
    info = response.json()
    print(f"[{info['status']}] {info['progress'] * 100:.0f}% - {info['stage']}")
    if info["status"] == "succeeded":
        res = info["result"]
        print("${t("Succeeded, output URL:", "生成成功，结果地址:")}", BASE_URL + res["${resultUrlKey}"])
        print("${t("Metadata:", "返回元数据:")}", {k: v for k, v in res.items() if k not in ("subtitles", "images")})
        break
    if info["status"] in ("failed", "cancelled"):
        raise RuntimeError(info.get("error") or "${t("Task failed", "任务未成功完成")}")
    time.sleep(1.0)`;

  const copyText = async (text: string, tip: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success(tip);
    } catch {
      message.warning(t("Copy failed. Please select and copy manually.", "复制失败，请手动选中代码复制"));
    }
  };

  const handleSaveKey = async () => {
    if (savingKey) return;
    setSavingKey(true);
    try {
      const clean = apiKeyInput.trim();
      await configureApiKey(clean);
      saveApiKey(clean);
      setSavedKey(clean);
      setKeyModalOpen(false);
      message.success(clean ? t("API key updated", "API Key 已生效") : t("API authentication disabled", "API 鉴权已关闭"));
      onAuthChanged?.();
      await refreshSystem(false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("Failed to save API key", "设置失败"));
    } finally {
      setSavingKey(false);
    }
  };

  const vramPct =
    sys?.gpu.available && sys.gpu.vram_total_gib > 0
      ? sys.gpu.vram_percent ?? (sys.gpu.vram_used_gib / sys.gpu.vram_total_gib) * 100
      : 0;
  const cpuPct = sys?.host?.cpu_percent ?? 0;
  const ramPct = sys?.host?.ram_percent ?? 0;
  const diskPct = sys?.host?.disk_percent ?? 0;
  const peakPct = Math.max(vramPct, cpuPct, ramPct, diskPct);
  const dotColor = peakPct >= 92 ? "var(--m3e-color-error)" : peakPct >= 78 ? "var(--m3e-color-warning)" : "var(--m3e-color-success)";

  const telemetryPopoverContent = sys ? (
    <div className="studio-telemetry-panel">
      <div className="studio-telemetry-header">
        <Space size={6} wrap>
          <DashboardOutlined style={{ color: "var(--studio-accent)" }} />
          <Text strong style={{ fontSize: 13 }}>
            {t("Live System Telemetry", "机器实时资源监控")}
          </Text>
          <Tag color={sys.gpu.available ? "success" : "default"} style={{ marginInlineEnd: 0 }}>
            {sys.gpu.available ? "CUDA" : t("CPU / Mock", "CPU / Mock")}
          </Tag>
        </Space>
        <Button
          htmlType="button"
          size="small"
          type="text"
          icon={<ReloadOutlined spin={refreshingSys} />}
          onClick={() => void refreshSystem(true)}
          aria-label={t("Refresh system telemetry", "立即刷新机器状态")}
        >
          {t("Refresh", "刷新")}
        </Button>
      </div>

      {sys.gpu.available ? (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 4, fontSize: 12 }}>
            <Text strong>{sys.gpu.name}</Text>
            <Space size={4} className="studio-tabular">
              {sys.gpu.temperature_c != null && <Tag style={{ marginInlineEnd: 0 }}>{Math.round(sys.gpu.temperature_c)}°C</Tag>}
              {sys.gpu.power_draw_w != null && (
                <Tag style={{ marginInlineEnd: 0 }}>
                  {Math.round(sys.gpu.power_draw_w)}
                  {sys.gpu.power_limit_w ? `/${Math.round(sys.gpu.power_limit_w)}` : ""}W
                </Tag>
              )}
              {sys.gpu.bf16_supported && <Tag color="processing" style={{ marginInlineEnd: 0 }}>BF16</Tag>}
            </Space>
          </div>

          {sys.gpu.utilization_pct != null && (
            <TelemetryMeterRow
              id={gpuUtilBarId}
              title={t("GPU Utilization", "GPU 算力利用率")}
              detail={`${Math.round(sys.gpu.utilization_pct)}%`}
              percent={sys.gpu.utilization_pct}
              t={t}
            />
          )}

          <TelemetryMeterRow
            id={vramBarId}
            title={t("GPU VRAM", "GPU 显存 (VRAM)")}
            detail={`${sys.gpu.vram_used_gib.toFixed(1)} / ${sys.gpu.vram_total_gib.toFixed(1)} GiB (${Math.round(vramPct)}%)`}
            percent={vramPct}
            t={t}
          />
        </>
      ) : (
        <Alert
          type="info"
          showIcon
          icon={<CloudServerOutlined />}
          description={
            <>
              {sys.gpu.name}
              {t(
                " (GPU compute, VRAM, and temperature appear automatically on Colab GPU runtimes)",
                "（在 Colab GPU 环境启动后自动展示显卡算力、显存与温度）",
              )}
            </>
          }
        />
      )}

      {sys.host && (
        <>
          <TelemetryMeterRow
            id={cpuBarId}
            title={t(`CPU (${sys.host.cpu_count} cores)`, `CPU 负载 (${sys.host.cpu_count} 核)`)}
            detail={`${sys.host.cpu_percent.toFixed(1)}%${
              sys.host.load_avg_1m != null ? ` · Load ${sys.host.load_avg_1m.toFixed(2)}` : ""
            }`}
            percent={sys.host.cpu_percent}
            t={t}
          />

          {sys.host.ram_total_gib > 0 && (
            <TelemetryMeterRow
              id={ramBarId}
              title={t("System RAM", "系统内存 (RAM)")}
              detail={`${sys.host.ram_used_gib.toFixed(1)} / ${sys.host.ram_total_gib.toFixed(1)} GiB (${Math.round(ramPct)}%)`}
              percent={ramPct}
              t={t}
            />
          )}

          {sys.host.disk_total_gib > 0 && (
            <TelemetryMeterRow
              id={diskBarId}
              title={t("Workspace Disk", "工作区磁盘")}
              detail={t(
                `${sys.host.disk_used_gib.toFixed(0)}G used / ${sys.host.disk_free_gib.toFixed(0)}G free (${Math.round(diskPct)}%)`,
                `已用 ${sys.host.disk_used_gib.toFixed(0)}G / 剩余 ${sys.host.disk_free_gib.toFixed(0)}G (${Math.round(diskPct)}%)`,
              )}
              percent={diskPct}
              t={t}
            />
          )}
        </>
      )}

      <dl className="studio-telemetry-dl studio-tabular">
        <div>
          <dt>{t("Running / Queued", "任务运行 / 排队")}</dt>
          <dd>
            {sys.queue.running} / {sys.queue.queued}
          </dd>
        </div>
        <div>
          <dt>{t("Succeeded / Failed", "已完成 / 失败")}</dt>
          <dd>
            {sys.queue.succeeded} / {sys.queue.failed}
          </dd>
        </div>
        {sys.host && (
          <div>
            <dt>{t("Uptime", "服务已运行")}</dt>
            <dd>{formatUptime(sys.host.uptime_sec)}</dd>
          </div>
        )}
        {sys.gpu.cuda_version && (
          <div>
            <dt>CUDA / Torch</dt>
            <dd>
              {sys.gpu.cuda_version} / {sys.gpu.torch_version.split("+")[0]}
            </dd>
          </div>
        )}
      </dl>
    </div>
  ) : null;

  return (
    <div className="studio-shell" data-layout={layoutRatio}>
      <header className="studio-header">
        <div className="studio-header-inner">
          <div className="studio-header-brand">
            <div className="studio-brand-badge" aria-hidden="true">
              <MaterialShapeView shape="square" size={36} fill="var(--m3e-color-primary-container)" />
              <span>{brandBadge}</span>
            </div>
            <div style={{ minInlineSize: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <h1 style={{ margin: 0, fontWeight: 700, fontSize: "1.02rem", color: "var(--studio-text)" }}>
                  {defaultTitle}
                </h1>
                {sys?.mock_mode && <Tag color="warning">{t("Mock Preview", "Mock 预览模式")}</Tag>}
                {tunnelMode === "quick" && (
                  <Tooltip
                    title={t(
                      "Using an ephemeral Cloudflare Quick Tunnel URL. This URL expires when Colab stops or restarts; select Custom Tunnel in Step 4 for a fixed domain.",
                      "当前使用 Cloudflare Quick Tunnel 免费临时公网链接，Colab 机器关闭或重启隧道后此地址即失效；如需固定域名请在部署第 4 步选择「自有 Tunnel」",
                    )}
                  >
                    <Tag color="warning" style={{ marginInlineEnd: 0 }}>
                      {t("Quick Tunnel (Ephemeral)", "Quick 临时链接（关机失效）")}
                    </Tag>
                  </Tooltip>
                )}
                {tunnelMode === "custom" && (
                  <Tooltip title={t(`Custom Cloudflare Tunnel domain: ${origin}`, `当前通过自有 Cloudflare Tunnel 固定域名访问：${origin}`)}>
                    <Tag color="success" style={{ marginInlineEnd: 0 }}>
                      {t("Custom Domain", "自有固定域名")}
                    </Tag>
                  </Tooltip>
                )}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--studio-text-muted)" }}>
                {defaultSubtitle ?? sys?.subtitle}
              </div>
            </div>
          </div>

          <div className="studio-header-actions">
            {headerExtra}

            {sys ? (
              <Popover
                placement="bottomRight"
                trigger={["hover", "click"]}
                content={telemetryPopoverContent}
              >
                <Button
                  htmlType="button"
                  size="small"
                  type="tonal"
                  className="studio-tabular"
                  icon={
                    <span
                      className="studio-telemetry-dot"
                      aria-hidden="true"
                      style={{ "--telemetry-dot-color": dotColor } as React.CSSProperties}
                    />
                  }
                  aria-label={t(
                    "View live CPU, RAM, GPU, and disk telemetry",
                    "查看机器 CPU、内存、GPU 与磁盘实时状态",
                  )}
                >
                  {sys.gpu.available
                    ? `${shortGpuLabel(sys.gpu.name)} ${sys.gpu.vram_used_gib.toFixed(0)}/${sys.gpu.vram_total_gib.toFixed(0)}G`
                    : `CPU${sys.host ? ` ${Math.round(sys.host.cpu_percent)}%` : ""}`}
                </Button>
              </Popover>
            ) : (
              <Badge status="error" text={t("Disconnected", "后端未连接")} />
            )}

            <Button
              htmlType="button"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => {
                setApiKeyInput(loadApiKey());
                setKeyModalOpen(true);
              }}
            >
              {sys?.api_key_configured ? t("API Key Set", "API Key 已设") : "API Key"}
            </Button>

            <Button
              htmlType="button"
              size="small"
              type="primary"
              icon={<ApiOutlined />}
              onClick={() => {
                setApiModalOpen(true);
              }}
            >
              {t("API Code", "API 调用代码")}
            </Button>

            <Tooltip title={locale === "zh" ? "Switch to English" : "切换为中文"}>
              <Button
                htmlType="button"
                size="small"
                icon={<GlobalOutlined />}
                aria-label={locale === "zh" ? "Switch language to English" : "切换语言为中文"}
                onClick={toggleLocale}
              >
                {locale === "zh" ? "中文" : "EN"}
              </Button>
            </Tooltip>

            <Tooltip title="GitHub · boltguo/colab">
              <IconButton
                className="studio-github-btn"
                icon={<GithubOutlined size={24} />}
                href="https://github.com/boltguo/colab"
                target="_blank"
                rel="noopener noreferrer"
                variant="standard"
                size="xs"
                aria-label={t("Open GitHub repository (boltguo/colab)", "打开 GitHub 仓库 (boltguo/colab)")}
              />
            </Tooltip>

            {sys?.browser_authenticated && (
              <form method="post" action="/auth/logout">
                <Button htmlType="submit" size="small" type="text">
                  {t("Sign out", "退出")}
                </Button>
              </form>
            )}
          </div>
        </div>
      </header>

      <main className="studio-main" data-layout={layoutRatio}>
        {topBanner && <div style={{ marginBlockEnd: "0.95rem" }}>{topBanner}</div>}
        <nav className="studio-mobile-nav" aria-label={t("Workspace sections", "工作区快速跳转")}>
          <a href={`#${controlsId}`}>
            {layoutRatio === "chat" ? t("Chat", "对话") : t("Parameters", "参数设置")}
          </a>
          <a href={`#${resultsId}`}>
            {layoutRatio === "chat" ? t("Settings", "参数设置") : t("Results & History", "结果与历史")}
          </a>
        </nav>
        <div className="studio-grid" data-layout={layoutRatio}>
          <section id={controlsId} className="studio-column" aria-label={t("Controls", "创作与生成设置")}>
            {leftPane}
          </section>
          <aside id={resultsId} className="studio-sticky-aside" aria-label={t("Results & History", "结果与历史")}>
            <ScrollArea className="studio-preview-scroll" maxHeight="var(--studio-preview-max-height)">
              <div className="studio-preview-content">{rightPane}</div>
            </ScrollArea>
          </aside>
        </div>
      </main>

      <Modal
        title={t("Configure API Key", "设置 API Key")}
        open={keyModalOpen}
        onCancel={() => setKeyModalOpen(false)}
        onOk={handleSaveKey}
        confirmLoading={savingKey}
        okText={t("Save", "保存")}
        cancelText={t("Cancel", "取消")}
      >
        <Space direction="vertical" size={14} style={{ inlineSize: "100%", paddingBlock: 8 }}>
          <Text>
            {t(
              "Used only for external API requests. Save empty to allow anonymous API calls.",
              "仅用于外部程序调用。留空保存后，API 可免鉴权调用。",
            )}
          </Text>

          <div className="studio-field-group">
            <label htmlFor="studio-api-key" className="studio-field-label">
              <span>Bearer API Key</span>
            </label>
            <Input.Password
              id="studio-api-key"
              name="api_key"
              allowClear
              placeholder={
                sys?.api_key_configured
                  ? t("Enter a new API key", "填写新的 API Key")
                  : t("At least 8 ASCII characters", "至少 8 位字母、数字或符号")
              }
              value={apiKeyInput}
              onValueChange={(value) => setApiKeyInput(value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  handleSaveKey();
                }
              }}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
            />
          </div>
          <Space wrap>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                const bytes = crypto.getRandomValues(new Uint8Array(24));
                setApiKeyInput(`sk-${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`);
              }}
            >
              {t("Generate Random", "随机生成")}
            </Button>
            <Button
              icon={<CopyOutlined />}
              disabled={!apiKeyInput}
              onClick={() => void copyText(apiKeyInput, t("API key copied", "API Key 已复制"))}
            >
              {t("Copy", "复制")}
            </Button>
          </Space>
          {sys?.api_key_configured && (
            <Text type="secondary">
              {t("Saving a new key invalidates the previous one immediately.", "保存新 Key 后，原 Key 立即失效。")}
            </Text>
          )}
        </Space>
      </Modal>

      <Dialog
        title={apiModalTitle || apiDrawerTitle || t("HTTP / WebSocket API Examples", "标准 HTTP / WebSocket API 调用示例")}
        open={apiModalOpen}
        onOpenChange={setApiModalOpen}
        showCloseButton
        className="studio-api-dialog"
        style={{ width: "min(1000px, calc(100vw - 48px))", maxWidth: "none" }}
      >
        <div className="studio-api-content">
          {tunnelMode === "quick" && (
            <Alert
              type="warning"
              showIcon
              message={t("Ephemeral Quick Tunnel Domain Active", "当前为 Quick Tunnel 临时公网域名")}
              description={t(
                "The snippets below already use the active tunnel URL. This address expires when the Colab instance stops; choose Custom Tunnel in Step 4 for a permanent URL.",
                "下方调用代码已自动填入当前临时链接。Colab 实例关闭或重启隧道后该链接即失效；如需固定 API 域名，请在 Colab 第 4 步选择「自有 Tunnel」。",
              )}
            />
          )}

          <div className="studio-api-address">
            <Space wrap size={6}>
              <Text strong style={{ fontSize: 13 }}>
                {t("Endpoint Base URL:", "当前服务调用地址：")}
              </Text>
              <Text code>{origin}</Text>
              {tunnelMode === "quick" && <Tag color="warning">{t("Ephemeral", "临时链接")}</Tag>}
              {tunnelMode === "custom" && <Tag color="success">{t("Custom Tunnel", "自有 Tunnel")}</Tag>}
            </Space>
            <Space size={8}>
              <Button
                type="link"
                size="small"
                icon={<BookOutlined />}
                href={`${origin}/docs`}
                target="_blank"
                rel="noreferrer"
              >
                {t("API Docs", "API 文档")}
              </Button>
              <Tooltip title={t("Copy Base URL", "复制服务地址")}>
                <Button
                  htmlType="button"
                  size="small"
                  icon={<CopyOutlined />}
                  aria-label={t("Copy Base URL", "复制服务地址")}
                  onClick={() => void copyText(origin, t("Base URL copied", "已复制当前服务地址"))}
                />
              </Tooltip>
            </Space>
          </div>

          <Text type="secondary" className="studio-api-guidance" style={{ fontSize: 13 }}>
            {t(
              "The examples below reflect your current server origin and Studio settings:",
              "下方代码已带入当前服务地址和页面设置，可直接复制运行：",
            )}
          </Text>

          <Tabs
            className="studio-api-tabs"
            items={
              customApiTabs
                ? customApiTabs({
                    origin,
                    savedKey,
                    authRequired: Boolean(sys?.auth_required),
                    copyText,
                  })
                : [
                    {
                      key: "python",
                      label: "Python",
                      icon: <CodeOutlined />,
                      children: <CodeBlock code={pythonSnippet} language="python" />,
                    },
                    {
                      key: "curl",
                      label: "cURL",
                      icon: <CodeOutlined />,
                      children: <CodeBlock code={curlSnippet} language="bash" />,
                    },
                  ]
            }
          />
        </div>
      </Dialog>
    </div>
  );
}
