import assert from "node:assert/strict";
import test from "node:test";
import { fitImageScale, imageDownloadUrl } from "../frontend/packages/shared/src/utils/imageViewing.ts";

test("fit view fills the available area while preserving the complete image and its proportions", () => {
  for (const [width,height] of [[1536,2720],[4096,512],[2048,2048],[64,96]]) {
    const scale=fitImageScale(width,height,800,500);
    assert.ok(width*scale<=800+1e-8 && height*scale<=500+1e-8);
    assert.ok(scale>0);
    assert.ok(Math.abs(width*scale-800)<1e-8 || Math.abs(height*scale-500)<1e-8);
    assert.ok(Math.abs((width*scale)/(height*scale)-width/height)<1e-12);
  }
});

test("image downloads request the original attachment while retaining existing query params", () => {
  assert.equal(imageDownloadUrl("/api/v1/outputs/image.png"),"/api/v1/outputs/image.png?download=1");
  assert.equal(imageDownloadUrl("/api/v1/outputs/image.png?token=v2"),"/api/v1/outputs/image.png?token=v2&download=1");
});
