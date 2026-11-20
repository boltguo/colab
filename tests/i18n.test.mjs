import assert from "node:assert/strict";
import test from "node:test";
import {
  detectBrowserLocale,
  parseLocaleTag,
  resolveInitialLocale,
  toHtmlLang,
  toM3ELocale,
} from "../frontend/packages/shared/src/i18n/locale.ts";

test("parseLocaleTag normalizes English and Chinese BCP 47 tags", () => {
  assert.equal(parseLocaleTag("en"), "en");
  assert.equal(parseLocaleTag("en-US"), "en");
  assert.equal(parseLocaleTag(" ZH-cn "), "zh");
  assert.equal(parseLocaleTag("zh-Hant-TW"), "zh");
  assert.equal(parseLocaleTag("fr-FR"), null);
  assert.equal(parseLocaleTag(""), null);
});

test("detectBrowserLocale defaults to English and switches to Chinese for zh browsers", () => {
  assert.equal(detectBrowserLocale([], ""), "en");
  assert.equal(detectBrowserLocale(["fr-FR", "ja-JP"], "fr"), "en");
  assert.equal(detectBrowserLocale(["zh-CN", "en-US"], "zh-CN"), "zh");
  assert.equal(detectBrowserLocale(["zh-TW"], "en-US"), "zh");
  assert.equal(detectBrowserLocale(["en-US", "zh-CN"], "zh-CN"), "en");
});

test("resolveInitialLocale honors explicit stored override before browser detection", () => {
  assert.equal(
    resolveInitialLocale({ stored: "en", languages: ["zh-CN"], language: "zh-CN" }),
    "en",
  );
  assert.equal(
    resolveInitialLocale({ stored: "zh", languages: ["en-US"], language: "en-US" }),
    "zh",
  );
  assert.equal(
    resolveInitialLocale({ stored: "fr", languages: ["zh-CN"], language: "zh-CN" }),
    "zh",
  );
  assert.equal(
    resolveInitialLocale({ stored: null, languages: ["ja-JP"], language: "ja-JP" }),
    "en",
  );
  assert.equal(toM3ELocale("en"), "en-US");
  assert.equal(toM3ELocale("zh"), "zh-CN");
  assert.equal(toHtmlLang("en"), "en");
  assert.equal(toHtmlLang("zh"), "zh-CN");
});
