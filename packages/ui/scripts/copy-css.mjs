// Copies the CSS entry points next to the compiled JS (tsc does not handle CSS).
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
mkdirSync(dist, { recursive: true });
copyFileSync(join(root, "src/tokens/tokens.css"), join(dist, "tokens.css"));
copyFileSync(join(root, "src/components/components.css"), join(dist, "styles.css"));
