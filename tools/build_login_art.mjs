// Export one native m3eui Material shape for the server-rendered access page.
// Regenerate after changing the library version: node tools/build_login_art.mjs
import { createRequire } from "node:module";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const require = createRequire(new URL("../frontend/packages/shared/package.json", import.meta.url));
const tokenFile = require.resolve("m3eui/tokens.json");
const { getMaterialShape, cubicsToSvgPath } = await import(new URL("./tokens/index.js", pathToFileURL(tokenFile)));
const tokens = JSON.parse(await readFile(tokenFile, "utf8"));
const colors = tokens.themes.expressiveViolet.light;
const d = cubicsToSvgPath(getMaterialShape("softBurst").cubics, 64, 0.94);
await writeFile(new URL("../backend/core/login_art.svg", import.meta.url),
  `<!-- Composed from m3eui ${tokens.meta.version} MaterialShapeView geometry; see licenses/m3eui for attribution and Apache-2.0 license. -->\n` +
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" aria-hidden="true" focusable="false">\n` +
  `  <path d="${d}" fill="${colors.primary}"/>\n` +
  `  <g fill="none" stroke="${colors.onPrimary}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">\n` +
  `    <rect x="22" y="29" width="20" height="17" rx="3"/><path d="M26 29v-5a6 6 0 0 1 12 0v5M32 36v3"/>\n` +
  `  </g>\n</svg>\n`);
const licenseDir = new URL("../backend/core/licenses/m3eui/", import.meta.url);
await mkdir(licenseDir, { recursive: true });
for (const file of ["LICENSE", "NOTICE"]) {
  await copyFile(new URL(`../${file}`, pathToFileURL(tokenFile)), new URL(file, licenseDir));
}
