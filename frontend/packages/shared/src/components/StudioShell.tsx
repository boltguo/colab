import React, { useCallback, useEffect, useId, useState } from "react";
import { fetchSystemStatus } from "../api/client";
import { useStudioLocale } from "../i18n";
import type { AccessMode, SystemStatus } from "../api/types";
import {
  Alert,
  Badge,
  Button,
  CloudServerOutlined,
  DashboardOutlined,
  GithubOutlined,
  GlobalOutlined,
  IconButton,
  MaterialShapeView,
  Meter,
  Popover,
  ReloadOutlined,
  ScrollArea,
  Space,
  Tag,
  Text,
  Tooltip,
} from "../ui/primitives";

export interface StudioShellProps {
  brandBadge?: string;
  defaultTitle: string;
  defaultSubtitle?: string;
  layoutRatio?: "default" | "chat";
  headerExtra?: React.ReactNode;
  topBanner?: React.ReactNode;
  leftPane: React.ReactNode;
  rightPane: React.ReactNode;
}

function detectAccessMode(sys: SystemStatus | null): AccessMode {
  if (sys?.access_mode === "colab") {
    return "colab";
  }
  if (typeof window !== "undefined") {
    const host = window.location.hostname.toLowerCase();
    if (host.endsWith(".colab.dev") || host.endsWith(".colab.googleusercontent.com")) {
      return "colab";
    }
  }
  return sys?.access_mode || "local";
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
  layoutRatio = "default",
  headerExtra,
  topBanner,
  leftPane,
  rightPane,
}: StudioShellProps) {
  const { locale, toggleLocale, t } = useStudioLocale();
  const gpuUtilBarId = useId();
  const vramBarId = useId();
  const cpuBarId = useId();
  const ramBarId = useId();
  const diskBarId = useId();
  const controlsId = useId();
  const resultsId = useId();

  const [sys, setSys] = useState<SystemStatus | null>(null);
  const [refreshingSys, setRefreshingSys] = useState(false);

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

  const accessMode = detectAccessMode(sys);

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
                {accessMode === "colab" && (
                  <Tooltip
                    title={t(
                      "Using Google Colab's native proxy bound to your signed-in Google account. This URL expires when the Colab runtime stops.",
                      "当前通过 Google Colab 原生内置代理访问，仅绑定当前登录的 Google 账号；实例关闭后此地址即失效",
                    )}
                  >
                    <Tag color="processing" style={{ marginInlineEnd: 0 }}>
                      {t("Colab Proxy (Ephemeral)", "Colab 内置代理（临时）")}
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
    </div>
  );
}
