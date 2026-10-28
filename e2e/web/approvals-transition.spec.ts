// TESTING-13 Part B (was APPROVALS-07, carried forward from APPROVALS-02 by ADR 0035 §9): the two
// workflow transition API journeys against a whole deployment. The compose stack's
// `approvals-seed` one-shot publishes the dev-only `demo` workflow (record type `approvals_demo`)
// in kaefer-demo with real catalogue permissions (approvals.start / approvals.design, both held by
// the fixture admin through tenant_admin); its `approve` is critical and guarded by
// `record.allPhotosClean`, which the dev-only fixture switch flips. Runs in CI lane e2e-skeleton
// (`--project web`). Not @staging: the Coolify demo does not run the seed.
import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { CSRF_COOKIE, loginAs } from "../fixtures/login";
import { tenantUsers } from "../fixtures/tenants";

const users = tenantUsers();
const RECORD_TYPE = "approvals_demo";
const HEX64 = /^[0-9a-f]{64}$/;

test.describe.configure({ mode: "serial" });

interface ApiReply {
  status: number;
  json: Record<string, unknown>;
}

/** Call the API from inside the page, so the browser sends Origin and the CSRF header like the app. */
async function api(page: Page, method: string, path: string, body?: unknown): Promise<ApiReply> {
  return page.evaluate(
    async ({ method, path, body, csrfCookie }) => {
      const token = document.cookie
        .split("; ")
        .find((c) => c.startsWith(`${csrfCookie}=`))
        ?.slice(csrfCookie.length + 1);
      const init: RequestInit = {
        method,
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": token ?? "" },
      };
      if (body !== undefined) init.body = JSON.stringify(body);
      const response = await fetch(path, init);
      const text = await response.text();
      return { status: response.status, json: (text ? JSON.parse(text) : {}) as Record<string, unknown> };
    },
    { method, path, body, csrfCookie: CSRF_COOKIE },
  );
}

async function startDemo(page: Page): Promise<{ id: string; recordId: string }> {
  const started = await api(page, "POST", "/api/v1/approvals/instances", {
    recordType: RECORD_TYPE,
    recordId: randomUUID(),
  });
  expect(started.status, `APPROVALS-07: the submitter starts a demo workflow: ${JSON.stringify(started.json)}`).toBe(201);
  expect(started.json.definitionKey, "APPROVALS-07: the seeded demo workflow is used").toBe("demo");
  expect(started.json.currentState).toBe("draft");
  return { id: started.json.id as string, recordId: started.json.recordId as string };
}

async function transition(page: Page, id: string, action: string): Promise<ApiReply> {
  return api(page, "POST", `/api/v1/approvals/instances/${id}/transition`, { action });
}

test("@skeleton submit writes one hash-chained decision; another tenant gets 404", async ({ browser }) => {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();
  const pageA = await contextA.newPage();
  const pageB = await contextB.newPage();
  try {
    await loginAs(pageA, users.a);
    const instance = await startDemo(pageA);

    const submitted = await transition(pageA, instance.id, "submit");
    expect(submitted.status, `APPROVALS-02: submit takes effect: ${JSON.stringify(submitted.json)}`).toBe(200);

    const history = await api(pageA, "GET", `/api/v1/approvals/instances/${instance.id}/history`);
    expect(history.status).toBe(200);
    const entries = history.json.entries as { entryHash: string; action: string }[];
    expect(entries, "APPROVALS-02: one decision is recorded").toHaveLength(1);
    const [entry] = entries;
    expect(entry?.action).toBe("submit");
    expect(entry?.entryHash, "APPROVALS-02: the decision carries a sha256 entry hash").toMatch(HEX64);
    expect(history.json.chainValid, "APPROVALS-02: the decision chain verifies").toBe(true);

    await loginAs(pageB, users.b);
    const asB = await api(pageB, "GET", `/api/v1/approvals/instances/${instance.id}/history`);
    expect(asB.status, "APPROVALS-02: another tenant's instance history is 404").toBe(404);
  } finally {
    await contextA.close();
    await contextB.close();
  }
});

test("@skeleton the guard refuses approve until the fixture flips allPhotosClean", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    // A fresh sign-in: the demo's sign-off policy (approvals.demo_approve) wants one within 10 min.
    await loginAs(page, users.a);
    const instance = await startDemo(page);
    expect((await transition(page, instance.id, "submit")).status).toBe(200);

    const refused = await transition(page, instance.id, "approve");
    expect(refused.status, "APPROVALS-02: a false guard refuses the transition").toBe(422);
    expect(refused.json.code).toBe("GUARD_FAILED");

    const flipped = await api(page, "PUT", `/api/v1/approvals/demo-records/${instance.recordId}/facts`, {
      allPhotosClean: true,
    });
    expect(flipped.status, "the dev-only fixture switch sets allPhotosClean").toBe(204);

    const approved = await transition(page, instance.id, "approve");
    expect(approved.status, `APPROVALS-02: approve takes effect once the guard passes: ${JSON.stringify(approved.json)}`).toBe(200);
    expect((approved.json.instance as { currentState: string }).currentState).toBe("approved");

    const history = await api(page, "GET", `/api/v1/approvals/instances/${instance.id}/history`);
    const entries = history.json.entries as { action: string }[];
    expect(entries.map((e) => e.action)).toEqual(["submit", "approve"]);
    expect(history.json.chainValid, "APPROVALS-02: the chain still verifies after approve").toBe(true);
  } finally {
    await context.close();
  }
});
