/** WCAG 2.x contrast helpers (DESIGN-01; reused by DESIGN-05 tenant theming). */

const HEX = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;

function parseHex(hex: string): [number, number, number] {
  const match = HEX.exec(hex.trim());
  if (!match?.[1]) throw new Error(`invalid hex colour: ${hex}`);
  let digits = match[1];
  if (digits.length === 3) {
    digits = digits
      .split("")
      .map((d) => d + d)
      .join("");
  }
  return [0, 2, 4].map((i) => parseInt(digits.slice(i, i + 2), 16)) as [number, number, number];
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG 2.x relative luminance of a hex colour (0 = black, 1 = white). */
export function relativeLuminance(hex: string): number {
  const [r, g, b] = parseHex(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG 2.x contrast ratio between two hex colours, from 1 to 21. Order does not matter. */
export function contrastRatio(fg: string, bg: string): number {
  const a = relativeLuminance(fg);
  const b = relativeLuminance(bg);
  const [hi, lo] = a >= b ? [a, b] : [b, a];
  return (hi + 0.05) / (lo + 0.05);
}

export const MIN_TEXT_CONTRAST = 4.5;

/**
 * An accent is accessible when white text on it and the accent on the surface both reach 4.5:1.
 * @param surface page surface colour; defaults to the token surface (white).
 */
export function isAccessibleAccent(hex: string, surface = "#ffffff"): boolean {
  return (
    contrastRatio("#ffffff", hex) >= MIN_TEXT_CONTRAST &&
    contrastRatio(hex, surface) >= MIN_TEXT_CONTRAST
  );
}
