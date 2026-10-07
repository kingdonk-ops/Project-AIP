// Shared ESLint flat config for every TypeScript app and package (ARCH-03, ADR 0004).
//
// Boundaries: an app (apps/<name>) may import its own files and any package (packages/<name>,
// including the generated packages/api-client), never another app. A package may import its own
// files and other packages, never an app.
//
// Usage in apps/<name>/eslint.config.js:
//   import aip from "@aip/config-eslint";
//   export default [...aip];
import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import globals from "globals";
import { fileURLToPath } from "node:url";
import tseslint from "typescript-eslint";

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

/** TypeScript + boundaries. Apps append their own framework rules (React hooks etc.). */
export default tseslint.config(
  { ignores: ["**/dist/", "**/node_modules/", "**/coverage/"] },
  {
    files: SOURCE_FILES,
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
  },
  boundariesConfig,
);
