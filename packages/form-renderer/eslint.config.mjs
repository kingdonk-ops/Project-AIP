// ESLint flat config for @aip/form-renderer: the shared ARCH-03 boundaries + terms config (FORMS-02),
// plus jsx-a11y (recommended, as errors), the React hooks rules and a no-literal-text rule for the
// components (FORMS-03), mirroring packages/ui/eslint.config.mjs.
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
    // Every renderer string is a terminology key (`t()`) or template content; never a JSX literal.
    files: ["src/**/*.tsx"],
    ignores: ["**/*.test.tsx"],
    rules: {
      "react/jsx-no-literals": ["error", { noStrings: false, allowedStrings: [" "] }],
    },
  },
);
