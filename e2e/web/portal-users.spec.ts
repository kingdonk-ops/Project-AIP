// PORTAL-07: the external users admin pages (register, invite with grant builder, detail). The stub
// session (Vite dev server) covers what the browser alone decides: filters in the URL, the invite
// body the grant builder sends (no expiry, view always on), renewing an expired grant, and fitting a
// phone. The portal API is answered with page.route (a fake that honours status, expiringWithinDays
// and q, and keeps renewals). Real sessions need a step-up for invite and renew, so the routes run
// against Postgres in apps/api (PORTAL-01's test_portal_users_db.py and test_admin_filters_db.py),
// including the tenant-b 404.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

const DAY = 24 * 60 * 60 * 1000;
const inDays = (days: number) => new Date(Date.now() + days * DAY).toISOString();
const ALICE_ID = "00000000-0000-4000-8000-0000000000a1";
const P1 = { id: "00000000-0000-4000-8000-0000000002a1", code: "KF-01", name: "Karratha compressor station" };
const P2 = { id: "00000000-0000-4000-8000-0000000002a2", code: "PL-07", name: "Pilbara gas plant" };
const USERS = "/api/v1/admin/portal/users";

function projectOut(p: typeof P1) {
  return {
    ...p,
    status: "active",
    siteId: null,
    clientCompanyId: null,
    classificationId: null,
    templateId: null,
    region: "ap-southeast-2",
    timezone: "Australia/Perth",
    currency: "AUD",
    closedAt: null,
    syncVersion: 1,
    createdAt: "2026-10-01T00:00:00Z",
    updatedAt: "2026-10-01T00:00:00Z",
  };
}

type Grant = Record<string, unknown> & { id: string; state: string; expiresAt: string; projectId: string };
type User = Record<string, unknown> & { id: string; email: string; companyName: string; status: string; grants: Grant[] };

function grant(n: number, projectId: string, expiresInDays: number): Grant {
  return {
    id: `00000000-0000-7000-8000-0000000003${String(n).padStart(2, "0")}`,
    projectId,
    assetId: null,
    actions: ["view", "sign_off"],
    accessDays: 180,
    expiresAt: inDays(expiresInDays),
    state: expiresInDays > 0 ? "live" : "expired",
    renewedAt: null,
    renewedBy: null,
    revokedAt: null,
    revokedReason: null,
    createdBy: ALICE_ID,
    createdAt: "2026-10-01T00:00:00Z",
  };
}

function user(n: number, email: string, companyName: string, status: string, grants: Grant[]): User {
  return {
    id: `00000000-0000-7000-8000-0000000001${String(n).padStart(2, "0")}`,
    userId: `00000000-0000-4000-8000-0000000004${String(n).padStart(2, "0")}`,
    email,
    companyName,
    organisationId: null,
    status,
    invitedBy: ALICE_ID,
    firstSignedInAt: status === "invited" ? null : "2026-10-02T00:00:00Z",
    suspendedAt: null,
    suspendedReason: null,
    syncVersion: 1,
    createdAt: "2026-10-01T00:00:00Z",
    updatedAt: "2026-10-01T00:00:00Z",
    grants,
  };
}

function view(u: User) {
  const states = new Set(u.grants.map((g) => g.state));
  const effectiveStatus = u.status !== "active" ? u.status : !states.has("live") && states.has("expired") ? "expired" : "active";
  const live = u.grants.filter((g) => g.state === "live").map((g) => g.expiresAt).sort();
  return { ...u, effectiveStatus, expiresAt: live.at(-1) ?? null };
}

function fixture(): User[] {
  return [
    user(1, "client.a@rio.example", "Rio Example Pty Ltd", "active", [grant(1, P1.id, 5), grant(2, P2.id, 120)]),
    user(2, "lead@bhp.example", "BHP Example", "invited", [grant(3, P1.id, 170)]),
    user(3, "old@fmg.example", "FMG Example", "active", [grant(4, P2.id, -3)]),
  ];
}

/** Answer the portal admin API like the server would, for one tab. Returns the invite bodies seen. */
async function servePortal(page: Page): Promise<unknown[]> {
  const users = fixture();
  const invites: unknown[] = [];
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route(
    (url) => url.pathname === "/api/v1/projects",
    (route) => route.fulfill(json({ items: [projectOut(P1), projectOut(P2)], nextCursor: null })),
  );
  await page.route(
    (url) => url.pathname === "/api/v1/assets",
    (route) => route.fulfill(json({ items: [], nextCursor: null })),
  );
  await page.route(
    (url) => url.pathname.startsWith(USERS),
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const rest = url.pathname.slice(USERS.length).split("/").filter(Boolean);
      if (request.method() === "GET" && rest.length === 0) {
        const status = url.searchParams.get("status");
        const days = Number(url.searchParams.get("expiringWithinDays") ?? 0);
        const q = (url.searchParams.get("q") ?? "").toLowerCase();
        const items = users
          .filter((u) => !status || u.status === status)
          .filter((u) => !days || u.grants.some((g) => g.state === "live" && new Date(g.expiresAt).getTime() <= Date.now() + days * DAY))
          .filter((u) => !q || u.email.includes(q) || u.companyName.toLowerCase().includes(q))
          .map(view);
        return route.fulfill(json({ items, nextCursor: null }));
      }
      if (request.method() === "POST" && rest.length === 0) {
        invites.push(request.postDataJSON());
        const created = user(9, "client.b@rio.example", "Rio Example Pty Ltd", "invited", [grant(9, P1.id, 180)]);
        users.push(created);
        return route.fulfill(json(view(created), 201));
      }
      const found = users.find((u) => u.id === rest[0]);
      if (!found) return route.fulfill(json({ code: "NOT_FOUND" }, 404));
      if (request.method() === "GET" && rest.length === 1) return route.fulfill(json(view(found)));
      if (request.method() === "POST" && rest[1] === "grants" && rest[3] === "renew") {
        const g = found.grants.find((x) => x.id === rest[2])!;
        Object.assign(g, { state: "live", expiresAt: inDays(180), renewedAt: new Date().toISOString(), renewedBy: ALICE_ID });
        return route.fulfill(json(g));
      }
      return route.fulfill(json({ code: "NOT_FOUND" }, 404));
    },
  );
  return invites;
}

async function open(browser: Browser, path: string, email = "alice@kaefer.test"): Promise<{ page: Page; invites: unknown[] }> {
  const page = await (await browser.newContext()).newPage();
  await signInAsStub(page, email);
  const invites = await servePortal(page);
  await page.goto(path);
  return { page, invites };
}

const dataRows = (page: Page) => page.locator("tbody tr[data-row]");

test("the register filters by expiry and status in the URL, and a user's expired access is renewed", async ({ browser }) => {
  const { page } = await open(browser, "/admin/portal/users");
  await expect(page.getByRole("heading", { name: "External users", level: 1 })).toBeVisible();
  await expect(dataRows(page)).toHaveCount(3);
  await expect(dataRows(page).filter({ hasText: "Rio Example" })).toContainText("Expiring soon");
  await expectNoBlockingAxe(page);

  await page.getByRole("combobox", { name: "Expiring within" }).selectOption("30d");
  await expect(page).toHaveURL(/[?&]expiring=30d(&|$)/);
  await expect(dataRows(page)).toHaveCount(1);
  await expect(dataRows(page).first()).toContainText("client.a@rio.example");

  await page.getByRole("combobox", { name: "Expiring within" }).selectOption("");
  await page.getByRole("combobox", { name: "Status" }).selectOption("invited");
  await expect(page).toHaveURL(/[?&]status=invited(&|$)/);
  await expect(dataRows(page)).toHaveCount(1);
  await expect(dataRows(page).first()).toContainText("BHP Example");

  await page.getByRole("combobox", { name: "Status" }).selectOption("");
  await page.getByRole("link", { name: "old@fmg.example" }).click();
  await expect(page.getByRole("heading", { name: "old@fmg.example", level: 1 })).toBeVisible();
  await page.getByRole("tab", { name: "Access" }).click();
  const access = page.getByRole("table", { name: "Project access" });
  await expect(access).toContainText("Expired");
  await expectNoBlockingAxe(page);
  await access.getByRole("button", { name: "Renew access to PL-07 Pilbara gas plant" }).click();
  await expect(access).toContainText("Current");
  await expect(access).toContainText("Renewed");
});

test("the invite form sends the grants built, with view always on and no expiry", async ({ browser }) => {
  const { page, invites } = await open(browser, "/admin/portal/users/new");
  await expect(page.getByRole("heading", { name: "Invite external user", level: 1 })).toBeVisible();
  await page.getByLabel("Email").fill("client.b@rio.example");
  await page.getByLabel("First name").fill("Client");
  await page.getByLabel("Last name").fill("B");
  await page.getByLabel("Company").fill("Rio Example Pty Ltd");

  const first = page.getByRole("group", { name: "Access 1" });
  await first.getByRole("combobox", { name: "Project" }).selectOption(P1.id);
  await expect(first.getByRole("checkbox", { name: "View records" })).toBeDisabled();
  await first.getByRole("checkbox", { name: "Sign off" }).click();
  await page.getByRole("button", { name: "Add project access" }).click();
  const second = page.getByRole("group", { name: "Access 2" });
  await second.getByRole("combobox", { name: "Project" }).selectOption(P2.id);
  await second.getByRole("checkbox", { name: "Download reports" }).click();
  await expectNoBlockingAxe(page);

  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByRole("heading", { name: "client.b@rio.example", level: 1 })).toBeVisible();
  expect(invites).toEqual([
    {
      email: "client.b@rio.example",
      firstName: "Client",
      lastName: "B",
      companyName: "Rio Example Pty Ltd",
      grants: [
        { projectId: P1.id, actions: ["view", "sign_off"] },
        { projectId: P2.id, actions: ["view", "download"] },
      ],
    },
  ]);
});

test("another tenant's user is not found, and bob has no external users item", async ({ browser }) => {
  const { page } = await open(browser, `${USERS.replace("/api/v1", "")}/00000000-0000-7000-8000-00000000dead`, "bob@acme.test");
  await expect(page.getByRole("link", { name: "Back to external users" })).toBeVisible();
  await expect(page.getByText("client.a@rio.example")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "External users", exact: true })).toHaveCount(0);
  await expectNoBlockingAxe(page);
});

// DESIGN-08: at 390px the table scrolls inside its own region and the page never scrolls sideways.
test("at 390px the register and the invite form fit without horizontal page scroll", async ({ browser }) => {
  const { page } = await open(browser, "/admin/portal/users");
  await page.setViewportSize({ width: 390, height: 780 });
  await expect(dataRows(page)).toHaveCount(3);
  const fits = () =>
    page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth);
  expect(await fits()).toBe(true);
  await page.goto("/admin/portal/users/new");
  await expect(page.getByRole("group", { name: "Access 1" })).toBeVisible();
  expect(await fits()).toBe(true);
  await expectNoBlockingAxe(page);
});
