import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_QWEN_IMAGE_PARAMS, editImageGeometry } from "../frontend/apps/qwen-image-2.1/src/types.ts";

const original = {
  ...DEFAULT_QWEN_IMAGE_PARAMS,
  mode: "img2img",
  prompt: "编辑 <image1>",
  reference_images: ["reference.png"],
  resolution_tier: "original",
  aspect_ratio: "match_input",
  width: 1536,
  height: 2048,
};

for (const [label, width, height] of [
  ["选择自定义比例", 1536, 2048],
  ["手动修改宽度", 1024, 2048],
  ["手动修改高度", 1536, 1024],
  ["互换宽高", 2048, 1536],
]) {
  test(`原图分辨率后${label}仍产生可提交的参数`, () => {
    const next = editImageGeometry(original, width, height);
    assert.equal(next.resolution_tier, "2K");
    assert.equal(next.aspect_ratio, "custom");
    assert.equal(next.width, width);
    assert.equal(next.height, height);
    assert.deepEqual(next.reference_images, original.reference_images);
    assert.equal(next.prompt, original.prompt);
    assert.equal(original.resolution_tier, "original");
  });
}

test("1K自定义尺寸保留现有参考编码档位", () => {
  const next = editImageGeometry({ ...original, resolution_tier: "1K" }, 1024, 768);
  assert.equal(next.resolution_tier, "1K");
});
