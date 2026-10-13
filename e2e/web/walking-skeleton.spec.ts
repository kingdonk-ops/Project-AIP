// TESTING-09: the M0 exit proof (ADR 0007). A kaefer-demo admin signs in for real and creates a
// project; a tenant-b admin signs in and can neither see nor fetch it; the creator can, and archives
// it afterwards so the demo does not fill up. Runs against the compose stack in CI (`--project web`)
// and against the Coolify demo after each deploy (`--project staging`). No fixed sleeps: every wait
// is a web-first assertion, and each assertion names the M0 property it proves.
import { expect, test, type Page } from "@playwright/test";
import { CSRF_COOKIE, loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const users = tenantUsers();
const code = `E2E-${runId()}`;
const name = "Walking skeleton";

test.describe.configure({ mode: "serial" });

let projectId = "";

/** PATCH a project from inside the page, so the browser sends Origin and the CSRF header like the app. */
async function patchProject(page: Page, id: string, body: Record<string, unknown>): Promise<{ status: number; json: Record<string, unknown> }> {
  return page.evaluate(
    async ({ id, body, csrfCookie }) => {
      const token = document.cookie
        .split("; ")
        .find((c) => c.startsWith(`${csrfCookie}=`))
        ?.slice(csrfCookie.length + 1);
      const response = await fetch(`/api/v1/projects/${id}`, {
        method: "PATCH",
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": token ?? "" },
        body: JSON.stringify(body),
      });
      return { status: response.status, json: (await response.json()) as Record<string, unknown> };
    },
    { id, body, csrfCookie: CSRF_COOKIE },
  );
}

test("@skeleton @staging tenant A creates a project, tenant B cannot see or fetch it", async ({ browser }) => {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();
  try {
    // (a) A signs in, creates E2E-<runId> and sees it as Draft in the register.
    await loginAs(pageA, users.a);
    await pageA.goto("/projects");
    await pageA.getByRole("link", { name: "Create project" }).click();
    await pageA.getByLabel("Project code").fill(code);
    await pageA.getByLabel("Name").fill(name);
    const created = pageA.waitForResponse(
      (r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v1/projects",
    );
    await pageA.getByRole("button", { name: "Create project" }).click();
    const response = await created;
    expect(response.status(), "M0: tenant A's admin can create a project").toBe(201);
    projectId = ((await response.json()) as { id: string }).id;
    expect(projectId).toMatch(/^[0-9a-f-]{36}$/);

    await expect(pageA.getByText(`Project ${code} was created.`)).toBeVisible();
    await pageA.getByLabel("Search code or name").fill(code);
    const rowA = pageA.getByRole("row").filter({ hasText: code });
    await expect(rowA, "M0: the creator sees the new project in the register").toHaveCount(1);
    await expect(rowA.getByText("Draft"), "M0: a new project starts as Draft").toBeVisible();

    // (b) B signs in (own browser context) and the register does not show A's project.
    await loginAs(pageB, users.b);
    await pageB.goto("/projects");
    await expect(pageB.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
    await expect(
      pageB.getByRole("row").filter({ hasText: code }),
      "M0: tenant B's register does not contain tenant A's project",
    ).toHaveCount(0);
    await pageB.getByLabel("Search code or name").fill(code);
    await expect(
      pageB.getByText("No projects match these filters."),
      "M0: tenant B's search for tenant A's project finds nothing",
    ).toBeVisible();

    // (c) B fetching A's project by id is 404: not 403 (which would confirm it exists), not 200.
    const asB = await pageB.request.get(`/api/v1/projects/${projectId}`);
    expect(asB.status(), "M0: another tenant's project id is 404 for tenant B").toBe(404);

    // (d) A fetching the same id is 200.
    const asA = await pageA.request.get(`/api/v1/projects/${projectId}`);
    expect(asA.status(), "M0: the owning tenant can read its project").toBe(200);
  } finally {
    // (e) A archives the project (draft -> active -> closing -> archived) so the demo stays clean.
    if (projectId) {
      let version = ((await (await pageA.request.get(`/api/v1/projects/${projectId}`)).json()) as { syncVersion: number }).syncVersion;
      for (const status of ["active", "closing", "archived"]) {
        const patched = await patchProject(pageA, projectId, { syncVersion: version, status });
        expect(patched.status, `cleanup: the project moves to ${status}`).toBe(200);
        version = patched.json.syncVersion as number;
      }
    }
    await contextA.close();
    await contextB.close();
  }
});
