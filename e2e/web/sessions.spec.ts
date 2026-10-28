// TESTING-12 Part A (review 11 H4): server-side sessions (IDENTITY-03) and SSO logout proven end to
// end against real Keycloak, in the skeleton lane (compose in CI; the demo for the `@staging` ones).
// Owns TESTING-09's carried-forward list: the real sign-in cookie, reload, /me/tenant per tenant,
// revoking another browser from Active sessions (main journey, cross-tenant, axe), Logout ending the
// aip realm's SSO session, and Keycloak's back-channel logout ending the app session.
// Every wait is a web-first assertion or a poll; there are no fixed sleeps.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { KeycloakAdmin } from "../fixtures/keycloak-admin";
import { CSRF_COOKIE, SESSION_COOKIE, loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const users = tenantUsers();
const AUTHORIZE = /\/realms\/aip\/protocol\/openid-connect\/auth\b/;

test.describe.configure({ mode: "serial" });

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

/** A context whose user agent ends with `tag`, so its row in Active sessions is unambiguous. */
async function taggedContext(browser: Browser, tag: string): Promise<BrowserContext> {
  const probe = await browser.newContext();
  const userAgent = await (await probe.newPage()).evaluate(() => navigator.userAgent);
  await probe.close();
  return browser.newContext({ userAgent: `${userAgent} ${tag}` });
}

/** Call the API from inside the page, so the browser sends Origin and the CSRF header like the app. */
async function apiFromPage(page: Page, method: string, path: string): Promise<number> {
  return page.evaluate(
    async ({ method, path, csrfCookie }) => {
      const token = document.cookie
        .split("; ")
        .find((c) => c.startsWith(`${csrfCookie}=`))
        ?.slice(csrfCookie.length + 1);
      const response = await fetch(path, {
        method,
        credentials: "same-origin",
        headers: { "x-csrf-token": token ?? "" },
      });
      return response.status;
    },
    { method, path, csrfCookie: CSRF_COOKIE },
  );
}

async function sessionIds(page: Page): Promise<string[]> {
  const response = await page.request.get("/api/v1/me/sessions");
  expect(response.status()).toBe(200);
  return ((await response.json()) as { items: { id: string; current: boolean }[] }).items.map((s) => s.id);
}

async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page, "IDENTITY-03: Sign out lands on the signed-out sign-in page").toHaveURL(/\/login\?signed_out=1$/);
}

test("@skeleton @staging real sign-in returns to next with an HttpOnly session cookie, survives a reload, and /me/tenant is per tenant", async ({ browser }) => {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();
  try {
    await loginAs(pageA, users.a, { from: "/projects" });
    await expect(pageA.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();

    const sid = (await contextA.cookies()).find((c) => c.name === SESSION_COOKIE);
    expect(sid, "IDENTITY-03: the app issued its session cookie").toBeDefined();
    expect(sid?.httpOnly, "IDENTITY-03: the session cookie is HttpOnly").toBe(true);
    expect(sid?.secure, "IDENTITY-03: the session cookie is Secure (__Host-)").toBe(true);
    expect(sid?.path).toBe("/");
    const readable = await pageA.evaluate(() => document.cookie);
    expect(readable, "IDENTITY-03: script cannot read the session cookie").not.toContain(`${SESSION_COOKIE}=`);
    expect(readable, "IDENTITY-03: the CSRF cookie is readable by design (double submit)").toContain(`${CSRF_COOKIE}=`);

    await pageA.reload();
    await expect(pageA.getByRole("button", { name: "Account menu" }), "IDENTITY-03: a reload keeps the session").toBeVisible();
    await expect(pageA).toHaveURL(/\/projects$/);

    // TENANCY-01: GET /me/tenant answers each signed-in user with their own tenant.
    const tenantA = await pageA.request.get("/api/v1/me/tenant");
    expect(tenantA.status()).toBe(200);
    expect(((await tenantA.json()) as { slug: string }).slug, "TENANCY-01: alice's tenant is kaefer-demo").toBe("kaefer-demo");
    await loginAs(pageB, users.b);
    const tenantB = await pageB.request.get("/api/v1/me/tenant");
    expect(tenantB.status()).toBe(200);
    expect(((await tenantB.json()) as { slug: string }).slug, "TENANCY-01: bob's tenant is tenant-b").toBe("tenant-b");
  } finally {
    await contextA.close();
    await contextB.close();
  }
});

test("@skeleton @staging revoking another browser from Active sessions signs it out; tenant B sees none of tenant A's sessions", async ({ browser }) => {
  const tagA = `e2e-a-${runId()}`;
  const tagOther = `e2e-other-${runId()}`;
  const contextA = await taggedContext(browser, tagA);
  const contextOther = await taggedContext(browser, tagOther);
  const contextB = await browser.newContext();
  const pageA = await contextA.newPage();
  const pageOther = await contextOther.newPage();
  const pageB = await contextB.newPage();
  try {
    await loginAs(pageA, users.a);
    await loginAs(pageOther, users.a);
    const uaOther = await pageOther.evaluate(() => navigator.userAgent);

    // Main journey: the Account menu opens Active sessions, which lists both browsers.
    await pageA.getByRole("button", { name: "Account menu" }).click();
    await pageA.getByRole("menuitem", { name: "Active sessions" }).click();
    await expect(pageA).toHaveURL(/\/settings\/profile\/sessions$/);
    await expect(pageA.getByRole("heading", { name: "Active sessions", level: 1 })).toBeVisible();
    const current = pageA.getByRole("row").filter({ hasText: tagA });
    await expect(current, "IDENTITY-03: this browser's session is listed once").toHaveCount(1);
    await expect(current, "IDENTITY-03: and marked as this device").toContainText("(This device)");
    const other = pageA.getByRole("row").filter({ hasText: tagOther });
    await expect(other, "IDENTITY-03: the other browser's session is listed").toHaveCount(1);
    await expect(other).not.toContainText("(This device)");
    await expectNoBlockingAxe(pageA);

    await pageA.getByRole("button", { name: `Sign out the session on ${uaOther}`, exact: true }).click();
    await expect(other, "IDENTITY-03: the revoked session leaves the list").toHaveCount(0);
    await expect(current).toHaveCount(1);

    // The other browser's next request is 401, and its next navigation asks it to sign in.
    // Postgres is the truth at once; a failed cache purge could serve the session for up to 60 s.
    await expect
      .poll(async () => (await pageOther.request.get("/api/v1/me")).status(), {
        message: "IDENTITY-03: the revoked browser's next request is 401",
        timeout: 70_000,
      })
      .toBe(401);
    await pageOther.goto("/projects");
    await expect(pageOther, "IDENTITY-03: the revoked browser is sent to sign in").toHaveURL(/\/login\?next=/);

    // The revoking browser is still signed in.
    await pageA.reload();
    await expect(pageA.getByRole("heading", { name: "Active sessions", level: 1 })).toBeVisible();
    expect((await pageA.request.get("/api/v1/me")).status(), "IDENTITY-03: revoking another session keeps this one").toBe(200);
    const idsA = await sessionIds(pageA);
    expect(idsA.length).toBeGreaterThan(0);

    // Cross-tenant: bob's Active sessions show none of alice's, and revoking one of hers is 404.
    await loginAs(pageB, users.b);
    await pageB.goto("/settings/profile/sessions");
    await expect(pageB.getByRole("heading", { name: "Active sessions", level: 1 })).toBeVisible();
    await expect(pageB.getByRole("row").filter({ hasText: "(This device)" })).toHaveCount(1);
    await expect(pageB.getByRole("row").filter({ hasText: tagA }), "IDENTITY-03: tenant B never sees tenant A's sessions").toHaveCount(0);
    const idsB = await sessionIds(pageB);
    expect(idsB.filter((id) => idsA.includes(id)), "IDENTITY-03: tenant B's session list shares no id with tenant A's").toEqual([]);
    expect(await apiFromPage(pageB, "DELETE", `/api/v1/me/sessions/${idsA[0]}`), "IDENTITY-03: tenant A's session id is 404 for tenant B").toBe(404);
    await expectNoBlockingAxe(pageB);
    expect((await pageA.request.get("/api/v1/me")).status(), "IDENTITY-03: tenant B's attempt left alice signed in").toBe(200);
  } finally {
    await contextA.close();
    await contextOther.close();
    await contextB.close();
  }
});

test("@skeleton Sign out ends the aip realm's Keycloak SSO session and clears both cookies; returning asks for credentials", async ({ page }) => {
  const kc = await KeycloakAdmin.connect();
  try {
    const before = new Set(await kc.sessionIdsFor(users.a.email));
    const authorize = page.waitForRequest(AUTHORIZE);
    await loginAs(page, users.a);
    const authorizeUrl = new URL((await authorize).url());
    const userId = await kc.userId(users.a.email);
    const mine = (await kc.sessionIds(userId)).filter((id) => !before.has(id));
    expect(mine, "IDENTITY-03: this sign-in opened an SSO session in the aip realm").toHaveLength(1);

    await signOut(page);
    const names = (await page.context().cookies()).map((c) => c.name);
    expect(names, "IDENTITY-03: Logout clears the session cookie").not.toContain(SESSION_COOKIE);
    expect(names, "IDENTITY-03: Logout clears the CSRF cookie").not.toContain(CSRF_COOKIE);

    // The queued identity.revoke_keycloak_sessions job (the worker) ends this browser's SSO session.
    await expect
      .poll(async () => (await kc.sessionIds(userId)).filter((id) => mine.includes(id)), {
        message: "IDENTITY-03: Keycloak no longer holds the signed-out SSO session",
        timeout: 60_000,
      })
      .toEqual([]);

    // Without an SSO session the aip realm asks for credentials instead of signing straight back in.
    // (The hint is dropped so Keycloak shows its own form rather than forwarding to the tenant IdP,
    // whose own session is the customer's to end.)
    authorizeUrl.searchParams.delete("kc_idp_hint");
    authorizeUrl.searchParams.delete("login_hint");
    await page.goto(authorizeUrl.toString());
    await expect(page.locator("#kc-form-login"), "IDENTITY-03: the aip realm shows its sign-in form again").toBeVisible();

    await page.goto("/projects");
    await expect(page, "IDENTITY-03: the app asks the signed-out browser to sign in").toHaveURL(/\/login\?next=/);
  } finally {
    await kc.dispose();
  }
});

test("@skeleton Keycloak's admin sign-out reaches the back-channel endpoint and ends the app session", async ({ page }) => {
  const kc = await KeycloakAdmin.connect();
  try {
    await loginAs(page, users.a);
    expect((await page.request.get("/api/v1/me")).status()).toBe(200);

    await kc.logoutUser(await kc.userId(users.a.email));

    await expect
      .poll(
        async () => {
          const response = await page.request.get("/api/v1/me");
          if (response.status() !== 401) return String(response.status());
          return `401 ${((await response.json()) as { detail?: { code?: string } }).detail?.code}`;
        },
        { message: "IDENTITY-03: the back-channel logout revoked the app session", timeout: 70_000 },
      )
      .toBe("401 SESSION_EXPIRED");
    await page.goto("/projects");
    await expect(page, "IDENTITY-03: the browser is sent to sign in").toHaveURL(/\/login\?next=/);
  } finally {
    await kc.dispose();
  }
});
