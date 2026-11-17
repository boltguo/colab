import assert from "node:assert/strict";
import test from "node:test";
import { isGenerationTask } from "../frontend/packages/shared/src/hooks/history.ts";

test("LoRA download tasks never enter media history or preview restoration", () => {
  assert.equal(isGenerationTask({ params: { __task_kind__: "lora_download" }, result: { kind: "lora_download", lora: {} } }), false);
  assert.equal(isGenerationTask({ params: {}, result: { kind: "lora_download", lora: {} } }), false);
  assert.equal(isGenerationTask({ params: { seed: 123 }, result: { image_url: "/api/v1/outputs/test.png" } }), true);
  assert.equal(isGenerationTask({ params: {}, result: { audio_url: "/api/v1/outputs/test.wav" } }), true);
});
