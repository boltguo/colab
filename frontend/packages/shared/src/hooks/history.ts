/** Internal asset downloads share the task queue but are not generated media. */
export function isGenerationTask(task: { params: unknown; result?: unknown }): boolean {
  if (task.params && typeof task.params === "object" && "__task_kind__" in task.params) return false;
  return !(task.result && typeof task.result === "object" && "kind" in task.result && task.result.kind === "lora_download");
}
