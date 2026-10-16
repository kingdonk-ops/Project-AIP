// ESLint flat config for @aip/ui (DESIGN-01): the shared ARCH-03 boundaries config plus
// jsx-a11y (recommended, as errors), react hooks and a no-literal-text rule for components.
// DESIGN-04: `noBlockingDialogs` bans window.confirm/alert/prompt; apps/web extends it.
import aip from "@aip/config-eslint";
import jsxA11y from "eslint-plugin-jsx-a11y";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

const dialogMessage =
  "Blocking browser dialogs are banned: use confirm() for questions and toast() for messages, from @aip/ui.";
const dialogs = ["confirm", "alert", "prompt"];

/** Bans the blocking browser dialogs. Import as `@aip/ui/eslint` and spread into an app's config. */
export const noBlockingDialogs = {
  files: ["**/*.{js,mjs,cjs,jsx,ts,mts,cts,tsx}"],
  rules: {
    "no-restricted-globals": ["error", ...dialogs.map((name) => ({ name, message: dialogMessage }))],
    "no-restricted-properties": [
      "error",
      ...["window", "globalThis", "self"].flatMap((object) =>
        dialogs.map((property) => ({ object, property, message: dialogMessage })),
      ),
    ],
  },
};

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
    files: ["src/components/**/*.tsx", "src/feedback/**/*.tsx", "src/patterns/**/*.tsx"],
    ignores: ["**/*.test.tsx"],
    rules: {
      "react/jsx-no-literals": ["error", { noStrings: false, allowedStrings: [] }],
    },
  },
  noBlockingDialogs,
);
