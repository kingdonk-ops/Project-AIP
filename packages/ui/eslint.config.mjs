// ESLint flat config for @aip/ui (DESIGN-01): the shared ARCH-03 boundaries config plus
// jsx-a11y (recommended, as errors), react hooks and a no-literal-text rule for components.
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
    // Labels arrive as props (terminology keys); components never carry user-visible literals.
    files: ["src/components/**/*.tsx"],
    ignores: ["src/components/**/*.test.tsx"],
    rules: {
      "react/jsx-no-literals": ["error", { noStrings: false, allowedStrings: [] }],
    },
  },
);
