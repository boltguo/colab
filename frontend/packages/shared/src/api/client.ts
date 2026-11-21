import type {
  LoraCatalogEntry,
  LoraDownloadPayload,
  LoraListResponse,
  PresetItem,
  SystemStatus,
  TaskRecord,
  UploadedFileInfo,
} from "./types";

export function resolveApiUrl(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

async function parseJsonOrThrow<T>(resp: Response): Promise<T> {
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
  const resp = await fetch(resolveApiUrl("/api/v1/system"));
  return parseJsonOrThrow<SystemStatus>(resp);
}

export async function fetchPresets(): Promise<PresetItem[]> {
  const resp = await fetch(resolveApiUrl("/api/v1/presets"));
  return parseJsonOrThrow<PresetItem[]>(resp);
}

export async function uploadMediaFile(file: File): Promise<UploadedFileInfo> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(resolveApiUrl("/api/v1/files"), {
    method: "POST",
    body: form,
  });
  return parseJsonOrThrow<UploadedFileInfo>(resp);
}

export async function fetchLoraCatalog(): Promise<LoraListResponse> {
  const resp = await fetch(resolveApiUrl("/api/v1/loras"));
  return parseJsonOrThrow<LoraListResponse>(resp);
}

export async function submitLoraDownloadTask(
  payload: LoraDownloadPayload
): Promise<TaskRecord<{ kind: string; lora: LoraCatalogEntry }>> {
  const resp = await fetch(resolveApiUrl("/api/v1/loras/download"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<TaskRecord<{ kind: string; lora: LoraCatalogEntry }>>(resp);
}

export async function uploadLoraSafetensors(file: File): Promise<LoraCatalogEntry> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch(resolveApiUrl("/api/v1/loras/upload"), {
    method: "POST",
    body: form,
  });
  return parseJsonOrThrow<LoraCatalogEntry>(resp);
}

export async function deleteCachedLora(filename: string): Promise<{ deleted: string; freed_bytes: number }> {
  const resp = await fetch(resolveApiUrl(`/api/v1/loras/${encodeURIComponent(filename)}`), {
    method: "DELETE",
  });
  return parseJsonOrThrow<{ deleted: string; freed_bytes: number }>(resp);
}

export async function submitFeatureTask<TResult = Record<string, unknown>, TParams = Record<string, unknown>>(
  endpointPath: string,
  payload: TParams
): Promise<TaskRecord<TResult, TParams>> {
  const resp = await fetch(resolveApiUrl(endpointPath), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJsonOrThrow<TaskRecord<TResult, TParams>>(resp);
}

export async function fetchTaskStatus<TResult = Record<string, unknown>, TParams = Record<string, unknown>>(
  taskId: string
): Promise<TaskRecord<TResult, TParams>> {
  const resp = await fetch(resolveApiUrl(`/api/v1/tasks/${encodeURIComponent(taskId)}`));
  return parseJsonOrThrow<TaskRecord<TResult, TParams>>(resp);
}

export async function fetchRecentTasks<TResult, TParams>(limit = 50): Promise<TaskRecord<TResult, TParams>[]> {
  const resp = await fetch(resolveApiUrl(`/api/v1/tasks?limit=${Math.min(100, Math.max(1, limit))}`));
  const data = await parseJsonOrThrow<{ items: TaskRecord<TResult, TParams>[] }>(resp);
  return data.items;
}

export async function cancelTaskById(taskId: string): Promise<TaskRecord> {
  const resp = await fetch(resolveApiUrl(`/api/v1/tasks/${encodeURIComponent(taskId)}`), {
    method: "DELETE",
  });
  return parseJsonOrThrow<TaskRecord>(resp);
}

export async function triggerModelRelease(): Promise<{ status: string; released_instances?: number }> {
  const resp = await fetch(resolveApiUrl("/api/v1/model/release"), {
    method: "POST",
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
