// REPORTS-04: the report register and authorised download against a whole deployment (the compose
// stack in CI lane e2e-skeleton, with Gotenberg and the `pdf` worker). A kaefer-demo admin (A)
// creates a project, requests a project-summary render through the API and waits for it to
// succeed, finds it on /reports/register by searching the project code, and downloads the PDF: the
// file is the stored report (sha256 = the row's pdfSha256) and came from the API, not a storage
// URL. The tenant-b admin (B) cannot list or download it (404). Without the fixture credentials
// (E2E_USER_*/E2E_PASS_*) the suite skips.
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { apiCall } from "../fixtures/api";
import { loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

const code = `RPT-${runId()}`.slice(0, 32);
const name = "Report register e2e";

async function expectNoSeriousAxe(page: Page, where: string) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter((v) => v.impact === "serious" || v.impact === "critical"),
    `${where}: no serious or critical axe violations`,
  ).toEqual([]);
}

interface RenderJob {
  id: string;
  status: string;
  pdfSha256: string | null;
}

(users ? test.describe : test.describe.skip)("REPORTS-04 report register and download", () => {
  test("@skeleton A downloads a rendered report from the register; B cannot see it", async ({ browser }) => {
    test.setTimeout(180_000);
    const contextA = await browser.newContext({ acceptDownloads: true });
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    try {
      await loginAs(pageA, users!.a);

      const project = await apiCall(pageA, "POST", "/api/v1/projects", { code, name });
      expect(project.status, "a project to report on is created").toBe(201);
      const requested = await apiCall(pageA, "POST", "/api/v1/reports/renders", {
        templateKey: "project-summary",
        variant: "internal",
        recordType: "project",
        recordId: project.json!.id,
      });
      expect(requested.status, "A requests a render").toBe(202);
      const jobId = requested.json!.id as string;

      // The pdf worker renders it through Gotenberg.
      let job: RenderJob | undefined;
      await expect
        .poll(
          async () => {
            job = (await apiCall(pageA, "GET", `/api/v1/reports/renders/${jobId}`)).json as unknown as RenderJob;
            return job.status;
          },
          { timeout: 120_000, intervals: [1_000, 2_000, 5_000] },
        )
        .toBe("succeeded");

      await pageA.goto(`/reports/register?q=${encodeURIComponent(code)}`);
      await expect(pageA.getByRole("heading", { level: 1, name: "Report register" })).toBeVisible();
      const row = pageA.locator("tbody tr[data-row]").filter({ hasText: code });
      await expect(row).toHaveCount(1);
      await expect(row.getByText("Ready")).toBeVisible();
      await expectNoSeriousAxe(pageA, "report register");

      const link = row.getByRole("link", { name: `Download PDF for ${code} ${name}` });
      await expect(link).toHaveAttribute("href", `/api/v1/reports/renders/${jobId}/file`);
      const [download] = await Promise.all([pageA.waitForEvent("download"), link.click()]);
      expect(download.url()).toMatch(new RegExp(`/api/v1/reports/renders/${jobId}/file$`));
      expect(download.suggestedFilename()).toMatch(/^project-summary-internal-.+\.pdf$/);
      const bytes = await readFile(await download.path());
      expect(bytes.subarray(0, 4).toString()).toBe("%PDF");
      const sha256 = createHash("sha256").update(bytes).digest("hex");
      expect(sha256, "the download is the stored report").toBe(job?.pdfSha256);

      // Cross-tenant: B lists none of A's reports and gets a 404 for the download.
      await loginAs(pageB, users!.b);
      const listed = await apiCall(pageB, "GET", `/api/v1/reports/renders?q=${encodeURIComponent(code)}`);
      expect(listed.status).toBe(200);
      expect(listed.json!.items, "B lists none of A's reports").toEqual([]);
      const stolen = await pageB.request.get(`/api/v1/reports/renders/${jobId}/file`);
      expect(stolen.status(), "RLS: B's download of A's report is 404").toBe(404);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
