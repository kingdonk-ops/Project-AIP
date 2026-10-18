// DESIGN-02: the app shell main journey. Runs on the Vite dev server with the fixture session stub
// (preview/production builds cannot contain it). Tests tagged @needs-identity-03 need real sessions.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

test("unauthenticated /projects redirects to /login, then sign in lands on /projects", async ({ page }) => {
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login\?next=%2Fprojects$/);
  await expect(page.locator("input[type=password]")).toHaveCount(0);
  await expectNoBlockingAxe(page);

  await page.getByLabel("Work email").fill("alice@kaefer.test");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/projects$/);
  await expect(page.getByRole("banner")).toContainText("Kaefer Demo");
  await page.getByRole("button", { name: "Account menu" }).click();
  await expect(page.getByTestId("user-email")).toHaveText("alice@kaefer.test");
});

test("shell landmarks, nav and axe on the signed-in page", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/");
  await expect(page.getByRole("banner")).toBeVisible();
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  // Key off the real viewport, not Playwright's isMobile flag: the iPad project is isMobile but is
  // 810px wide, above the 768px breakpoint, so its rail stays open.
  const narrow = (page.viewportSize()?.width ?? Number.POSITIVE_INFINITY) < 768;
  if (narrow) {
    // Under 768px the rail collapses behind the menu button.
    await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeHidden();
    await page.getByRole("button", { name: "Menu", exact: true }).click();
  }
  await expect(page.getByRole("link", { name: "Projects" })).toBeVisible();
  await expectNoBlockingAxe(page);
  expect(await page.evaluate(() => document.cookie)).not.toContain("__Host-");
});

// DESIGN-08: under 768px the rail is a drawer with a backdrop; Escape or a backdrop click closes it.
test("mobile drawer: backdrop, Escape and backdrop click close it and focus returns to the menu button", async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? Number.POSITIVE_INFINITY) >= 768, "the rail is a drawer only under 768px");
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/");
  const menu = page.getByRole("button", { name: "Menu", exact: true });
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  const backdrop = page.getByTestId("shell-backdrop");

  await menu.click();
  await expect(nav).toBeVisible();
  await expect(backdrop).toBeVisible();
  await expectNoBlockingAxe(page);
  await nav.getByRole("link", { name: "Home" }).focus();
  await page.keyboard.press("Escape");
  await expect(nav).toBeHidden();
  await expect(backdrop).toHaveCount(0);
  await expect(menu).toBeFocused();

  await menu.click();
  // Click the dimmed page to the right of the 160px drawer.
  await backdrop.click({ position: { x: 300, y: 200 } });
  await expect(nav).toBeHidden();
  await expect(menu).toBeFocused();
});

test("login: the email input, hint and Continue button share one width", async ({ page }) => {
  await page.goto("/login");
  const input = await page.getByLabel("Work email").boundingBox();
  const button = await page.getByRole("button", { name: "Continue" }).boundingBox();
  const hint = await page.locator(".aip-form-field__hint").boundingBox();
  expect(input?.width).toBeGreaterThan(0);
  expect(button?.width).toBeCloseTo(input?.width ?? 0, 0);
  expect(hint?.width).toBeCloseTo(input?.width ?? 0, 0);
});

test("sign out lands on /login?signed_out=1 and the session is gone", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/projects");
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login\?signed_out=1$/);

  await page.goto("/");
  await expect(page).toHaveURL(/\/login\?next=/);
  await page.goBack();
  await page.reload();
  await expect(page).toHaveURL(/\/login/);
});

test("cross-tenant: the other tenant's user sees only their own tenant", async ({ page }) => {
  await signInAsStub(page, "bob@acme.test");
  await page.goto("/");
  await expect(page.getByRole("banner")).toContainText("Tenant B");
  await expect(page.getByText("Kaefer Demo")).toHaveCount(0);
});

// DESIGN-14: the header lockup "<Company> AIP" links Home and the document title ends with it.
for (const [email, company] of [
  ["alice@kaefer.test", "Kaefer Demo"],
  ["bob@acme.test", "Tenant B"],
] as const) {
  test(`brand lockup: ${email} sees "${company} AIP" linking Home`, async ({ page }) => {
    await signInAsStub(page, email);
    await page.goto("/projects");
    const lockup = page.getByRole("banner").getByRole("link", { name: `${company} AIP, home` });
    await expect(lockup).toBeVisible();
    await expect(page).toHaveTitle(new RegExp(`${company} AIP$`));
    await lockup.click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page).toHaveTitle(`Home · ${company} AIP`);
    await expectNoBlockingAxe(page);
  });
}

test("unknown email gets the same generic failure, with no enumeration", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Work email").fill("nobody@nowhere.test");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/login\?error=failed$/);
  await expect(page.getByRole("alert")).toContainText("We could not sign you in");
});

test("@needs-identity-03 real Keycloak sign-in lands on next with an HttpOnly cookie", () => {
  test.skip(true, "needs IDENTITY-03 (app sessions) and IDENTITY-02 (GET /me); the stub covers the shell until then");
});
