import { useCallback, useEffect, useRef, useState } from "react";
import { cancelTaskById, submitFeatureTask, subscribeTaskProgress } from "../api/client";
import type { TaskRecord } from "../api/types";

export interface UseTaskRunnerOptions<TResult, TParams> {
  endpointPath?: string;
  onSuccess?: (task: TaskRecord<TResult, TParams>) => void;
  onError?: (errorMessage: string) => void;
}

export function useTaskRunner<
  TResult = Record<string, unknown>,
  TParams = Record<string, unknown>
>(options: UseTaskRunnerOptions<TResult, TParams> = {}) {
  const endpointPath = options.endpointPath || "/api/v1/generate";
  const [activeTask, setActiveTask] = useState<TaskRecord<TResult, TParams> | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const unsubRef = useRef<(() => void) | null>(null);
  const busyRef = useRef(false);
  const mountedRef = useRef(true);
  const generationRef = useRef(0);
  const onSuccessRef = useRef(options.onSuccess);
  const onErrorRef = useRef(options.onError);

  onSuccessRef.current = options.onSuccess;
  onErrorRef.current = options.onError;

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      if (unsubRef.current) {
        unsubRef.current();
        unsubRef.current = null;
      }
    };
  }, []);

  const runTask = useCallback(
    async (payload: TParams) => {
      // React state updates are asynchronous; a hotkey and click can arrive
      // before the button reflects the first request.
      if (busyRef.current) return null;
      busyRef.current = true;
      const generation = ++generationRef.current;
      if (unsubRef.current) {
        unsubRef.current();
        unsubRef.current = null;
      }
      setSubmitting(true);
      try {
        const initial = await submitFeatureTask<TResult, TParams>(endpointPath, payload);
        if (!mountedRef.current || generation !== generationRef.current) return null;
        setActiveTask(initial);

        let notified = false;
        let connectionErrorShown = false;
        unsubRef.current = subscribeTaskProgress<TResult, TParams>(
          initial.task_id,
          (updated) => {
            if (!mountedRef.current || generation !== generationRef.current) return;
            connectionErrorShown = false;
            setActiveTask(updated);
            if (["succeeded", "failed", "cancelled"].includes(updated.status)) {
              busyRef.current = false;
            }
            if (!notified && updated.status === "succeeded") {
              notified = true;
              onSuccessRef.current?.(updated);
            } else if (!notified && updated.status === "failed") {
              notified = true;
              onErrorRef.current?.(updated.error || "模型推理执行失败");
            }
          },
          (err) => {
            if (!notified && !connectionErrorShown && mountedRef.current && generation === generationRef.current) {
              connectionErrorShown = true;
              onErrorRef.current?.(err.message);
            }
          }
        );
        return initial;
      } catch (err) {
        busyRef.current = false;
        const msg = err instanceof Error ? err.message : String(err);
        if (mountedRef.current && generation === generationRef.current) onErrorRef.current?.(msg);
        return null;
      } finally {
        if (mountedRef.current && generation === generationRef.current) setSubmitting(false);
      }
    },
    [endpointPath]
  );

  const cancelActive = useCallback(async () => {
    if (!activeTask) return;
    const generation = generationRef.current;
    try {
      const cancelled = await cancelTaskById(activeTask.task_id);
      if (!mountedRef.current || generation !== generationRef.current) return;
      setActiveTask(cancelled as TaskRecord<TResult, TParams>);
      if (["succeeded", "failed", "cancelled"].includes(cancelled.status)) {
        busyRef.current = false;
      }
    } catch (err) {
      if (mountedRef.current && generation === generationRef.current) {
        onErrorRef.current?.(err instanceof Error ? err.message : String(err));
      }
    }
  }, [activeTask]);

  const isBusy =
    submitting ||
    activeTask?.status === "queued" ||
    activeTask?.status === "running";

  return {
    activeTask,
    submitting,
    isBusy,
    runTask,
    cancelActive,
    setActiveTask,
  };
}
