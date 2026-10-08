/**
 * Tailwind preset for apps that use Tailwind (v3 `presets: [aipPreset]`, or v4 via `@config`).
 * Every value points at a CSS variable from tokens.css, so tenant theming (e.g. `--accent`)
 * applies at runtime without a rebuild and apps never hard-code hex values.
 * Typed structurally so @aip/ui does not depend on Tailwind itself.
 */
import { colors, fontSize, radii, spacing } from "./src/tokens/tokens";

type Stripped<K extends string, P extends string> = K extends `${P}${infer R}` ? R : K;

/** Maps token names to `var(--name)`, optionally stripping a prefix from the key, keeping key types. */
function varMap<K extends string, P extends string = "">(
  tokens: Readonly<Record<K, unknown>>,
  strip?: P,
): Record<Stripped<K, P>, string> {
  return Object.fromEntries(
    (Object.keys(tokens) as K[]).map((k) => [strip ? k.replace(strip, "") : k, `var(--${k})`]),
  ) as Record<Stripped<K, P>, string>;
}

export const aipPreset = {
  theme: {
    extend: {
      colors: {
        ...varMap(colors),
        surface: "var(--surface)",
        "surface-muted": "var(--surface-muted)",
        foreground: "var(--foreground)",
        "foreground-muted": "var(--foreground-muted)",
        border: "var(--border)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      fontSize: varMap(fontSize, "text-"),
      spacing: varMap(spacing, "space-"),
      borderRadius: varMap(radii, "radius-"),
      height: { row: "var(--row-h)", control: "var(--control-h)" },
      minHeight: { touch: "var(--touch-target)" },
      minWidth: { touch: "var(--touch-target)" },
    },
  },
} as const;

export default aipPreset;
