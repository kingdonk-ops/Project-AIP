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
