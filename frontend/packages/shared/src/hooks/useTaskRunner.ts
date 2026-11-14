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
  const onSuccessRef = useRef(options.onSuccess);
  const onErrorRef = useRef(options.onError);

  onSuccessRef.current = options.onSuccess;
  onErrorRef.current = options.onError;

  useEffect(() => {
    return () => {
      if (unsubRef.current) {
        unsubRef.current();
        unsubRef.current = null;
      }
    };
  }, []);

  const runTask = useCallback(
    async (payload: TParams) => {
      if (unsubRef.current) {
        unsubRef.current();
        unsubRef.current = null;
      }
      setSubmitting(true);
      try {
        const initial = await submitFeatureTask<TResult, TParams>(endpointPath, payload);
        setActiveTask(initial);

        let notified = false;
        unsubRef.current = subscribeTaskProgress<TResult, TParams>(
          initial.task_id,
          (updated) => {
            setActiveTask(updated);
            if (!notified && updated.status === "succeeded") {
              notified = true;
              onSuccessRef.current?.(updated);
            } else if (!notified && updated.status === "failed") {
              notified = true;
              onErrorRef.current?.(updated.error || "模型推理执行失败");
            }
          },
          (err) => {
            if (!notified) {
              onErrorRef.current?.(err.message);
            }
          }
        );
        return initial;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        onErrorRef.current?.(msg);
        throw err;
      } finally {
        setSubmitting(false);
      }
    },
    [endpointPath]
  );

  const cancelActive = useCallback(async () => {
    if (!activeTask) return;
    const cancelled = await cancelTaskById(activeTask.task_id);
    setActiveTask(cancelled as TaskRecord<TResult, TParams>);
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
