// ESLint boundaries between apps and packages (ARCH-03, ADR 0004).
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

import { ESLint } from "eslint";

import { ROOT } from "../index.js";

const SHARED_CONFIG = path.join(ROOT, "packages/config-eslint/index.js");

/** Lint `code` as if it lived at `relPath` (repo-relative), with the shared config. */
async function boundaryErrors(relPath, code) {
  const ownerDir = path.join(ROOT, ...relPath.split("/").slice(0, 2));
  const eslint = new ESLint({ cwd: ownerDir, overrideConfigFile: SHARED_CONFIG });
  const [result] = await eslint.lintText(code, { filePath: path.join(ROOT, relPath) });
  return result.messages.filter((m) => m.ruleId?.startsWith("boundaries/"));
}

test("an app importing another app is a boundaries error", async () => {
  const errors = await boundaryErrors(
    "apps/portal/src/probe.ts",
    'import x from "../../web/src/main";\nexport default x;\n',
  );
  assert.equal(errors.length, 1, JSON.stringify(errors));
  assert.equal(errors[0].ruleId, "boundaries/dependencies");
});

test("an app importing its own files is allowed", async () => {
  const errors = await boundaryErrors(
    "apps/web/src/probe.ts",
    'import { router } from "./router";\nexport default router;\n',
  );
  assert.deepEqual(errors, []);
});

test("an app importing a package is allowed", async () => {
  const errors = await boundaryErrors(
    "apps/web/src/probe.ts",
    'import { ROOT } from "../../../packages/config-eslint/index.js";\nexport default ROOT;\n',
  );
  assert.deepEqual(errors, []);
});

test("a package importing an app is a boundaries error", async () => {
  const errors = await boundaryErrors(
    "packages/config-eslint/probe.js",
    'import x from "../../apps/web/src/router";\nexport default x;\n',
  );
  assert.equal(errors.length, 1, JSON.stringify(errors));
});

test("external modules stay allowed", async () => {
  const errors = await boundaryErrors(
    "apps/web/src/probe.ts",
    'import { StrictMode } from "react";\nexport default StrictMode;\n',
  );
  assert.deepEqual(errors, []);
});

test("pnpm --filter portal lint fails on a cross-app import", () => {
  const dir = path.join(ROOT, "apps/portal/src");
  const file = path.join(dir, "__boundaries_probe__.ts");
  mkdirSync(dir, { recursive: true });
  writeFileSync(file, 'import x from "../../web/src/main";\nexport default x;\n');
  try {
    const run = spawnSync("pnpm", ["--filter", "portal", "lint"], {
      cwd: ROOT,
      encoding: "utf8",
    });
    const out = `${run.stdout}${run.stderr}`;
    assert.notEqual(run.status, 0, out);
    assert.match(out, /boundaries\/dependencies/);
  } finally {
    rmSync(file);
  }
});
