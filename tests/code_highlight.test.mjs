import assert from "node:assert/strict";
import test from "node:test";
import { highlightCode } from "../frontend/packages/shared/src/utils/highlightCode.ts";

const textOf = (tokens) => tokens.map((line) => line.map((token) => token.content).join("")).join("\n");

test("Shiki highlights API and streaming code without changing source text", async () => {
  const examples = [
    ["py", 'print("你好 <script>")\n# comment\nvalue = "unfinished'],
    ["json", '{"seed": 1659226686848892, "prompt": "<image1>"}'],
    ["sh", 'curl "http://localhost:8188/api/v1/tasks" \\\n  -H "Content-Type: application/json"'],
  ];
  await Promise.all(examples.map(async ([lang, code]) => {
    const tokens = await highlightCode(code, lang);
    assert.ok(tokens);
    assert.equal(textOf(tokens), code);
    assert.ok(new Set(tokens.flat().map((token) => token.color)).size > 1);
  }));
});

test("Unknown code languages fall back to plain text", async () => {
  assert.equal(await highlightCode("anything", "not-a-language"), null);
  assert.equal(await highlightCode("anything", "constructor"), null);
});
