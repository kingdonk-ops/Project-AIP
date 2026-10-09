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

test("shell landmarks, nav and axe on the signed-in page", async ({ page, isMobile }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/");
  await expect(page.getByRole("banner")).toBeVisible();
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Home" })).toBeVisible();
  if (isMobile) {
    // Under 768px the rail collapses behind the menu button.
    await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeHidden();
    await page.getByRole("button", { name: "Menu", exact: true }).click();
  }
  await expect(page.getByRole("link", { name: "Projects" })).toBeVisible();
  await expectNoBlockingAxe(page);
  expect(await page.evaluate(() => document.cookie)).not.toContain("__Host-");
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
