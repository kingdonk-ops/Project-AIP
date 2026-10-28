// TESTING-12 (review 11 H4 and M12): real-session journeys against real Keycloak, no stub. Sign-in
// survives a reload with an HttpOnly session cookie; sign out ends the app session and the Keycloak
// SSO session; Keycloak's back-channel logout revokes the app session; revoking another browser
// from Active sessions makes its next request 401; tenant B can neither see nor revoke tenant A's
// sessions; and the seeded viewer's project create is refused by the server, not just hidden.
// Runs against the compose stack in CI (`--project web --grep @skeleton`); only the viewer journey
// also runs on the demo (`@staging`), when its secret is set (`@viewer`).
import AxeBuilder from "@axe-core/playwright";
import { devices, expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { apiCall, isAuthorizeRequest, keycloakSso } from "../fixtures/api";
import { CSRF_COOKIE, SESSION_COOKIE, loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers, viewerUser, type TenantUser } from "../fixtures/tenants";

test.describe.configure({ mode: "serial" });

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

interface SignedIn {
  context: BrowserContext;
  page: Page;
  /** The aip realm authorize URL this sign-in went through (for the SSO probe and logout). */
  authorize: string;
}

async function signIn(browser: Browser, user: TenantUser, options: { userAgent?: string } = {}): Promise<SignedIn> {
  const context = await browser.newContext(options.userAgent ? { userAgent: options.userAgent } : {});
  const page = await context.newPage();
  const authorize = page.waitForRequest(isAuthorizeRequest);
  await loginAs(page, user);
  return { context, page, authorize: (await authorize).url() };
}

test("@skeleton a real session survives a reload, its cookie is HttpOnly and /me/tenant is the user's tenant", async ({ browser }) => {
  const users = tenantUsers();
  const a = await signIn(browser, users.a);
  const b = await signIn(browser, users.b);
  try {
    await a.page.reload();
    await expect(a.page, "IDENTITY-03: a reload keeps the session").not.toHaveURL(/\/login(\?|$)/);
    await expect(a.page.getByRole("button", { name: "Account menu" })).toBeVisible();

    const cookies = new Map((await a.context.cookies()).map((c) => [c.name, c]));
    expect(cookies.get(SESSION_COOKIE)?.httpOnly, "IDENTITY-03: the session cookie is HttpOnly").toBe(true);
    expect(cookies.get(CSRF_COOKIE)?.httpOnly, "the CSRF cookie is readable by design (double submit)").toBe(false);
    const visible = await a.page.evaluate(() => document.cookie);
    expect(visible, "IDENTITY-03: script cannot read the session cookie").not.toContain(SESSION_COOKIE);
    expect(visible).toContain(CSRF_COOKIE);

    for (const [signedIn, slug] of [
      [a, "kaefer-demo"],
      [b, "tenant-b"],
    ] as const) {
      const tenant = await apiCall(signedIn.page, "GET", "/api/v1/me/tenant");
      expect(tenant.status, `TENANCY-01: /me/tenant answers for ${slug}`).toBe(200);
      expect(tenant.json?.slug, `TENANCY-01: /me/tenant is ${slug}`).toBe(slug);
    }
  } finally {
    await a.context.close();
    await b.context.close();
  }
});

test("@skeleton sign out ends the app session and the Keycloak SSO session", async ({ browser }) => {
  const a = await signIn(browser, tenantUsers().a);
  try {
    expect(await keycloakSso(a.context, a.authorize), "the Keycloak SSO session exists after sign-in").toBe("active");

    await a.page.getByRole("button", { name: "Account menu" }).click();
    await a.page.getByRole("menuitem", { name: "Sign out" }).click();
    await expect(a.page).toHaveURL(/\/login\?signed_out=1$/);
    const names = (await a.context.cookies()).map((c) => c.name);
    expect(names, "IDENTITY-03: logout clears the session cookie").not.toContain(SESSION_COOKIE);
    expect(names, "IDENTITY-03: logout clears the CSRF cookie").not.toContain(CSRF_COOKIE);

    // The queued identity.revoke_keycloak_sessions job (worker) ends the SSO session.
    await expect
      .poll(() => keycloakSso(a.context, a.authorize), {
        message: "IDENTITY-03: the Keycloak SSO session is gone after logout",
        timeout: 90_000,
        intervals: [1_000, 2_000, 5_000],
      })
      .toBe("ended");

    await a.page.goto("/projects");
    await expect(a.page, "re-visiting the app asks for credentials").toHaveURL(/\/login\?next=/);
    await expect(a.page.getByLabel("Work email")).toBeVisible();
  } finally {
    await a.context.close();
  }
});

test("@skeleton Keycloak back-channel logout revokes the app session", async ({ browser }) => {
  const a = await signIn(browser, tenantUsers().a);
  try {
    expect((await apiCall(a.page, "GET", "/api/v1/me")).status).toBe(200);

    // End the SSO session at Keycloak itself (its own logout page, confirmed in the browser).
    // Keycloak then posts a logout token to the API's back-channel endpoint.
    const logout = new URL(a.authorize);
    logout.pathname = logout.pathname.replace(/\/auth$/, "/logout");
    logout.search = "";
    const kc = await a.context.newPage();
    await kc.goto(logout.toString());
    await kc.locator("#kc-logout").click();
    await expect(kc.locator("body")).toContainText(/logged out/i);
    await kc.close();

    await expect
      .poll(async () => (await apiCall(a.page, "GET", "/api/v1/me")).status, {
        message: "IDENTITY-03: the back-channel logout revoked the app session",
        timeout: 30_000,
      })
      .toBe(401);
    await a.page.goto("/projects");
    await expect(a.page).toHaveURL(/\/login\?next=/);
  } finally {
    await a.context.close();
  }
});

test("@skeleton revoking another browser from Active sessions makes its next request 401", async ({ browser }) => {
  const users = tenantUsers();
  // A real Chrome user agent with a marker, so the second browser's row can be told apart.
  const device = `E2E-second-${runId()}`;
  const first = await signIn(browser, users.a);
  const second = await signIn(browser, users.a, { userAgent: `${devices["Desktop Chrome"].userAgent} ${device}` });
  try {
    await first.page.goto("/settings/profile/sessions");
    await expect(first.page.getByRole("heading", { name: "Active sessions", level: 1 })).toBeVisible();
    const row = first.page.getByRole("row").filter({ hasText: device });
    await expect(row, "the other browser is listed").toHaveCount(1);
    await expect(first.page.getByRole("row").filter({ hasText: "This device" })).toHaveCount(1);
    await expectNoBlockingAxe(first.page);

    await first.page.getByRole("button", { name: new RegExp(`^Sign out the session on .*${device}$`) }).click();
    await expect(row, "the revoked session leaves the list").toHaveCount(0);

    const next = await apiCall(second.page, "GET", "/api/v1/me");
    expect(next.status, "IDENTITY-03: the revoked browser's next request is 401").toBe(401);
    expect((next.json?.detail as { code?: string } | undefined)?.code).toBe("SESSION_EXPIRED");
    await second.page.goto("/projects");
    await expect(second.page, "the revoked browser is sent to sign in").toHaveURL(/\/login\?next=/);

    expect((await apiCall(first.page, "GET", "/api/v1/me")).status, "the revoking browser stays signed in").toBe(200);
  } finally {
    await first.context.close();
    await second.context.close();
  }
});

test("@skeleton Active sessions: tenant B sees none of tenant A's sessions and cannot revoke them", async ({ browser }) => {
  const users = tenantUsers();
  const a = await signIn(browser, users.a);
  const b = await signIn(browser, users.b);
  try {
    const listA = await apiCall(a.page, "GET", "/api/v1/me/sessions");
    const idsA = (listA.json?.items as { id: string; current: boolean }[]).map((s) => s.id);
    const currentA = (listA.json?.items as { id: string; current: boolean }[]).find((s) => s.current)?.id;
    expect(currentA).toBeTruthy();

    await b.page.goto("/settings/profile/sessions");
    await expect(b.page.getByRole("heading", { name: "Active sessions", level: 1 })).toBeVisible();
    await expect(b.page.getByRole("row").filter({ hasText: "This device" })).toHaveCount(1);
    await expectNoBlockingAxe(b.page);
    const idsB = ((await apiCall(b.page, "GET", "/api/v1/me/sessions")).json?.items as { id: string }[]).map((s) => s.id);
    expect(idsB.filter((id) => idsA.includes(id)), "tenant B's list holds none of tenant A's sessions").toEqual([]);

    const revoke = await apiCall(b.page, "DELETE", `/api/v1/me/sessions/${currentA}`);
    expect(revoke.status, "tenant A's session id is 404 for tenant B").toBe(404);
    expect((await apiCall(a.page, "GET", "/api/v1/me")).status, "tenant A's session is untouched").toBe(200);
  } finally {
    await a.context.close();
    await b.context.close();
  }
});

// Part B (was QA-3, review 11 M12). The viewer holds no role, so the form is hidden from them; the
// browser's copy of their abilities is widened to show it, and the server must still refuse.
test("@skeleton @staging @viewer the viewer's project create is refused by the server and nothing is created", async ({ browser }) => {
  const code = `E2E-V-${runId()}`;
  const viewer = await signIn(browser, viewerUser());
  let admin: SignedIn | null = null;
  try {
    const abilities = await apiCall(viewer.page, "GET", "/api/v1/access/me/abilities");
    expect(abilities.status).toBe(200);
    expect(abilities.json?.permissions, "ACCESS-01: a user with no role holds no permission").toEqual([]);

    await viewer.page.goto("/projects/new");
    await expect(viewer.page.getByRole("heading", { name: "You do not have permission to create projects." })).toBeVisible();

    await viewer.page.route(
      (url) => url.pathname === "/api/v1/access/me/abilities",
      (route) =>
        route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ permissions: ["project.create"] }) }),
    );
    await viewer.page.reload();
    await viewer.page.getByLabel("Project code").fill(code);
    await viewer.page.getByLabel("Name").fill("Viewer must not create this");
    const posted = viewer.page.waitForResponse(
      (r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v1/projects",
    );
    await viewer.page.getByRole("button", { name: "Create project" }).click();
    expect((await posted).status(), "ACCESS-01: the server refuses project.create").toBe(403);
    await expect(
      viewer.page.getByRole("heading", { name: "You do not have permission to create projects." }),
      "the server's 403 is shown as the permission message",
    ).toBeVisible();
    await expectNoBlockingAxe(viewer.page);

    admin = await signIn(browser, tenantUsers().a);
    const found = await apiCall(admin.page, "GET", `/api/v1/projects?q=${encodeURIComponent(code)}`);
    expect(found.status).toBe(200);
    expect(found.json?.items, "no project was created").toEqual([]);
  } finally {
    await viewer.context.close();
    await admin?.context.close();
  }
});
