// Export m3eui's native Material shapes for the server-rendered access page.
// Regenerate after changing the library version: node tools/build_login_art.mjs
import { createRequire } from "node:module";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const require = createRequire(new URL("../frontend/packages/shared/package.json", import.meta.url));
const tokenFile = require.resolve("m3eui/tokens.json");
const { getMaterialShape, cubicsToSvgPath } = await import(new URL("./tokens/index.js", pathToFileURL(tokenFile)));
const tokens = JSON.parse(await readFile(tokenFile, "utf8"));
const colors = tokens.themes.expressiveViolet.light;
const shapes = [
  ["softBurst", 228, 18, 18, "primary", -10],
  ["clover4Leaf", 180, 278, 24, "tertiaryContainer", 12],
  ["cookie12Sided", 110, 62, 314, "tertiary", -8],
  ["pill", 204, 246, 256, "secondaryContainer", 35],
];
const paths = shapes.map(([name, size, x, y, role, angle]) => {
  const d = cubicsToSvgPath(getMaterialShape(name).cubics, size, 0.88);
  return `  <g transform="translate(${x} ${y})"><path transform="rotate(${angle} ${size / 2} ${size / 2})" d="${d}" fill="${colors[role]}"/></g>`;
});
await writeFile(new URL("../backend/core/login_art.svg", import.meta.url),
  `<!-- Composed from m3eui ${tokens.meta.version} MaterialShapeView geometry; see licenses/m3eui for attribution and Apache-2.0 license. -->\n` +
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 480" aria-hidden="true" focusable="false">\n${paths.join("\n")}\n</svg>\n`);
const licenseDir = new URL("../backend/core/licenses/m3eui/", import.meta.url);
await mkdir(licenseDir, { recursive: true });
for (const file of ["LICENSE", "NOTICE"]) {
  await copyFile(new URL(`../${file}`, pathToFileURL(tokenFile)), new URL(file, licenseDir));
}
