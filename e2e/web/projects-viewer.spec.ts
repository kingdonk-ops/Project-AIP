// TESTING-12 Part B (was QA-3, review 11 M12): a real kaefer-demo viewer (the seeded read-only
// `auditor`, no `project.create`) and the server-enforced 403 on project create, with a real session.
// The UI hides the form from a user without `project.create`, so the 403 branch is reached the way
// it happens in production: the browser's abilities are stale (here the abilities response is
// widened in the browser only) and the API, which decides alone, refuses the POST.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { viewerUser } from "../fixtures/tenants";

const ABILITIES = "/api/v1/access/me/abilities";

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

test("@skeleton @staging @viewer a viewer without project.create is refused by the server and no project is created", async ({ page }) => {
  const viewer = viewerUser();
  const code = `E2E-V-${runId()}`;
  await loginAs(page, viewer);

  // ACCESS-01: the viewer's real abilities read projects but do not create them.
  const abilities = await page.request.get(ABILITIES);
  expect(abilities.status()).toBe(200);
  const permissions = ((await abilities.json()) as { permissions: string[] }).permissions;
  expect(permissions, "ACCESS-02: the seeded viewer can read projects").toContain("project.view");
  expect(permissions, "ACCESS-02: the seeded viewer cannot create projects").not.toContain("project.create");

  // The register has no Create button and /projects/new shows the denied state (the client's view).
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Create project" }), "PROJECTS-06: no Create button without project.create").toHaveCount(0);
  await page.goto("/projects/new");
  await expect(page.getByRole("heading", { name: "You do not have permission to create projects." })).toBeVisible();

  // Stale abilities: the browser believes it may create, so the form is shown and posts for real.
  const isAbilities = (url: URL) => url.pathname === ABILITIES;
  await page.route(
    isAbilities,
    async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as { permissions: string[] };
      await route.fulfill({ response, json: { ...body, permissions: [...body.permissions, "project.create"] } });
    },
  );
  await page.goto("/projects/new");
  await page.getByLabel("Project code").fill(code);
  await page.getByLabel("Name").fill("Viewer denied");
  const posted = page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v1/projects");
  await page.getByRole("button", { name: "Create project" }).click();
  expect((await posted).status(), "ACCESS-01: the API refuses project create without project.create").toBe(403);

  await expect(
    page.getByRole("heading", { name: "You do not have permission to create projects." }),
    "PROJECTS-06: the server's 403 is shown as the permission message",
  ).toBeVisible();
  await expect(page.getByLabel("Project code"), "PROJECTS-06: the form is gone after the 403").toHaveCount(0);
  await expectNoBlockingAxe(page);
  await page.unroute(isAbilities);

  // Nothing was created: the viewer (who can read the whole register) finds no such project.
  const search = await page.request.get(`/api/v1/projects?q=${encodeURIComponent(code)}`);
  expect(search.status()).toBe(200);
  const items = ((await search.json()) as { items: { code: string }[] }).items;
  expect(items.filter((p) => p.code === code), "ACCESS-01: the refused create left no project").toEqual([]);
});
