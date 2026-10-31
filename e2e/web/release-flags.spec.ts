// DESIGN-15: nav items honour release flags and a tenant admin switches them on the Settings page.
// The stub session (Vite dev server) supplies the fixture users; the flags API is mocked with
// page.route, one stateful store per tenant, because the default e2e run has no API session holding
// tenant.flags.manage. The API's own permission check (403 without it) and per-tenant isolation are
// covered by apps/api/tests/platform/flags/test_flags.py (ARCH-08).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

const ADMIN = "alice@kaefer.test"; // kaefer-demo, holds tenant.flags.manage
const OTHER_TENANT = "bob@acme.test"; // tenant-b, does not
const FLAGS = "/api/v1/settings/flags";
const BIM_NAV = "BIM models (preview)";

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
}

interface TenantFlags {
  values: Record<string, boolean>;
  puts: { flag: string; enabled: boolean }[];
}

/** One tenant's flags API: GET lists the values, PUT changes one (only `canManage` may). */
async function mockFlagsApi(page: Page, store: TenantFlags, canManage: boolean) {
  await page.route(`**${FLAGS}**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() === "GET" && path === FLAGS) {
      return json({ flags: Object.entries(store.values).map(([flag, enabled]) => ({ flag, enabled })) });
    }
    const put = path.match(/\/settings\/flags\/([^/]+)$/);
    if (put && request.method() === "PUT") {
      if (!canManage) return json({ detail: "forbidden" }, 403);
      const flag = put[1]!;
      const { enabled } = request.postDataJSON() as { enabled: boolean };
      store.puts.push({ flag, enabled });
      store.values[flag] = enabled;
      return json({ flag, enabled });
    }
    return json({ detail: "not mocked" }, 500);
  });
}

/** Under 768px the rail sits behind the menu button (DESIGN-08); open it before reading the nav. */
async function openNav(page: Page) {
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  if ((page.viewportSize()?.width ?? Number.POSITIVE_INFINITY) < 768) {
    await page.getByRole("button", { name: "Menu", exact: true }).click();
  }
  await expect(nav).toBeVisible();
  return nav;
}

async function closeNav(page: Page) {
  if ((page.viewportSize()?.width ?? Number.POSITIVE_INFINITY) < 768) await page.keyboard.press("Escape");
}

test("an admin switches bim on and the gated nav item appears; the other tenant's flag is unchanged", async ({
  page,
  browser,
}) => {
  const tenantA: TenantFlags = { values: { ai: false, bim: false }, puts: [] };
  const tenantB: TenantFlags = { values: { ai: false, bim: false }, puts: [] };
  await mockFlagsApi(page, tenantA, true);
  await signInAsStub(page, ADMIN);
  await page.goto("/settings/flags");

  await expect(page.getByRole("heading", { name: "Release flags", level: 1 })).toBeVisible();
  const bim = page.getByRole("checkbox", { name: "BIM models" });
  await expect(bim).not.toBeChecked();
  let nav = await openNav(page);
  await expect(nav.getByRole("link", { name: "Release flags" })).toBeVisible();
  await expect(nav.getByRole("link", { name: BIM_NAV })).toHaveCount(0);
  await closeNav(page);
  await expectNoBlockingAxe(page);

  await bim.click();
  await expect(bim).toBeChecked();
  await expect(page.getByText("BIM models is now on.")).toBeVisible();
  expect(tenantA.puts).toEqual([{ flag: "bim", enabled: true }]);
  nav = await openNav(page);
  await expect(nav.getByRole("link", { name: BIM_NAV })).toBeVisible();
  await expectNoBlockingAxe(page);

  // Cross-tenant: tenant B's user reads tenant B's flags, so the item stays hidden, and has no flags page.
  const context = await browser.newContext();
  try {
    const other = await context.newPage();
    await mockFlagsApi(other, tenantB, false);
    await signInAsStub(other, OTHER_TENANT);
    await other.goto("/");
    await expect(other.getByRole("heading", { name: "Home" })).toBeVisible();
    const otherNav = await openNav(other);
    await expect(otherNav.getByRole("link", { name: "Projects" })).toBeVisible();
    await expect(otherNav.getByRole("link", { name: BIM_NAV })).toHaveCount(0);
    await expect(otherNav.getByRole("link", { name: "Release flags" })).toHaveCount(0);
    expect(tenantB).toEqual({ values: { ai: false, bim: false }, puts: [] });
  } finally {
    await context.close();
  }
});

test("a user without tenant.flags.manage gets the 403 state and no switches", async ({ page }) => {
  const store: TenantFlags = { values: { ai: false, bim: false }, puts: [] };
  await mockFlagsApi(page, store, false);
  await signInAsStub(page, OTHER_TENANT);
  await page.goto("/settings/flags");
  await expect(page.getByRole("heading", { name: "Release flags", level: 1 })).toBeVisible();
  await expect(page.getByText("You don’t have access")).toBeVisible();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await expectNoBlockingAxe(page);
  expect(store.puts).toEqual([]);
});
