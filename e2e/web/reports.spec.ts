// REPORTS-04: the report register (RegisterTable). The stub session (Vite dev server) covers what
// the browser alone decides: the register keeps its status filter and search in the URL, shows a
// download link to the API only on succeeded reports, and fits a phone. The list API is answered
// with page.route (a fake that honours status and q). Rendering, the real download and the
// cross-tenant 404 run against the whole stack in reports-live.spec.ts and against Postgres in
// apps/api (test_register_download_db.py).
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
  { label: "KF-01 Karratha compressor station", status: "succeeded" },
  { label: "PL-07 Pilbara gas plant", status: "queued" },
  { label: "KF-02 Karratha tank farm", status: "failed" },
  { label: "BR-11 Burrup jetty", status: "succeeded" },
].map(({ label, status }, i) => ({
  id: `00000000-0000-7000-8000-00000000010${i}`,
  status,
  templateId: "00000000-0000-7000-8000-0000000000f1",
  templateKey: "project-summary",
  templateVersion: 1,
  variant: "internal",
  recordType: "project",
  recordId: `00000000-0000-4000-8000-00000000020${i}`,
  recordLabel: label,
  projectId: `00000000-0000-4000-8000-00000000020${i}`,
  snapshotId: "00000000-0000-7000-8000-0000000000e1",
  dataHash: "a".repeat(64),
  opsJobId: null,
  requestedBy: null,
  rerenderOf: null,
  htmlSha256: null,
  fileId: status === "succeeded" ? `00000000-0000-7000-8000-00000000030${i}` : null,
  pdfSha256: status === "succeeded" ? "b".repeat(64) : null,
  pdfSizeBytes: status === "succeeded" ? 2048 : null,
  errorCode: status === "failed" ? "RENDER_UNAVAILABLE" : null,
  renderedAt: status === "succeeded" ? "2026-10-31T02:00:00Z" : null,
  createdAt: "2026-10-31T01:59:00Z",
  updatedAt: "2026-10-31T02:00:00Z",
  templateNameKey: "report.template.project_summary",
}));

/** Answer the list API like the server would for `status` and `q` (one page). */
async function serveReports(page: Page) {
  await page.route(
    (url) => url.pathname === "/api/v1/reports/renders",
    (route) => {
      const params = new URL(route.request().url()).searchParams;
      const statuses = params.getAll("status");
      const q = (params.get("q") ?? "").toLowerCase();
      const items = FIXTURE.filter(
        (r) =>
          (statuses.length === 0 || statuses.includes(r.status)) &&
          (!q || r.recordLabel.toLowerCase().includes(q) || r.templateKey.includes(q)),
      );
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items, nextCursor: null }) });
    },
  );
}

async function openRegister(browser: Browser, path: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await signInAsStub(page, "alice@kaefer.test");
  await serveReports(page);
  await page.goto(path);
  return page;
}

const dataRows = (page: Page) => page.locator("tbody tr[data-row]");

test("the register lists reports with a download link to the API only on ready ones", async ({ browser }) => {
  const page = await openRegister(browser, "/reports/register");
  await expect(page.getByRole("heading", { name: "Report register", level: 1 })).toBeVisible();
  await expect(dataRows(page)).toHaveCount(4);
  await expect(page.getByRole("link", { name: /^Download PDF for/ })).toHaveCount(2);
  await expect(page.getByRole("link", { name: "Download PDF for KF-01 Karratha compressor station" })).toHaveAttribute(
    "href",
    `/api/v1/reports/renders/${FIXTURE[0]!.id}/file`,
  );
  await expect(dataRows(page).filter({ hasText: "PL-07" }).getByRole("link")).toHaveCount(0);
  await expectNoBlockingAxe(page);
});

test("status filter and search live in the URL: a copied link reopens the same register", async ({ browser }) => {
  const page = await openRegister(browser, "/reports/register");
  await expect(dataRows(page)).toHaveCount(4);
  await page.getByRole("combobox", { name: "Status" }).selectOption("succeeded");
  await expect(dataRows(page)).toHaveCount(2);
  await page.getByRole("searchbox", { name: "Search record or template" }).fill("karratha");
  await expect(page).toHaveURL(/[?&]q=karratha(&|$)/);
  await expect(dataRows(page)).toHaveCount(1);
  await expect(dataRows(page).first()).toContainText("KF-01");
  await expectNoBlockingAxe(page);

  const copied = await openRegister(browser, page.url());
  await expect(copied.getByRole("combobox", { name: "Status" })).toHaveValue("succeeded");
  await expect(copied.getByRole("searchbox", { name: "Search record or template" })).toHaveValue("karratha");
  await expect(dataRows(copied)).toHaveCount(1);
});

// DESIGN-08: at 390px the table scrolls inside its own region and the page never scrolls sideways.
test("at 390px the register scrolls in its own region, with no horizontal page scroll", async ({ browser }) => {
  const page = await openRegister(browser, "/reports/register");
  await page.setViewportSize({ width: 390, height: 780 });
  await page.locator("summary", { hasText: "Columns" }).click();
  await page.getByRole("checkbox", { name: "Error" }).check(); // more columns than fit
  await page.locator("summary", { hasText: "Columns" }).click();
  await expect(dataRows(page)).toHaveCount(4);
  const scroll = page.getByRole("region", { name: "Reports generated in this tenant" });
  await expect(scroll).toHaveAttribute("tabindex", "0");
  const widths = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(widths.page).toBe(widths.viewport);
  await expectNoBlockingAxe(page);
});
