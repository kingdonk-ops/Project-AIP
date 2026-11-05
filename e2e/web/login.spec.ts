// DESIGN-02: the production build (`vite preview`, no dev stub): guard redirect, headers, login axe.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("unauthenticated /projects?status=active redirects to /login with the encoded next", async ({ page }) => {
  await page.goto("/projects?status=active");
  await expect(page).toHaveURL(/\/login\?next=%2Fprojects%3Fstatus%3Dactive$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.locator("input[type=password]")).toHaveCount(0);
});

test("login page has no serious or critical axe violations", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("Work email")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});

test("preview serves the security headers with a strict CSP", async ({ request }) => {
  const response = await request.get("/login");
  const csp = response.headers()["content-security-policy"] ?? "";
  expect(csp).toMatch(/script-src 'self';/);
  expect(csp).not.toMatch(/script-src[^;]*unsafe-inline/);
  expect(csp).toContain("frame-ancestors 'none'");
  expect(response.headers()["referrer-policy"]).toBe("strict-origin-when-cross-origin");
});

// DESIGN-19: the sign-in page follows DESIGN-09 — the form sits in one white Panel with a 1px hairline
// on the off-white canvas, the notice is a tinted strip in the tone (danger for a failure), and the
// email field carries a decorative leading icon. Under [data-contrast="high"] the canvas is white and
// the notice drops its tint for a 2px outline. axe passes in both.
for (const contrast of ["default", "high"] as const) {
  test(`login page matches the DESIGN-09 surfaces (${contrast} contrast) and passes axe`, async ({ page }, testInfo) => {
    await page.goto("/login?error=failed");
    await expect(page.getByLabel("Work email")).toBeVisible();
    if (contrast === "high") await page.evaluate(() => (document.documentElement.dataset.contrast = "high"));

    const panel = page.getByRole("region", { name: "Sign in" });
    await expect(panel).toBeVisible();
    await expect(panel.getByLabel("Work email")).toBeVisible();
    const look = await page.evaluate(() => {
      const panelEl = document.querySelector("section.aip-panel") as Element;
      const notice = document.querySelector(".shell-login__notice") as Element;
      const p = getComputedStyle(panelEl);
      const n = getComputedStyle(notice);
      return {
        canvas: getComputedStyle(document.documentElement).backgroundColor,
        panel: { width: p.borderTopWidth, style: p.borderTopStyle, background: p.backgroundColor, shadow: p.boxShadow },
        notice: { background: n.backgroundColor, color: n.color, border: n.borderTopWidth },
      };
    });
    expect(look.panel).toEqual({ width: "1px", style: "solid", background: "rgb(255, 255, 255)", shadow: "none" });
    if (contrast === "default") {
      expect(look.canvas).toBe("rgb(250, 250, 250)");
      // --status-danger on --status-danger-subtle, never an accent fill
      expect(look.notice).toEqual({ background: "rgb(254, 242, 242)", color: "rgb(185, 28, 28)", border: "0px" });
    } else {
      expect(look.canvas).toBe("rgb(255, 255, 255)");
      expect(look.notice).toEqual({ background: "rgb(255, 255, 255)", color: "rgb(127, 29, 29)", border: "2px" });
    }
    await expect(page.getByRole("alert")).toContainText("We could not sign you in");
    await expect(page.locator(".aip-input-wrap svg[aria-hidden='true']")).toHaveCount(1);
    expect(await page.getByLabel("Work email").evaluate((el) => el.getBoundingClientRect().height)).toBe(32);

    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
      `${testInfo.project.name}, ${contrast} contrast: no serious or critical axe violations`,
    ).toEqual([]);
  });
}

test("login page shows the signed-out notice as a tinted info strip", async ({ page }) => {
  await page.goto("/login?signed_out=1");
  const notice = page.getByRole("status").filter({ hasText: "You have been signed out." });
  await expect(notice).toBeVisible();
  const look = await notice.evaluate((el) => ({ background: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color }));
  expect(look).toEqual({ background: "rgb(239, 246, 255)", color: "rgb(29, 78, 216)" });
});
