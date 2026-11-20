import type {
  LoraCatalogEntry,
  LoraDownloadPayload,
  LoraListResponse,
  PresetItem,
  SystemStatus,
  TaskRecord,
  UploadedFileInfo,
} from "./types";

const LEGACY_BASE_URL_KEY = "colab_studio_base_url";
const STORAGE_API_KEY = "colab_studio_snippet_key";

export function loadApiKey(): string {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    window.localStorage.removeItem(LEGACY_BASE_URL_KEY);
    window.localStorage.removeItem("colab_studio_api_key");
    return (window.sessionStorage.getItem(STORAGE_API_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function saveApiKey(rawKey: string): string {
  const cleanKey = rawKey.trim();
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(LEGACY_BASE_URL_KEY);
      window.localStorage.removeItem("colab_studio_api_key");
      if (cleanKey) {
        window.sessionStorage.setItem(STORAGE_API_KEY, cleanKey);
      } else {
        window.sessionStorage.removeItem(STORAGE_API_KEY);
      }
    } catch {
      // ignore storage errors
    }
    window.dispatchEvent(new Event("colab:auth-changed"));
  }
  return cleanKey;
}

/**
 * Returns the active public/tunnel origin to display in API call snippets.
 * Same-origin deployment: uses browser's current tunnel domain when accessed via tunnel,
 * or falls back to backend-reported tunnel `public_url` if accessed via localhost proxy.
 */
export function getEffectiveOrigin(sysPublicUrl?: string): string {
  const cleanSysUrl = (sysPublicUrl || "").trim().replace(/\/+$/, "");
  if (typeof window !== "undefined") {
    const host = window.location.hostname.toLowerCase();
    const isLocalHost = host === "127.0.0.1" || host === "localhost" || host === "::1";
    if (!isLocalHost) {
      return window.location.origin;
    }
    if (cleanSysUrl && !cleanSysUrl.includes("<")) {
      return cleanSysUrl;
    }
    return window.location.origin;
  }
  return cleanSysUrl && !cleanSysUrl.includes("<") ? cleanSysUrl : "http://127.0.0.1:8188";
}

export function resolveApiUrl(path: string, _includeAuthQuery = false): string {
  return path.startsWith("/") ? path : `/${path}`;
}

function buildAuthHeaders(extra?: Record<string, string>): Record<string, string> {
  return { ...(extra || {}) };
}

async function parseJsonOrThrow<T>(resp: Response): Promise<T> {
  if (resp.status === 401 && resp.headers.get("X-Colab-Login-Required") && typeof window !== "undefined") {
    window.location.assign("/auth/login");
  }
  if (!resp.ok) {
    let detail = `Request failed (HTTP ${resp.status})`;
    try {
      const data = await resp.json();
      if (typeof data?.detail === "string") {
        detail = data.detail;
      } else if (Array.isArray(data?.detail)) {
        detail = data.detail.map((item: { msg?: string }) => item?.msg || JSON.stringify(item)).join("; ");
      }
    } catch {
      // ignore non-json body
    }
    throw new Error(detail);
  }
  return (await resp.json()) as T;
}

export async function fetchSystemStatus(): Promise<SystemStatus> {
  const resp = await fetch(resolveApiUrl("/api/v1/system"), {
    headers: buildAuthHeaders(),
  });
  return parseJsonOrThrow<SystemStatus>(resp);
}

export async function configureApiKey(key: string): Promise<void> {
  const resp = await fetch("/auth/api-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: key }),
  });
  await parseJsonOrThrow<{ configured: boolean }>(resp);
}

export async function fetchPresets(): Promise<PresetItem[]> {
  const resp = await fetch(resolveApiUrl("/api/v1/presets"), {
    headers: buildAuthHeaders(),
  });
  return parseJsonOrThrow<PresetItem[]>(resp);
}

export async function uploadMediaFile(file: File): Promise<UploadedFileInfo> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(resolveApiUrl("/api/v1/files"), {
    method: "POST",
    headers: buildAuthHeaders(),
    body: form,
  });
  return parseJsonOrThrow<UploadedFileInfo>(resp);
}

export async function fetchLoraCatalog(): Promise<LoraListResponse> {
  const resp = await fetch(resolveApiUrl("/api/v1/loras"), {
    headers: buildAuthHeaders(),
  });
  return parseJsonOrThrow<LoraListResponse>(resp);
}

export async function submitLoraDownloadTask(
  payload: LoraDownloadPayload
): Promise<TaskRecord<{ kind: string; lora: LoraCatalogEntry }>> {
  const resp = await fetch(resolveApiUrl("/api/v1/loras/download"), {
    method: "POST",
    headers: buildAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<TaskRecord<{ kind: string; lora: LoraCatalogEntry }>>(resp);
}

export async function uploadLoraSafetensors(file: File): Promise<LoraCatalogEntry> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(resolveApiUrl("/api/v1/loras/upload"), {
    method: "POST",
    headers: buildAuthHeaders(),
    body: form,
  });
  return parseJsonOrThrow<LoraCatalogEntry>(resp);
}

export async function deleteCachedLora(filename: string): Promise<{ deleted: string; freed_bytes: number }> {
  const resp = await fetch(resolveApiUrl(`/api/v1/loras/${encodeURIComponent(filename)}`), {
    method: "DELETE",
    headers: buildAuthHeaders(),
  });
  return parseJsonOrThrow<{ deleted: string; freed_bytes: number }>(resp);
}

export async function submitFeatureTask<TResult = Record<string, unknown>, TParams = Record<string, unknown>>(
  endpointPath: string,
  payload: TParams
): Promise<TaskRecord<TResult, TParams>> {
  const resp = await fetch(resolveApiUrl(endpointPath), {
    method: "POST",
    headers: buildAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<TaskRecord<TResult, TParams>>(resp);
}

export async function fetchTaskStatus<TResult = Record<string, unknown>, TParams = Record<string, unknown>>(
  taskId: string
): Promise<TaskRecord<TResult, TParams>> {
  const resp = await fetch(resolveApiUrl(`/api/v1/tasks/${encodeURIComponent(taskId)}`), {
    headers: buildAuthHeaders(),
  });
  return parseJsonOrThrow<TaskRecord<TResult, TParams>>(resp);
}

export async function fetchRecentTasks<TResult, TParams>(limit = 50): Promise<TaskRecord<TResult, TParams>[]> {
  const resp = await fetch(resolveApiUrl(`/api/v1/tasks?limit=${Math.min(100, Math.max(1, limit))}`), {
    headers: buildAuthHeaders(),
  });
  const data = await parseJsonOrThrow<{ items: TaskRecord<TResult, TParams>[] }>(resp);
  return data.items;
}

export async function cancelTaskById(taskId: string): Promise<TaskRecord> {
  const resp = await fetch(resolveApiUrl(`/api/v1/tasks/${encodeURIComponent(taskId)}`), {
    method: "DELETE",
    headers: buildAuthHeaders(),
  });
  return parseJsonOrThrow<TaskRecord>(resp);
}

export async function triggerModelRelease(): Promise<{ status: string; released_instances?: number }> {
  const resp = await fetch(resolveApiUrl("/api/v1/model/release"), {
    method: "POST",
    headers: buildAuthHeaders(),
  });
  return parseJsonOrThrow(resp);
}

export function subscribeTaskProgress<TResult = Record<string, unknown>, TParams = Record<string, unknown>>(
  taskId: string,
  onUpdate: (task: TaskRecord<TResult, TParams>) => void,
  onError?: (err: Error) => void
): () => void {
  let closed = false;
  let ws: WebSocket | null = null;
  let pollTimer: number | null = null;
  let pollInFlight = false;

  const stopAll = () => {
    closed = true;
    if (ws) {
      try {
        ws.close();
      } catch {
        // ignore
      }
      ws = null;
    }
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  };

  const startPollingFallback = () => {
    if (closed || pollTimer !== null) return;
    const pollOnce = async () => {
      if (closed || pollInFlight) return;
      pollInFlight = true;
      try {
        const snapshot = await fetchTaskStatus<TResult, TParams>(taskId);
        if (closed) return;
        onUpdate(snapshot);
        if (["succeeded", "failed", "cancelled"].includes(snapshot.status)) {
          stopAll();
        }
      } catch (err) {
        if (!closed && onError) {
          onError(err instanceof Error ? err : new Error(String(err)));
        }
      } finally {
        pollInFlight = false;
      }
    };
    void pollOnce();
    pollTimer = window.setInterval(pollOnce, 1000);
  };

  try {
    const sameOrigin = typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:8188";
    const wsOrigin = sameOrigin.replace(/^http:/i, "ws:").replace(/^https:/i, "wss:");
    const wsUrl = `${wsOrigin}/api/v1/tasks/${encodeURIComponent(taskId)}/ws`;

    ws = new WebSocket(wsUrl);
    ws.onmessage = (ev) => {
      if (closed) return;
      try {
        const parsed = JSON.parse(ev.data);
        if (parsed?.type === "ping") return;
        if (parsed?.task_id) {
          onUpdate(parsed as TaskRecord<TResult, TParams>);
          if (["succeeded", "failed", "cancelled"].includes(parsed.status)) {
            stopAll();
          }
        }
      } catch {
        // ignore malformed frame
      }
    };
    ws.onerror = () => {
      startPollingFallback();
    };
    ws.onclose = () => {
      if (!closed) {
        startPollingFallback();
      }
    };
  } catch {
    startPollingFallback();
  }

  return stopAll;
}
