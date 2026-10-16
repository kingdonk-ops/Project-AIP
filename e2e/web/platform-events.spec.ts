// ARCH-09: the event catalogue, event detail and dead-letter pages for platform operators. The stub
// session (Vite dev server) supplies the operator fixture; the admin API is mocked with page.route
// (stateful, so retry, discard and deprecate change what the next GET returns), because the default
// e2e run has no API session holding platform.events.manage. The API's own permission, RLS and
// SECURITY DEFINER behaviour is covered by its pytest suites (ARCH-06, ARCH-07).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

const OPERATOR = "operator@kaefer.test";
const BASE = "/api/v1/admin/platform/events";

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
}

interface State {
  status: "active" | "deprecated";
  deadLetters: { id: string; eventName: string; eventVersion: number; tenantId: string; attempts: number; lastError: string; deadLetteredAt: string }[];
  discardReasons: string[];
  adminCalls: number;
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockAdminApi(page: Page): Promise<State> {
  const state: State = {
    status: "active",
    deadLetters: ["0192f0c1-0000-7000-8000-000000000001", "0192f0c1-0000-7000-8000-000000000002"].map((id) => ({
      id,
      eventName: "project.created",
      eventVersion: 1,
      tenantId: "00000000-0000-4000-8000-00000000000a",
      attempts: 10,
      lastError: "TimeoutError: subscriber audit",
      deadLetteredAt: "2026-10-16T02:00:00Z",
    })),
    discardReasons: [],
    adminCalls: 0,
  };
  const events = () => [
    { name: "project.created", version: 1, module: "projects", status: state.status, subscribers: ["audit"], published24h: 12, failed24h: 2 },
    { name: "tenant.entitlements_changed", version: 1, module: "tenancy", status: "active", subscribers: [], published24h: 3, failed24h: 0 },
  ];
  await page.route(`**${BASE}**`, async (route) => {
    state.adminCalls += 1;
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() === "GET" && path === BASE) {
      const module = url.searchParams.get("module");
      return json(route, { events: events().filter((e) => !module || e.module === module) });
    }
    if (request.method() === "GET" && path === `${BASE}/dead-letter`) {
      return json(route, { items: state.deadLetters, nextAfter: null });
    }
    const action = path.match(/\/dead-letter\/([^/]+)\/(retry|discard)$/);
    if (action && request.method() === "POST") {
      const [, id, verb] = action;
      if (!state.deadLetters.some((d) => d.id === id)) return json(route, { detail: "not found" }, 404);
      if (verb === "discard") state.discardReasons.push((request.postDataJSON() as { reason: string }).reason);
      state.deadLetters = state.deadLetters.filter((d) => d.id !== id);
      return json(route, { id, eventName: "project.created", eventVersion: 1, action: verb === "retry" ? "retried" : "discarded" });
    }
    if (request.method() === "POST" && path === `${BASE}/project.created/versions/1/deprecate`) {
      state.status = "deprecated";
      return json(route, { name: "project.created", version: 1, status: "deprecated", deprecatedAt: "2026-10-16T03:00:00Z", deprecatedBy: null });
    }
    if (request.method() === "GET" && path === `${BASE}/project.created`) {
      return json(route, {
        name: "project.created",
        versions: [
          {
            version: 1,
            status: state.status,
            subscribers: ["audit"],
            schema: { title: "ProjectEvent", type: "object", properties: { projectId: { type: "string", format: "uuid" } } },
          },
        ],
      });
    }
    return json(route, { detail: "not mocked" }, 500);
  });
  return state;
}

test("an operator filters the catalogue, reads a schema and deprecates a version", async ({ page }) => {
  await mockAdminApi(page);
  await signInAsStub(page, OPERATOR);
  await page.goto("/admin/platform/events");
  await expect(page.getByRole("heading", { name: "Domain event catalogue", level: 1 })).toBeVisible();
  const table = page.getByRole("table", { name: "Domain events" });
  await expect(table.getByRole("row", { name: /tenant\.entitlements_changed/ })).toBeVisible();
  await expectNoBlockingAxe(page);

  await page.getByLabel("Module", { exact: true }).selectOption("projects");
  await expect(page).toHaveURL(/module=projects/);
  await expect(table.getByRole("row", { name: /tenant\.entitlements_changed/ })).toHaveCount(0);

  await table.getByRole("link", { name: "Open project.created version 1" }).click();
  await expect(page.getByRole("heading", { name: "project.created", level: 1 })).toBeVisible();
  const version = page.getByRole("region", { name: "Version 1" });
  await expect(version.getByText('"ProjectEvent"')).toBeVisible();
  await expectNoBlockingAxe(page);

  await version.getByRole("button", { name: "Deprecate" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Deprecate version" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("project.created version 1 is now deprecated.")).toBeVisible();
  await expect(version.getByText("Deprecated")).toBeVisible();
  await expect(version.getByRole("button", { name: "Deprecate" })).toHaveCount(0);
});

test("an operator retries one dead letter and discards another with a reason, by keyboard", async ({ page }) => {
  const state = await mockAdminApi(page);
  await signInAsStub(page, OPERATOR);
  await page.goto("/admin/platform/events/dead-letter");
  const table = page.getByRole("table", { name: "Dead-lettered events" });
  const [first, second] = state.deadLetters.map((d) => d.id);
  await expect(table.getByRole("row", { name: new RegExp(first!) })).toBeVisible();
  await expectNoBlockingAxe(page);

  await table.getByRole("button", { name: `Retry event ${first}` }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("The event was sent back for delivery.")).toBeVisible();
  await expect(table.getByRole("row", { name: new RegExp(first!) })).toHaveCount(0);

  await table.getByRole("button", { name: `Discard event ${second}` }).focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Discard event" })).toBeDisabled();
  await dialog.getByLabel("Reason").fill("Duplicate delivery, raised INC-42");
  await dialog.getByLabel("Reason").press("Tab");
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Discard event" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("The event was discarded.")).toBeVisible();
  await expect(page.getByText("Nothing matches these filters.")).toBeVisible();
  expect(state.discardReasons).toEqual(["Duplicate delivery, raised INC-42"]);
  await expectNoBlockingAxe(page);
});

for (const email of ["alice@kaefer.test", "bob@acme.test"]) {
  test(`${email} sees no event nav entries and a 403 state on every page`, async ({ page }) => {
    const state = await mockAdminApi(page);
    await signInAsStub(page, email);
    for (const path of ["/admin/platform/events", "/admin/platform/events/project.created", "/admin/platform/events/dead-letter"]) {
      await page.goto(path);
      await expect(page.getByRole("alert")).toContainText("You don’t have access");
      await expect(page.getByRole("link", { name: "Domain events" })).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Dead letters" })).toHaveCount(0);
    }
    await expectNoBlockingAxe(page);
    expect(state.adminCalls).toBe(0);
  });
}
