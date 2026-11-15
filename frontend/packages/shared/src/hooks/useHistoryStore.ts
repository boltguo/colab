import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRecentTasks } from "../api/client";

export interface HistoryEntry<TResult = Record<string, unknown>, TParams = Record<string, unknown>> {
  id: string;
  feature: string;
  createdAt: string;
  elapsedSec?: number | null;
  params: TParams;
  result: TResult;
}

export function useHistoryStore<
  TResult = Record<string, unknown>,
  TParams = Record<string, unknown>
>(feature: string, maxItems = 50) {
  const [items, setItems] = useState<HistoryEntry<TResult, TParams>[]>([]);
  const hiddenRef = useRef(new Set<string>());
  const knownRef = useRef(new Set<string>());
  const loadedRef = useRef(false);
  const clearPendingRef = useRef(false);
  const storageKey = `colab_history_hidden:${feature}`;

  const persistHidden = useCallback(() => {
    try {
      window.sessionStorage.setItem(storageKey, JSON.stringify([...hiddenRef.current]));
    } catch {
      // Clearing history still works in memory if browser storage is disabled.
    }
  }, [storageKey]);

  useEffect(() => {
    let cancelled = false;
    hiddenRef.current = new Set();
    try {
      const saved: unknown = JSON.parse(window.sessionStorage.getItem(storageKey) || "[]");
      if (Array.isArray(saved)) hiddenRef.current = new Set(saved.filter((id): id is string => typeof id === "string"));
    } catch {
      // Use the server's current runtime history when local storage is unavailable.
    }

    const refresh = async () => {
      try {
        const tasks = await fetchRecentTasks<TResult, TParams>(100);
        if (cancelled) return;
        const recovered: HistoryEntry<TResult, TParams>[] = tasks
          .filter((task) => task.feature === feature && task.status === "succeeded" && task.result)
          .map((task) => ({
            id: task.task_id,
            feature,
            createdAt: task.created_at,
            elapsedSec: task.elapsed_sec,
            params: task.params,
            result: task.result!,
          }));
        recovered.forEach((entry) => knownRef.current.add(entry.id));
        if (clearPendingRef.current) {
          recovered.forEach((entry) => hiddenRef.current.add(entry.id));
          clearPendingRef.current = false;
          persistHidden();
        }
        loadedRef.current = true;
        setItems((previous) => {
          // Preserve a task that completed while the initial request was in flight.
          const merged = new Map(recovered.map((entry) => [entry.id, entry]));
          previous.forEach((entry) => merged.set(entry.id, entry));
          return [...merged.values()]
            .filter((entry) => !hiddenRef.current.has(entry.id))
            .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
            .slice(0, maxItems);
        });
      } catch {
        // A missing API key/offline runtime must not prevent using the workbench.
      }
    };
    void refresh();
    window.addEventListener("colab:auth-changed", refresh);
    return () => {
      cancelled = true;
      window.removeEventListener("colab:auth-changed", refresh);
    };
  }, [feature, maxItems, storageKey, persistHidden]);

  const addEntry = useCallback(
    (entry: HistoryEntry<TResult, TParams>) => {
      knownRef.current.add(entry.id);
      setItems((prev) => [entry, ...prev.filter((item) => item.id !== entry.id)].slice(0, maxItems));
    },
    [maxItems]
  );

  const removeEntry = useCallback((id: string) => {
    hiddenRef.current.add(id);
    persistHidden();
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, [persistHidden]);

  const clearAll = useCallback(() => {
    knownRef.current.forEach((id) => hiddenRef.current.add(id));
    items.forEach((item) => hiddenRef.current.add(item.id));
    clearPendingRef.current = !loadedRef.current;
    persistHidden();
    setItems([]);
  }, [items, persistHidden]);

  return { items, addEntry, removeEntry, clearAll };
}
