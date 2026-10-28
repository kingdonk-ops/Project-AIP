/**
 * ProjectAIP brand marks (DESIGN-17, owner brand files 2026-10-28).
 *
 * - `AipMark`: the green app icon ("AIP" on a rounded square), the inline tag used in lockups, or the
 *   single-letter favicon mark. The letters are drawn as paths, not text, so they look the same in every
 *   font and axe does not score the logotype for text contrast (WCAG 1.4.3 exempts logotypes).
 * - `BadgeLockup` (lockup A): the client's name in their brand colour, then the AIP tag. Tenant headers.
 * - `EndorsedLockup` (lockup C): the client leads, ProjectAIP signs off as the platform. Portal footer.
 *
 * Every word comes from the caller (terminology keys); the client's colour is the `--tenant-brand` token.
 */
import type { ComponentProps } from "react";
import { cn } from "../lib/cn";

/** "AIP" in a 73.5 × 36 box whose cap line sits at y=32 (A: 0–33, I: 36–44.5, P: 48–73.5). */
const LETTER_A = "M0 68L12 32H21L33 68H24L21.67 61H11.33L9 68ZM13.67 54H19.33L16.5 45.5Z";
const LETTERS_IP = "M36 32H44.5V68H36ZM48 32H62A11.5 11.5 0 0 1 62 55H56.5V68H48ZM56.5 39.5V47.5H61.5A4 4 0 0 0 61.5 39.5Z";

export type AipMarkShape = "icon" | "tag" | "letter";

/** viewBox width and height, corner radius, letter scale and offset for each shape. */
const SHAPES: Record<AipMarkShape, { w: number; h: number; r: number; d: string; s: number; x: number; y: number }> = {
  icon: { w: 100, h: 100, r: 22, d: LETTER_A + LETTERS_IP, s: 0.8, x: 20.6, y: 10 },
  tag: { w: 80, h: 52, r: 8, d: LETTER_A + LETTERS_IP, s: 0.7222, x: 13.45, y: -10.11 },
  letter: { w: 100, h: 100, r: 22, d: LETTER_A, s: 1.3889, x: 27.08, y: -19.44 },
};

export interface AipMarkProps extends Omit<ComponentProps<"svg">, "children"> {
  shape?: AipMarkShape;
  /** Rendered height in px; the width follows the shape. Defaults to 1em of the surrounding text. */
  size?: number;
  /** "plain" draws only the letters in the brand green, with no tile (the wordmark's "AIP"). */
  tone?: "tile" | "plain";
}

/** Decorative by default: the caller provides the accessible name (visible or visually hidden text). */
export function AipMark({ shape = "icon", size, tone = "tile", className, ...props }: AipMarkProps) {
  const m = SHAPES[shape];
  const plain = tone === "plain";
  // The plain wordmark letters are cropped to the glyphs so they sit on the text baseline.
  const viewBox = plain ? (shape === "letter" ? "0 32 33 36" : "0 32 73.5 36") : `0 0 ${m.w} ${m.h}`;
  const ratio = plain ? (shape === "letter" ? 33 / 36 : 73.5 / 36) : m.w / m.h;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={viewBox}
      height={size ?? "1em"}
      width={size === undefined ? `${ratio}em` : size * ratio}
      aria-hidden="true"
      focusable="false"
      className={cn("aip-mark", `aip-mark--${shape}`, plain && "aip-mark--plain", className)}
      {...props}
    >
      {plain ? (
        <path d={m.d} fill="var(--brand-green)" fillRule="evenodd" />
      ) : (
        <>
          <rect width={m.w} height={m.h} rx={m.r} fill="var(--brand-green)" />
          <path
            d={m.d}
            fill="var(--brand-on-green)"
            fillRule="evenodd"
            transform={`translate(${m.x} ${m.y}) scale(${m.s})`}
          />
        </>
      )}
    </svg>
  );
}

export interface BadgeLockupProps extends ComponentProps<"span"> {
  /** The client's display name, shown in `--tenant-brand`. */
  company: string;
  /** The product word ("AIP", from terms). The tag draws it; this is its text for assistive tech. */
  product: string;
  companyClassName?: string;
}

/** Lockup A, "Badge": `Kaefer [AIP]`. */
export function BadgeLockup({ company, product, companyClassName, className, ...props }: BadgeLockupProps) {
  return (
    <span className={cn("aip-lockup aip-lockup--badge", className)} {...props}>
      <span className={cn("aip-lockup__company", companyClassName)}>{company}</span>
      <span className="aip-lockup__product">
        <AipMark shape="tag" />
        <span className="aip-visually-hidden">{product}</span>
      </span>
    </span>
  );
}

export interface EndorsedLockupProps extends ComponentProps<"div"> {
  company: string;
  /** "Powered by", from terms. */
  poweredBy: string;
  /** The wordmark's lead-in ("project", from terms); the mark draws the product word after it. */
  platformPrefix: string;
  product: string;
}

/** Lockup C, "Endorsed": `Kaefer | [AIP] POWERED BY projectAIP`. */
export function EndorsedLockup({ company, poweredBy, platformPrefix, product, className, ...props }: EndorsedLockupProps) {
  return (
    <div className={cn("aip-lockup aip-lockup--endorsed", className)} {...props}>
      <span className="aip-lockup__company">{company}</span>
      <span className="aip-lockup__divider" aria-hidden="true" />
      <span className="aip-lockup__platform">
        <AipMark shape="icon" className="aip-lockup__icon" />
        <span className="aip-lockup__endorsement">
          <span className="aip-lockup__powered-by">{poweredBy}</span>
          <span className="aip-lockup__wordmark">
            <span aria-hidden="true">{platformPrefix}</span>
            <AipMark shape="tag" tone="plain" className="aip-lockup__wordmark-product" />
            <span className="aip-visually-hidden">{`${platformPrefix}${product}`}</span>
          </span>
        </span>
      </span>
    </div>
  );
}
