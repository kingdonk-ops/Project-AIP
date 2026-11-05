// DESIGN-18: shared check that a page's content sits in a DESIGN-09 Panel on the canvas.
import { expect, type Locator, type Page } from "@playwright/test";

const LOOK = {
  light: { canvas: "rgb(250, 250, 250)", border: "rgb(229, 229, 229)" },
  high: { canvas: "rgb(255, 255, 255)", border: "rgb(0, 0, 0)" },
} as const;

/** The element is a white panel with a visible 1px solid border on the canvas, in light and high contrast. */
export async function expectPanelOnCanvas(page: Page, panel: Locator): Promise<void> {
  for (const contrast of ["light", "high"] as const) {
    await page.evaluate((mode) => {
      if (mode === "high") document.documentElement.dataset.contrast = "high";
      else delete document.documentElement.dataset.contrast;
    }, contrast);
    const look = await panel.evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        canvas: getComputedStyle(document.documentElement).backgroundColor,
        background: s.backgroundColor,
        border: `${s.borderTopWidth} ${s.borderTopStyle} ${s.borderTopColor}`,
      };
    });
    expect(look, `${contrast} contrast`).toEqual({
      canvas: LOOK[contrast].canvas,
      background: "rgb(255, 255, 255)",
      border: `1px solid ${LOOK[contrast].border}`,
    });
  }
  await page.evaluate(() => delete document.documentElement.dataset.contrast);
}
