// PROJECTS-07: the project detail page (RecordDetail: edit + lifecycle/archive) and the sites
// register (create/edit/delete). Like projects.spec.ts, these run on the Vite dev server with the
// stub session; the API is faked with page.route, so they prove what the browser decides — opening
// a record, editing and archiving it, managing sites, and the cross-tenant not-found state. The
// server's RLS and permission enforcement are proven against Postgres in apps/api and, end to end,
// by the walking skeleton once real API sessions (IDENTITY-03) carry these permissions.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Browser, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

const PROJECT_ID = "00000000-0000-7000-8000-00000000d001";
const SITE_ID = "00000000-0000-7000-8000-0000000051d0";

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

function makeProject(overrides: Record<string, unknown> = {}) {
  return {
    id: PROJECT_ID,
    code: "L592",
    name: "Line 592",
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
    createdAt: "2026-10-13T00:00:00Z",
    updatedAt: "2026-10-13T01:00:00Z",
    ...overrides,
  };
}

function makeSite(overrides: Record<string, unknown> = {}) {
  return {
    id: SITE_ID,
    code: "PERTH-01",
    name: "Perth yard",
    lat: null,
    lng: null,
    timezone: "Australia/Perth",
    isSystem: false,
    createdAt: "2026-10-13T00:00:00Z",
    updatedAt: "2026-10-13T01:00:00Z",
    ...overrides,
  };
}

/** A fake projects + sites API the detail page and sites register drive against. */
async function serve(page: Page, options: { projectStatus?: string } = {}) {
  const project = makeProject({ status: options.projectStatus ?? "active" });
  const sites = [makeSite()];

  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route(
    (url) => url.pathname === "/api/v1/projects",
    (route) => route.fulfill(json({ items: [project], nextCursor: null })),
  );
  await page.route(
    (url) => url.pathname === `/api/v1/projects/${PROJECT_ID}`,
    (route) => {
      if (route.request().method() === "PATCH") {
        const body = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
        Object.assign(project, body, { syncVersion: (project.syncVersion as number) + 1 });
        return route.fulfill(json(project));
      }
      return route.fulfill(json(project));
    },
  );
  await page.route(
    (url) => url.pathname === "/api/v1/sites",
    (route) => {
      if (route.request().method() === "POST") {
        const body = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
        const created = makeSite({ id: "00000000-0000-7000-8000-0000000051d9", ...body });
        sites.push(created);
        return route.fulfill(json(created, 201));
      }
      return route.fulfill(json({ items: sites, nextCursor: null }));
    },
  );
}

async function openAs(browser: Browser, email: string, path: string, options?: { projectStatus?: string }): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signInAsStub(page, email);
  await serve(page, options);
  await page.goto(path);
  return page;
}

test("open a project from the register, edit its name, and archive it", async ({ browser }) => {
  const page = await openAs(browser, "alice@kaefer.test", "/projects");

  // Open the project from the register (focus the row, Enter opens it — RegisterTable's row action).
  const row = page.locator("tbody tr[data-row]").first();
  await row.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/projects/${PROJECT_ID}$`));
  await expect(page.getByRole("heading", { level: 1, name: "Line 592" })).toBeVisible();

  // Edit the name.
  const name = page.getByRole("textbox", { name: "Name" });
  await name.fill("Line 592 refurbishment");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.locator("[aria-live=polite]").getByText("Project L592 was saved.")).toBeVisible();
  await expectNoBlockingAxe(page);

  // Archive it through the confirm dialog.
  await page.getByRole("button", { name: "Archive project" }).click();
  const dialog = page.getByRole("dialog", { name: "Archive L592?" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Archive" }).click();
  await expect(page.locator("[aria-live=assertive], [aria-live=polite]").getByText("Project L592 was archived.")).toBeVisible();
});

test("the sites register creates a site through the dialog", async ({ browser }) => {
  const page = await openAs(browser, "alice@kaefer.test", "/sites");
  await expect(page.getByRole("heading", { level: 1, name: "Sites" })).toBeVisible();
  await expect(page.getByText("PERTH-01")).toBeVisible();

  await page.getByRole("button", { name: "Create site" }).click();
  const dialog = page.getByRole("dialog", { name: "Create site" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox", { name: "Site code" }).fill("KWINANA");
  await dialog.getByRole("textbox", { name: "Name" }).fill("Kwinana yard");
  await expectNoBlockingAxe(page);
  await dialog.getByRole("button", { name: "Save" }).click();

  await expect(page.locator("[aria-live=polite]").getByText("Site KWINANA was created.")).toBeVisible();
  await expect(dialog).toBeHidden();
});

test("tenant B opening tenant A's project id sees the not-found state", async ({ browser }) => {
  const page = await (await browser.newContext()).newPage();
  await signInAsStub(page, "bob@acme.test");
  // RLS makes another tenant's project a 404.
  await page.route(
    (url) => url.pathname === `/api/v1/projects/${PROJECT_ID}`,
    (route) => route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ code: "PROJECT_NOT_FOUND" }) }),
  );
  await page.route(
    (url) => url.pathname === "/api/v1/sites",
    (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], nextCursor: null }) }),
  );
  await page.goto(`/projects/${PROJECT_ID}`);

  await expect(page.getByText("Not found")).toBeVisible();
  await expectNoBlockingAxe(page);
});
