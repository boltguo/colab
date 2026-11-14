import { useCallback, useEffect, useState } from "react";

export interface HistoryEntry<TResult = Record<string, unknown>, TParams = Record<string, unknown>> {
  id: string;
  feature: string;
  createdAt: string;
  elapsedSec?: number | null;
  params: TParams;
  result: TResult;
}

const DB_NAME = "colab_studio_db";
const DB_VERSION = 1;
const STORE_NAME = "history_items";

function openHistoryDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB unavailable"));
      return;
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("by_feature", "feature", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("IndexedDB open error"));
  });
}

export function useHistoryStore<
  TResult = Record<string, unknown>,
  TParams = Record<string, unknown>
>(feature: string, maxItems = 50) {
  const [items, setItems] = useState<HistoryEntry<TResult, TParams>[]>([]);

  useEffect(() => {
    let cancelled = false;
    openHistoryDb()
      .then((db) => {
        const tx = db.transaction(STORE_NAME, "readonly");
        const store = tx.objectStore(STORE_NAME);
        const idx = store.index("by_feature");
        const req = idx.getAll(feature);
        req.onsuccess = () => {
          if (cancelled) return;
          const list = (req.result as HistoryEntry<TResult, TParams>[]) || [];
          list.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
          setItems(list.slice(0, maxItems));
        };
      })
      .catch(() => {
        // Fallback to in-memory list when IndexedDB is blocked
      });
    return () => {
      cancelled = true;
    };
  }, [feature, maxItems]);

  const addEntry = useCallback(
    (entry: HistoryEntry<TResult, TParams>) => {
      setItems((prev) => [entry, ...prev.filter((x) => x.id !== entry.id)].slice(0, maxItems));
      openHistoryDb()
        .then((db) => {
          const tx = db.transaction(STORE_NAME, "readwrite");
          tx.objectStore(STORE_NAME).put(entry);
        })
        .catch(() => {});
    },
    [maxItems]
  );

  const removeEntry = useCallback((id: string) => {
    setItems((prev) => prev.filter((x) => x.id !== id));
    openHistoryDb()
      .then((db) => {
        const tx = db.transaction(STORE_NAME, "readwrite");
        tx.objectStore(STORE_NAME).delete(id);
      })
      .catch(() => {});
  }, []);

  const clearAll = useCallback(() => {
    setItems((prev) => {
      openHistoryDb()
        .then((db) => {
          const tx = db.transaction(STORE_NAME, "readwrite");
          const store = tx.objectStore(STORE_NAME);
          for (const item of prev) {
            store.delete(item.id);
          }
        })
        .catch(() => {});
      return [];
    });
  }, []);

  return {
    items,
    addEntry,
    removeEntry,
    clearAll,
  };
}
