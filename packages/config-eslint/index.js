// Shared ESLint flat config for every TypeScript app and package (ARCH-03, ADR 0004).
//
// Boundaries: an app (apps/<name>) may import its own files and any package (packages/<name>,
// including the generated packages/api-client), never another app. A package may import its own
// files and other packages, never an app.
//
// Terms (TERMS-07): `aip/no-hardcoded-labels` rejects default dictionary texts (ITP, NCR, Variation)
// as JSX text or label-prop literals in every app and package that uses this config.
//
// Usage in apps/<name>/eslint.config.js:
//   import aip from "@aip/config-eslint";
//   export default [...aip];
import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import globals from "globals";
import { fileURLToPath } from "node:url";
import tseslint from "typescript-eslint";

import noHardcodedLabels from "./rules/no-hardcoded-labels.js";

/** The monorepo root, so element patterns match no matter which app runs `eslint .`. */
export const ROOT = fileURLToPath(new URL("../../", import.meta.url));

export const SOURCE_FILES = ["**/*.{js,mjs,cjs,jsx,ts,mts,cts,tsx}"];

export const boundariesConfig = {
  files: SOURCE_FILES,
  plugins: { boundaries },
  settings: {
    "boundaries/root-path": ROOT,
    "boundaries/elements": [
      { type: "app", pattern: "apps/*", partialMatch: false, capture: ["app"] },
      { type: "package", pattern: "packages/*", partialMatch: false, capture: ["package"] },
    ],
    "boundaries/include": ["apps/**/*", "packages/**/*"],
    "import/resolver": {
      node: { extensions: [".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"] },
    },
  },
  rules: {
    "boundaries/dependencies": [
      "error",
      {
        default: "disallow",
        policies: [
          // Anything may import a shared package.
          { allow: { to: { element: { type: "package" } } } },
          // An app may import its own files.
          {
            from: { element: { type: "app" } },
            allow: {
              to: { element: { type: "app", captured: { app: "{{ from.element.captured.app }}" } } },
            },
          },
          // A package may import its own files.
          {
            from: { element: { type: "package" } },
            allow: {
              to: {
                element: {
                  type: "package",
                  captured: { package: "{{ from.element.captured.package }}" },
                },
              },
            },
          },
        ],
      },
    ],
  },
};

export const termsConfig = {
  files: SOURCE_FILES,
  // Tests render components with sample labels; the rule guards shipped UI only.
  ignores: ["**/*.test.*", "**/__fixtures/**"],
  plugins: { aip: { rules: { "no-hardcoded-labels": noHardcodedLabels } } },
  rules: { "aip/no-hardcoded-labels": "error" },
};

/** TypeScript + boundaries + terms. Apps append their own framework rules (React hooks etc.). */
export default tseslint.config(
  { ignores: ["**/dist/", "**/node_modules/", "**/coverage/"] },
  {
    files: SOURCE_FILES,
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
  },
  boundariesConfig,
  termsConfig,
);
