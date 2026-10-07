/**
 * TypeScript mirror of tokens.css (:root defaults). A unit test keeps the two in sync.
 * Consumers style through `cssVar(...)` so tenant overrides of the CSS variables still apply.
 */
export const colors = {
  "neutral-0": "#ffffff",
  "neutral-50": "#fafafa",
  "neutral-100": "#f5f5f5",
  "neutral-200": "#e5e5e5",
  "neutral-300": "#d4d4d4",
  "neutral-400": "#a3a3a3",
  "neutral-500": "#737373",
  "neutral-600": "#525252",
  "neutral-700": "#404040",
  "neutral-800": "#262626",
  "neutral-900": "#171717",
  accent: "#0f766e",
  "accent-foreground": "#ffffff",
  "status-success": "#15803d",
  "status-warning": "#b45309",
  "status-danger": "#b91c1c",
  "status-info": "#1d4ed8",
  "status-neutral": "#525252",
  "status-foreground": "#ffffff",
} as const;

export const fontSize = {
  "text-xs": "12px",
  "text-sm": "13px",
  "text-base": "14px",
  "text-md": "16px",
  "text-lg": "20px",
  "text-xl": "24px",
  "text-2xl": "30px",
} as const;

export const spacing = {
  "space-0": "0px",
  "space-1": "4px",
  "space-2": "8px",
  "space-3": "12px",
  "space-4": "16px",
  "space-5": "20px",
  "space-6": "24px",
  "space-8": "32px",
  "space-10": "40px",
  "space-12": "48px",
} as const;

export const radii = {
  "radius-sm": "2px",
  "radius-md": "4px",
  "radius-lg": "8px",
} as const;

export const density = {
  compact: { "row-h": "32px", "control-h": "32px", "touch-target": "32px" },
  comfortable: { "row-h": "40px", "control-h": "40px", "touch-target": "40px" },
  field: { "control-h": "48px", "touch-target": "48px" },
} as const;

export const fonts = {
  sans: '"IBM Plex Sans", system-ui, sans-serif',
  mono: '"IBM Plex Mono", ui-monospace, monospace',
} as const;

export const statusTones = ["success", "warning", "danger", "info", "neutral"] as const;
export type StatusTone = (typeof statusTones)[number];

/** Every :root token with its default value, keyed by CSS variable name without the leading `--`. */
export const rootTokens: Readonly<Record<string, string>> = {
  ...colors,
  ...fontSize,
  ...spacing,
  ...radii,
  ...density.compact,
};

export function cssVar(name: string): string {
  return `var(--${name})`;
}
