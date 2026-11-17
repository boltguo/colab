import assert from "node:assert/strict";
import test from "node:test";
import { configureApiKey, fetchSystemStatus, resolveApiUrl, saveApiKey } from "../frontend/packages/shared/src/api/client.ts";

test("browser requests use the session while configured API keys are only used in external snippets", async (t) => {
  const previousWindow = globalThis.window;
  const previousFetch = globalThis.fetch;
  const session = new Map();
  globalThis.window = {
    localStorage: { removeItem() {} },
    sessionStorage: { getItem: (key) => session.get(key), setItem: (key, value) => session.set(key, value), removeItem: (key) => session.delete(key) },
    dispatchEvent() {},
  };
  t.after(() => { globalThis.window = previousWindow; globalThis.fetch = previousFetch; });
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ configured: true }), { status: 200 });
  };
  saveApiKey("external-snippet-key");
  assert.equal(resolveApiUrl("/api/v1/outputs/photo.png", true), "/api/v1/outputs/photo.png");
  await fetchSystemStatus();
  assert.equal(calls[0].options.headers.Authorization, undefined);
  await configureApiKey("new-external-key");
  assert.equal(calls[1].url, "/auth/api-key");
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.headers.Authorization, undefined);
  assert.deepEqual(JSON.parse(calls[1].options.body), { api_key: "new-external-key" });
});
