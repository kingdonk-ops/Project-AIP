import type { AxeResults, Result } from "axe-core";
import { axe } from "vitest-axe";

/** Violations at or above "serious" impact: the DESIGN-01 gate (same as packages/ui/src/test/axe.ts). */
export function blockingViolations(results: AxeResults): Result[] {
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

/** axe on a rendered container; `color-contrast` is off because jsdom computes no layout. */
export async function axeBlocking(container: Element): Promise<string[]> {
  const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
  return blockingViolations(results).map((v) => `${v.id}: ${v.help}`);
}
