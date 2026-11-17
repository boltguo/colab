import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_QWEN_IMAGE_PARAMS } from "../frontend/apps/qwen-image-2.1/src/types.ts";
import { buildStudioImageRequest } from "../frontend/apps/qwen-image-2.1/src/request.ts";
import { DEFAULT_MINIMAX_H3_PARAMS } from "../frontend/apps/minimax-h3/src/types.ts";
import { buildVideoStudioRequest } from "../frontend/apps/minimax-h3/src/request.ts";
import { DEFAULT_SEEDVR2_PARAMS } from "../frontend/apps/seedvr2/src/types.ts";
import { buildUpscaleStudioRequest } from "../frontend/apps/seedvr2/src/request.ts";

test("image requests retain common controls and ignore legacy engine overrides", () => {
  const request = buildStudioImageRequest({ ...DEFAULT_QWEN_IMAGE_PARAMS, mode: "t2i", batch_size: 3,
    steps: 32, seed: 12345, denoise: 0.3, sampler_name: "heun", kv_cache_dtype: "int4", release_vram_after: true,
    loras: [{ lora: "style.safetensors", strength_model: 0.7, apply_to_clip: true, strength_clip: 0.4, enabled: true }] }, ["stale.png"]);
  assert.equal(request.batch_size, 3);
  assert.equal(request.steps, 32);
  assert.equal(request.seed, 12345);
  assert.equal(request.denoise, 1);
  assert.deepEqual(request.reference_images, []);
  assert.equal(request.loras[0].apply_to_clip, false);
  assert.equal(request.loras[0].strength_clip, 1);
  for (const key of ["sampler_name", "kv_cache_dtype", "release_vram_after"]) assert.equal(key in request, false);
});

test("video defaults ignore removed guide/codec tuning and preserve audible native FPS", () => {
  const request = buildVideoStudioRequest({ ...DEFAULT_MINIMAX_H3_PARAMS, output_format: "webm", fps: 12,
    soundtrack_enabled: true, steps: 8, seed: 19, guide_audio: "legacy.wav", crf: 0, frame_count: 362 });
  assert.equal(request.video_codec, "av1");
  assert.equal(request.fps, 24);
  assert.equal(request.steps, 8);
  assert.equal(request.seed, 19);
  for (const key of ["guide_audio", "crf", "frame_count", "sampler_name"]) assert.equal(key in request, false);
});

test("upscaling uses automatic model chunking without restoring legacy trimming or playback changes", () => {
  const fast = buildUpscaleStudioRequest({ ...DEFAULT_SEEDVR2_PARAMS, model_variant: "3b_fast", trim_video: true,
    fps_override: 48, color_correction: "none", keep_audio: false, steps: 2, seed: 23 }, " input.mp4 ");
  assert.equal(fast.split_latent, true);
  assert.equal(fast.input_file, "input.mp4");
  assert.equal(fast.keep_audio, false);
  assert.equal(fast.steps, 2);
  assert.equal(fast.seed, 23);
  assert.equal(buildUpscaleStudioRequest({ ...DEFAULT_SEEDVR2_PARAMS, mode: "image", model_variant: "3b_fast" }).split_latent, false);
  for (const key of ["trim_video", "fps_override", "color_correction", "vae_tile_size"]) assert.equal(key in fast, false);
});
