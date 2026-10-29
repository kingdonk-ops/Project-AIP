// PROJECTS-02 / PROJECTS-06: the projects register (RegisterTable) and create form. The stub session
// (Vite dev server) covers what the browser alone decides: permissions gate the page, and the
// register keeps its filter, sort and columns in the URL. The register journeys answer the list API
// with page.route (a fake that honours status and sort); the server's sorting, paging and CSV
// export are proven against Postgres in apps/api (test_projects_db.py). Creating a project needs a
// real API session: the walking skeleton covers creation and the cross-tenant check for real, and
// sessions.spec.ts the seeded viewer's server-403 journey (TESTING-12, review 11 M12).
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

const FIXTURE = [
  { code: "A-100", status: "active" },
  { code: "A-300", status: "active" },
  { code: "A-200", status: "active" },
  { code: "D-900", status: "draft" },
  { code: "C-500", status: "closing" },
].map(({ code, status }, i) => ({
  id: `00000000-0000-7000-8000-00000000000${i}`,
  code,
  name: `Project ${code}`,
  status,
  siteId: null,
  clientCompanyId: null,
  classificationId: null,
  templateId: null,
  region: "ap-southeast-2",
  timezone: "Australia/Perth",
  currency: "AUD",
  closedAt: null,
  syncVersion: 1,
  createdAt: "2026-10-13T00:00:00Z",
  updatedAt: "2026-10-13T01:00:00Z",
}));

/** Answer the list API like the server would for `status` and `sort=code|-code` (one page). */
async function serveProjects(page: Page) {
  await page.route(
    (url) => url.pathname === "/api/v1/projects",
    (route) => {
      const params = new URL(route.request().url()).searchParams;
      const statuses = params.getAll("status");
      const sort = params.get("sort") ?? "code";
      const items = FIXTURE.filter((p) => statuses.length === 0 || statuses.includes(p.status)).sort(
        (a, b) => a.code.localeCompare(b.code) * (sort === "-code" ? -1 : 1),
      );
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items, nextCursor: null }) });
    },
  );
  await page.route(
    (url) => url.pathname === "/api/v1/sites",
    (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], nextCursor: null }) }),
  );
}

async function openRegister(browser: Browser, path: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signInAsStub(page, "alice@kaefer.test");
  await serveProjects(page);
  await page.goto(path);
  return page;
}

const dataRows = (page: Page) => page.locator("tbody tr[data-row]");

test("a user without project.create sees the register without a Create button", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/projects?status=active");
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Status" })).toHaveValue("active");
  await expect(page.getByRole("link", { name: "Create project" })).toHaveCount(0);
  await expect(page).toHaveURL(/\/projects\?status=active$/);
  await expectNoBlockingAxe(page);
});

// DESIGN-08: at 390px the table scrolls inside its own region and the page never scrolls sideways.
test("at 390px the register scrolls in its own region, with no horizontal page scroll", async ({ browser }) => {
  const page = await openRegister(browser, "/projects");
  await page.setViewportSize({ width: 390, height: 780 });
  await page.locator("summary", { hasText: "Columns" }).click();
  await page.getByRole("checkbox", { name: "Region" }).check(); // more columns than fit
  await page.locator("summary", { hasText: "Columns" }).click();
  await expect(dataRows(page)).toHaveCount(5);
  const scroll = page.getByRole("region", { name: "Projects in this tenant" });
  await expect(scroll).toHaveAttribute("tabindex", "0");
  const widths = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(widths.page).toBe(widths.viewport);
  const region = await scroll.evaluate((el) => ({ scroll: el.scrollWidth, client: el.clientWidth }));
  expect(region.scroll).toBeGreaterThan(region.client);
  await expectNoBlockingAxe(page);
});

// DESIGN-08: an anchor with button classes (here the CSV export link) has no underline and the button focus ring.
test("a link styled as a button has no underline and the 2px accent focus ring", async ({ browser }) => {
  const page = await openRegister(browser, "/projects");
  const link = page.getByRole("link", { name: "Export CSV" });
  // A key press first puts the page in keyboard mode, so programmatic focus shows :focus-visible.
  // (Not Tab: WebKit can skip links on Tab, which would test the browser, not the ring.)
  await page.keyboard.press("Shift");
  await link.focus();
  await expect(link).toBeFocused();
  const style = await link.evaluate((el) => {
    const s = getComputedStyle(el);
    return { decoration: s.textDecorationLine, outline: s.outlineStyle, width: s.outlineWidth };
  });
  expect(style).toEqual({ decoration: "none", outline: "solid", width: "2px" });
});

test("filter, sort and columns live in the URL: a copied link reopens the same register", async ({ browser }) => {
  const page = await openRegister(browser, "/projects");
  await expect(dataRows(page)).toHaveCount(5);
  await expect(page.getByRole("columnheader", { name: "Region" })).toHaveCount(0); // hidden by default

  await page.getByRole("combobox", { name: "Status" }).selectOption("active");
  await expect(dataRows(page)).toHaveCount(3);
  const sortByCode = page.getByRole("button", { name: /^Project code/ });
  await sortByCode.click(); // ascending
  await expect(page).toHaveURL(/[?&]sort=code(&|$)/);
  await sortByCode.click(); // descending
  await expect(page).toHaveURL(/[?&]sort=-code(&|$)/);
  await page.locator("summary", { hasText: "Columns" }).click();
  await page.getByRole("checkbox", { name: "Site" }).uncheck();
  await expect(page.getByRole("columnheader", { name: "Site" })).toHaveCount(0);
  await expect(dataRows(page).first()).toContainText("A-300");
  await expectNoBlockingAxe(page);

  const copied = await openRegister(browser, page.url());
  await expect(copied.getByRole("combobox", { name: "Status" })).toHaveValue("active");
  await expect(copied.getByRole("columnheader", { name: /Project code/ })).toHaveAttribute("aria-sort", "descending");
  await expect(copied.getByRole("columnheader", { name: "Site" })).toHaveCount(0);
  await expect(dataRows(copied)).toHaveCount(3);
  await expect(dataRows(copied).first()).toContainText("A-300");
  await expect(copied.getByRole("link", { name: "Export CSV" })).toHaveAttribute(
    "href",
    "/api/v1/projects/export.csv?sort=-code&status=active",
  );
});

test("keyboard only: Tab into the table, ArrowDown to the second row, Enter opens it", async ({ browser }) => {
  const page = await openRegister(browser, "/projects");
  await expect(dataRows(page)).toHaveCount(5);
  // The last header control before the rows: Tab from it lands on the first row (one tab stop).
  await page.getByRole("button", { name: /^Updated/ }).focus();
  await page.keyboard.press("Tab");
  await expect(dataRows(page).first()).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(dataRows(page).nth(1)).toBeFocused();
  await page.keyboard.press("Enter");
  // Code ascending: A-100, A-200, ... so the second row is A-200 (fixture index 2).
  await expect(page).toHaveURL(/\/projects\/00000000-0000-7000-8000-000000000002$/);
});

test("visiting /projects/new without project.create shows the permission-denied state", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/projects/new");
  await expect(page.getByRole("heading", { name: "You do not have permission to create projects." })).toBeVisible();
  await expect(page.getByLabel("Project code")).toHaveCount(0);
  await expectNoBlockingAxe(page);
});
