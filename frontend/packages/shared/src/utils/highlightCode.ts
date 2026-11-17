import { createHighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";

const languages = {
  python: () => import("shiki/langs/python.mjs"),
  bash: () => import("shiki/langs/bash.mjs"),
  json: () => import("shiki/langs/json.mjs"),
  javascript: () => import("shiki/langs/javascript.mjs"),
  typescript: () => import("shiki/langs/typescript.mjs"),
  jsx: () => import("shiki/langs/jsx.mjs"),
  tsx: () => import("shiki/langs/tsx.mjs"),
  html: () => import("shiki/langs/html.mjs"),
  css: () => import("shiki/langs/css.mjs"),
  yaml: () => import("shiki/langs/yaml.mjs"),
  sql: () => import("shiki/langs/sql.mjs"),
};
const aliases: Record<string, string> = { py: "python", sh: "bash", shell: "bash", shellscript: "bash", zsh: "bash", js: "javascript", ts: "typescript", yml: "yaml", xml: "html" };
let highlighter: ReturnType<typeof createHighlighterCore> | undefined;
const loadedLanguages = new Map<string, Promise<void>>();

export async function highlightCode(code: string, language: string) {
  const lang = aliases[language.toLowerCase()] || language.toLowerCase();
  if (!Object.hasOwn(languages, lang)) return null;
  const load = languages[lang as keyof typeof languages];
  highlighter ??= createHighlighterCore({
    themes: [import("shiki/themes/github-light.mjs")],
    langs: [],
    engine: createJavaScriptRegexEngine(),
  });
  const instance = await highlighter;
  if (!loadedLanguages.has(lang)) {
    loadedLanguages.set(lang, load().then((grammar) => instance.loadLanguage(grammar.default)));
  }
  await loadedLanguages.get(lang);
  return instance.codeToTokens(code, { lang, theme: "github-light" }).tokens;
}
