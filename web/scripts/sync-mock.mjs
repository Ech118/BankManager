// Copies the frozen ACME verdict into public/mock/ so the UI can be built and demoed with no backend.
// The fixture stays the single source of truth: public/mock/ is gitignored and regenerated on dev/build.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../fixtures/mock/verdict.json");
const dest = resolve(here, "../public/mock/verdict.json");
mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log(`synced ${src} -> ${dest}`);
