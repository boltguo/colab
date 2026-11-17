export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type TunnelMode = "local" | "quick" | "custom";

export interface GpuStats {
  available: boolean;
  name: string;
  utilization_pct?: number | null;
  vram_total_gib: number;
  vram_used_gib: number;
  vram_free_gib: number;
  vram_percent?: number;
  torch_allocated_gib?: number | null;
  torch_reserved_gib?: number | null;
  temperature_c?: number | null;
  power_draw_w?: number | null;
  power_limit_w?: number | null;
  bf16_supported: boolean;
  torch_version: string;
  cuda_version: string;
}

export interface HostStats {
  cpu_count: number;
  cpu_percent: number;
  load_avg_1m?: number | null;
  ram_total_gib: number;
  ram_used_gib: number;
  ram_free_gib: number;
  ram_percent: number;
  disk_mount: string;
  disk_total_gib: number;
  disk_used_gib: number;
  disk_free_gib: number;
  disk_percent: number;
  uptime_sec: number;
}

export interface QueueStats {
  running: number;
  queued: number;
  succeeded: number;
  failed: number;
}

export interface SystemStatus {
  feature: string;
  title: string;
  subtitle: string;
  version: string;
  engine: string;
  auth_required: boolean;
  browser_authenticated?: boolean;
  mock_mode: boolean;
  public_url?: string;
  tunnel_mode?: TunnelMode;
  gpu: GpuStats;
  host?: HostStats;
  queue: QueueStats;
}

export interface PresetItem {
  id: string;
  label: string;
  description: string;
  kind: "audio" | "image" | "video";
  url: string;
  filename: string;
}

export interface UploadedFileInfo {
  file_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  url: string;
  created_at: string;
}

export interface TaskRecord<TResult = Record<string, unknown>, TParams = Record<string, unknown>> {
  task_id: string;
  feature: string;
  status: TaskStatus;
  progress: number;
  stage: string;
  queue_position: number;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_sec?: number | null;
  params: TParams;
  result?: TResult | null;
  error?: string | null;
}

export interface AuthConfig {
  apiKey: string;
}

export interface LoraCatalogEntry {
  id: string;
  filename: string;
  label: string;
  description: string;
  installed: boolean;
  curated: boolean;
  size_bytes?: number | null;
  recommended_strength: number;
  trigger_words: string[];
  tags: string[];
  source_hint: string;
}

export interface LoraListResponse {
  loras_dir: string;
  free_disk_gb: number;
  total_disk_gb: number;
  items: LoraCatalogEntry[];
}

export interface LoraDownloadPayload {
  source: string;
  filename?: string;
  revision?: string;
  token?: string;
}

export interface LoraSlotConfig {
  lora: string;
  strength_model: number;
  apply_to_clip: boolean;
  strength_clip: number;
  enabled: boolean;
  token?: string;
}
