// TESTING-13 Part B (was APPROVALS-07, ADR 0035 §9): APPROVALS-02's workflow transition journeys,
// and the APPROVALS-05 preset journey, against a whole deployment (the compose stack in CI lane
// e2e-skeleton). The stack's approvals seed publishes the `demo` workflow in kaefer-demo, and the
// API serves the project-backed `demo` record type (AIP_APPROVALS_DEMO_RECORDS=1): a record is a
// project the journey creates, and its guard fact `allPhotosClean` is true once that project is
// active. The fixture admin (tenant_admin) holds the workflow's catalogue permissions.
//
// Not tagged @staging: the Coolify demo does not switch the demo record type on.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { CSRF_COOKIE, loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

type Json = Record<string, unknown>;

interface Decision {
  seq: number;
  action: string;
  entryHash: string;
  guardResult: { passed: boolean } | null;
}

interface History {
  entries: Decision[];
  chainValid: boolean;
}

interface Instance {
  id: string;
  currentState: string;
  syncVersion: number;
  availableTransitions: { action: string; labelKey: string; allowed: boolean; reasonKey: string | null }[];
}

/** POST/PATCH from inside the page, so the browser sends Origin and the app's CSRF header. */
async function apiJson(
  page: Page,
  method: "POST" | "PATCH",
  path: string,
  body: unknown,
): Promise<{ status: number; json: Json }> {
  return page.evaluate(
    async ({ method, path, body, csrfCookie }) => {
      const token = document.cookie
        .split("; ")
        .find((c) => c.startsWith(`${csrfCookie}=`))
        ?.slice(csrfCookie.length + 1);
      const response = await fetch(path, {
        method,
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": token ?? "" },
        body: JSON.stringify(body),
      });
      return { status: response.status, json: (await response.json()) as Record<string, unknown> };
    },
    { method, path, body, csrfCookie: CSRF_COOKIE },
  );
}

/** A fresh draft project: the `demo` record (and its guard switch) for one journey. */
async function createProject(page: Page, suffix: string): Promise<string> {
  const created = await apiJson(page, "POST", "/api/v1/projects", {
    code: `WF${suffix}-${runId()}`,
    name: `Workflow journey ${suffix}`,
  });
  expect(created.status, "setup: tenant A's admin creates the record's project").toBe(201);
  return created.json.id as string;
}

/** Move the project on through `statuses`; `active` is the fixture switch for allPhotosClean. */
async function moveProject(page: Page, id: string, statuses: string[]): Promise<void> {
  let version = ((await (await page.request.get(`/api/v1/projects/${id}`)).json()) as { syncVersion: number }).syncVersion;
  for (const status of statuses) {
    const patched = await apiJson(page, "PATCH", `/api/v1/projects/${id}`, { syncVersion: version, status });
    expect(patched.status, `the project moves to ${status}`).toBe(200);
    version = patched.json.syncVersion as number;
  }
}

/** Archive what is left (draft or active) so the demo register stays clean. */
async function archiveProject(page: Page, id: string): Promise<void> {
  const current = (await (await page.request.get(`/api/v1/projects/${id}`)).json()) as { status: string };
  const path = ["draft", "active", "closing", "archived"];
  const from = path.indexOf(current.status);
  if (from >= 0) await moveProject(page, id, path.slice(from + 1));
}

async function startDemo(page: Page, recordId: string, recordType = "demo"): Promise<Instance> {
  const started = await apiJson(page, "POST", "/api/v1/approvals/instances", { recordType, recordId });
  expect(started.status, `ADR 0035: tenant A starts the ${recordType} workflow on its own record`).toBe(201);
  return started.json as unknown as Instance;
}

async function transition(page: Page, instanceId: string, action: string): Promise<{ status: number; json: Json }> {
  return apiJson(page, "POST", `/api/v1/approvals/instances/${instanceId}/transition`, { action });
}

async function history(page: Page, instanceId: string): Promise<History> {
  const response = await page.request.get(`/api/v1/approvals/instances/${instanceId}/history`);
  expect(response.status(), "APPROVALS-02: the owning tenant reads the decision history").toBe(200);
  return (await response.json()) as History;
}

(users ? test.describe : test.describe.skip)("TESTING-13 workflow transition journeys", () => {
  test.describe.configure({ mode: "serial" });

  // One sign-in per user for the whole block: POST /auth/login/start allows 10 per minute per IP,
  // and the other @skeleton specs in the lane sign in too.
  let contextA: BrowserContext;
  let contextB: BrowserContext;
  let pageA: Page;
  let pageB: Page;
  const projects: string[] = [];

  test.beforeAll(async ({ browser }) => {
    contextA = await browser.newContext();
    contextB = await browser.newContext();
    pageA = await contextA.newPage();
    pageB = await contextB.newPage();
    await loginAs(pageA, users!.a);
    await loginAs(pageB, users!.b);
  });

  test.afterAll(async () => {
    for (const id of projects) await archiveProject(pageA, id);
    await contextA?.close();
    await contextB?.close();
  });

  test("@skeleton submit writes one chained decision; tenant B gets 404 for the history", async () => {
    const projectId = await createProject(pageA, "S");
    projects.push(projectId);
    const instance = await startDemo(pageA, projectId);
    expect(instance.currentState, "a new demo workflow starts in draft").toBe("draft");

    const submitted = await transition(pageA, instance.id, "submit");
    expect(submitted.status, "APPROVALS-02: submit is applied").toBe(200);
    expect((submitted.json.instance as Instance).currentState).toBe("submitted");

    const found = await history(pageA, instance.id);
    expect(found.entries, "APPROVALS-02: one decision per transition").toHaveLength(1);
    expect(found.entries[0]?.action).toBe("submit");
    expect(found.entries[0]?.entryHash, "APPROVALS-02: a sha256 entry hash").toMatch(/^[0-9a-f]{64}$/);
    expect(found.chainValid, "APPROVALS-02: the decision chain verifies").toBe(true);

    const asB = await pageB.request.get(`/api/v1/approvals/instances/${instance.id}/history`);
    expect(asB.status(), "ADR 0035: another tenant's instance is 404, not 403").toBe(404);
    const startAsB = await apiJson(pageB, "POST", "/api/v1/approvals/instances", {
      recordType: "demo",
      recordId: projectId,
    });
    expect(startAsB.status, "ADR 0035: tenant B cannot start a workflow on tenant A's record").toBe(404);
  });

  test("@skeleton approve is refused by its guard until the fixture flips allPhotosClean", async () => {
    const page = pageA;
    const projectId = await createProject(page, "G");
    projects.push(projectId);
    const instance = await startDemo(page, projectId);
    expect((await transition(page, instance.id, "submit")).status).toBe(200);

    const described = (await (await page.request.get(`/api/v1/approvals/instances/${instance.id}`)).json()) as Instance;
    const approve = described.availableTransitions.find((t) => t.action === "approve");
    expect(approve, "the submitted workflow offers approve").toBeDefined();
    expect(approve!.allowed, "APPROVALS-02 Part B: the guard is false while the photos are not clean").toBe(false);
    expect(approve!.reasonKey).toBe("workflow.demo.guard.photos_not_clean");

    const refused = await transition(page, instance.id, "approve");
    expect(refused.status, "APPROVALS-02 Part B: a false guard refuses the transition").toBe(422);
    expect(refused.json).toMatchObject({ code: "GUARD_FAILED", messageKey: "workflow.demo.guard.photos_not_clean" });
    expect((await history(page, instance.id)).entries, "a refused transition writes nothing").toHaveLength(1);

    await moveProject(page, projectId, ["active"]); // the fixture switch: allPhotosClean = true

    const approved = await transition(page, instance.id, "approve");
    expect(approved.status, "APPROVALS-02 Part B: once the guard holds, approve is applied").toBe(200);
    expect((approved.json.instance as Instance).currentState).toBe("approved");

    const found = await history(page, instance.id);
    expect(found.entries.map((e) => e.action)).toEqual(["submit", "approve"]);
    expect(found.entries[1]?.guardResult?.passed, "the decision records the guard that passed").toBe(true);
    expect(found.chainValid, "APPROVALS-02: the chain verifies after two decisions").toBe(true);
  });

  test("@skeleton an admin installs an inspection preset; a new inspection starts in draft with ready first", async () => {
    const page = pageA;
    const projectId = await createProject(page, "I");
    projects.push(projectId);
    const installed = await apiJson(page, "POST", "/api/v1/approvals/definitions/from-preset", {
      presetKey: "inspection_client_review",
      projectId,
    });
    expect(installed.status, "APPROVALS-05: the admin installs the client-review preset for a project").toBe(200);
    expect(installed.json).toMatchObject({ key: "inspection_client_review", projectId, status: "active" });

    const presets = (await (await page.request.get("/api/v1/approvals/presets")).json()) as { key: string }[];
    expect(presets.map((p) => p.key), "APPROVALS-05: both inspection presets are listed").toEqual(
      expect.arrayContaining(["inspection_standard", "inspection_client_review"]),
    );

    const instance = await startDemo(page, projectId, "inspection");
    expect(instance.currentState, "APPROVALS-05: a new inspection starts in draft").toBe("draft");
    expect(instance.availableTransitions[0]).toMatchObject({
      action: "ready",
      labelKey: "workflow.inspection.action.ready",
    });
  });
});
