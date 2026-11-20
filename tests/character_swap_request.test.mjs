import assert from "node:assert/strict";
import test from "node:test";
import {
  buildCharacterSwapRequest,
  computeSwapPreviewDimensions,
  estimateWindowCount,
  restoreCharacterSwapState,
} from "../frontend/apps/h3-character-swap/src/request.ts";
import { DEFAULT_SWAP_PARAMS } from "../frontend/apps/h3-character-swap/src/types.ts";

test("character swap request builder filters blank characters and formats clip ranges", () => {
  const req = buildCharacterSwapRequest({
    ...DEFAULT_SWAP_PARAMS,
    mode: "multi",
    source_video: "video-1",
    characters: [
      { image: "char-a", name: "", target_description: " left ", appearance_description: "   " },
      { image: "", name: "", target_description: "unused", appearance_description: "" },
      { image: "char-b", name: "", target_description: "", appearance_description: "" },
    ],
    clip_range_mode: "preview5s",
    resolution_tier: "736p",
    seed: 99,
  });

  assert.equal(req.characters.length, 2);
  assert.equal(req.characters[0].target_description, "left");
  assert.equal("appearance_description" in req.characters[0], false);
  assert.equal("name" in req.characters[0], false);
  assert.equal("target_description" in req.characters[1], false);
  assert.equal(req.start_time_sec, 0);
  assert.equal(req.duration_sec, 5);
  assert.equal(req.resolution_tier, "736p");
  assert.equal(req.seed, 99);
});

test("single character swap mode clamps both requests and restored history to 1 slot", () => {
  const req = buildCharacterSwapRequest({
    ...DEFAULT_SWAP_PARAMS,
    mode: "single",
    source_video: "video-1",
    characters: [
      { image: "char-primary", target_description: " center dancer " },
      { image: "char-extra", target_description: "second" },
    ],
  });
  assert.equal(req.characters.length, 1);
  assert.equal(req.characters[0].image, "char-primary");
  assert.equal(req.characters[0].target_description, "center dancer");

  const restored = restoreCharacterSwapState({
    mode: "single",
    source_video: "video-1",
    characters: [
      { image: "char-primary", target_description: "center" },
      { image: "char-second", target_description: "right" },
    ],
  });
  assert.equal(restored.mode, "single");
  assert.equal(restored.characters.length, 1);
  assert.equal(restored.characters[0].image, "char-primary");
});

test("character swap history restores custom clip range and ensures multi slots", () => {
  const restored = restoreCharacterSwapState({
    mode: "multi",
    source_video: "v.mp4",
    characters: [{ image: "only-one.png", name: "", target_description: "", appearance_description: "" }],
    prompt: "  bright light  ",
    guide_frames: [{ image: "g.png", frame_index: 12 }],
    resolution_tier: "480p",
    preserve_aspect: true,
    start_time_sec: 2.5,
    duration_sec: 8,
    keep_audio: false,
    seed: 7,
    output_format: "webm",
  });

  assert.equal(restored.clip_range_mode, "custom");
  assert.equal(restored.start_time_sec, 2.5);
  assert.equal(restored.duration_sec, 8);
  assert.equal(restored.characters.length, 2);
  assert.equal(restored.keep_audio, false);
  assert.equal(restored.output_format, "webm");
  assert.deepEqual(restored.guide_frames, [{ image: "g.png", frame_index: 12 }]);
});

test("canvas dimensions and window count estimates align with Viggle Remake backend math", () => {
  assert.deepEqual(computeSwapPreviewDimensions(1920, 1080, "480p", true), { width: 864, height: 480 });
  assert.deepEqual(computeSwapPreviewDimensions(1920, 1080, "480p", false), { width: 832, height: 480 });
  assert.equal(estimateWindowCount(5), 1);
  assert.equal(estimateWindowCount(12), 2);
});
