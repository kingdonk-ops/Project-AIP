import type { AxeResults, Result } from "axe-core";
import { axe } from "vitest-axe";

/** Violations at or above "serious" impact: the DESIGN-01 gate. */
export function blockingViolations(results: AxeResults): Result[] {
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

/**
 * Runs axe on a rendered container. `color-contrast` is disabled because jsdom does not compute
 * layout or cascade; contrast is covered by contrast.ts unit tests and the Playwright axe run.
 */
export async function axeBlocking(container: Element): Promise<string[]> {
  const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
  return blockingViolations(results).map((v) => `${v.id}: ${v.help}`);
}
