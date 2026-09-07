// Copies the latest v0.1 trace bundle into the shell's dev fixture so
// `npm run dev` works out of the box:  lecture build ... && npm run dev:sample
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "..", "dist", "lecture_01", "lecture.json");
const dest = join(root, "public", "sample", "lecture.json");
mkdirSync(dirname(dest), { recursive: true });
try {
  copyFileSync(src, dest);
  console.log(`sample bundle: ${src} -> ${dest}`);
} catch (e) {
  console.error(`copy-sample: build a bundle first (lecture build examples/lecture_01.py --out dist/lecture_01): ${e}`);
  process.exitCode = 1;
}
