// TESTING-09: the real sign-in (ADR 0005), no stub. The app's /login resolves the tenant from the
// email (login_directory), Keycloak sends the browser straight to the tenant's IdP (the mock IdP
// realm on dev and the demo), and the callback lands in the shell with the app's own session cookie.
import { expect, type BrowserContext, type Page } from "@playwright/test";
import type { TenantUser } from "./tenants";

export const SESSION_COOKIE = "__Host-aip_sid";
export const CSRF_COOKIE = "__Host-aip_csrf";

// The API allows 10 `login/start` calls per minute per client IP (moving window, IDENTITY-02), and
// every sign-in in the skeleton lane comes from the runner's one IP. On a 429 wait the window out
// and try again, instead of loosening the limit for tests (TESTING-12).
const LOGIN_START_WINDOW_MS = 61_000;

export async function loginAs(page: Page, user: TenantUser): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    await page.goto("/login");
    await page.getByLabel("Work email").fill(user.email);
    const started = page.waitForResponse(
      (r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v1/auth/login/start",
    );
    await page.getByRole("button", { name: "Continue" }).click();
    const status = (await started).status();
    if (status !== 429 || attempt >= 2) {
      expect(status, `${user.tenant}: login/start is accepted`).toBe(200);
      break;
    }
    await page.waitForTimeout(LOGIN_START_WINDOW_MS);
  }

  // The IdP's own form (Keycloak's default theme on the mock IdP realm).
  const username = page.locator("#username");
  await expect(username, `${user.tenant}: the IdP sign-in form is shown`).toBeVisible();
  await username.fill(user.email);
  await page.locator("#password").fill(user.password);
  await page.locator("#kc-login").click();

  await expect(page, `${user.tenant}: sign-in lands back in the app`).not.toHaveURL(/\/login(\?|$)|\/auth\/|\/realms\//);
  await expect(
    page.getByRole("button", { name: "Account menu" }),
    `${user.tenant}: the signed-in shell is shown`,
  ).toBeVisible();
  await expectSessionCookie(page.context(), user);
}

export async function expectSessionCookie(context: BrowserContext, user: TenantUser): Promise<void> {
  const names = (await context.cookies()).map((c) => c.name);
  expect(names, `${user.tenant}: the app issued its own session cookie`).toContain(SESSION_COOKIE);
}
