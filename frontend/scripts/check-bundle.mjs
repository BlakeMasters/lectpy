// Enforce the replay startup budget. Optional live chunks are intentionally lazy.
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const manifest = JSON.parse(await readFile(path.join(dist, ".vite/manifest.json"), "utf8"));
const seen = new Set();
const files = new Set();
function visit(key) {
  if (seen.has(key)) return;
  seen.add(key);
  const chunk = manifest[key];
  if (!chunk) throw new Error(`Missing manifest chunk: ${key}`);
  if (chunk.file.endsWith(".js")) files.add(chunk.file);
  for (const dependency of chunk.imports ?? []) visit(dependency);
}
for (const [key, chunk] of Object.entries(manifest)) {
  if (chunk.isEntry) visit(key);
}
if (!files.size) throw new Error("No startup JavaScript found in the production manifest");
const bytes = (await Promise.all([...files].map(async (file) => (
  await stat(path.join(dist, file))
).size))).reduce((sum, size) => sum + size, 0);
const limit = 250_000;
console.log(`Replay startup JavaScript: ${bytes.toLocaleString()} / ${limit.toLocaleString()} bytes`);
if (bytes > limit) {
  throw new Error("Replay startup budget exceeded. Load optional integrations dynamically.");
}
