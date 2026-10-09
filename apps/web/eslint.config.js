// ESLint flat config for apps/web (DESIGN-02): the shared ARCH-03 boundaries config (which already
// carries the TypeScript and JS recommended rules), plus jsx-a11y (recommended, as errors), the
// React hooks rules and a no-literal-text rule for the shell UI. Mirrors packages/ui/eslint.config.mjs.
import aip from "@aip/config-eslint";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  ...aip,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "jsx-a11y": jsxA11y, react, "react-hooks": reactHooks },
    settings: { react: { version: "19" } },
    rules: {
      ...Object.fromEntries(
        Object.entries(jsxA11y.flatConfigs.recommended.rules).map(([id, v]) => [
          id,
          Array.isArray(v) ? ["error", ...v.slice(1)] : "error",
        ]),
      ),
      ...reactHooks.configs.recommended.rules,
    },
  },
  {
    // User-visible text arrives through terminology keys (`t()`), never as JSX literals.
    files: ["src/features/**/*.tsx", "src/routes/**/*.tsx"],
    ignores: ["**/*.test.tsx", "src/routes/__fixtures/**"],
    rules: {
      "react/jsx-no-literals": ["error", { noStrings: false, allowedStrings: [] }],
    },
  },
);
