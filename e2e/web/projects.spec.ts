// PROJECTS-02: the projects register and create form. The stub session (Vite dev server) covers
// what the browser alone decides: permissions gate the page. Creating a project needs a real API
// session and a user holding project.create, so those journeys wait for IDENTITY-03 (sessions)
// and ACCESS-02 (roles); the component tests in apps/web cover them until then.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}

test("a user without project.create sees the register without a Create button", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/projects?status=active");
  await expect(page.getByRole("heading", { name: "Projects", level: 1 })).toBeVisible();
  await expect(page.getByLabel("Status")).toHaveValue("active");
  await expect(page.getByRole("link", { name: "Create project" })).toHaveCount(0);
  await expect(page).toHaveURL(/\/projects\?status=active$/);
  await expectNoBlockingAxe(page);
});

test("visiting /projects/new without project.create shows the permission-denied state", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await page.goto("/projects/new");
  await expect(page.getByRole("heading", { name: "You do not have permission to create projects." })).toBeVisible();
  await expect(page.getByLabel("Project code")).toHaveCount(0);
  await expectNoBlockingAxe(page);
});

test("@needs-identity-03 the kaefer-demo admin creates a project and sees it as Draft", () => {
  test.skip(true, "needs IDENTITY-03 (API sessions) and ACCESS-02 (a role holding project.create)");
});

test("@needs-identity-03 the server answers 403 to a user without project.create", () => {
  test.skip(true, "needs IDENTITY-03 (API sessions) and ACCESS-02 (seeded roles)");
});
