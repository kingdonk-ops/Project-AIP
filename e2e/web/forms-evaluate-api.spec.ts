// FORMS-02: the form evaluate API end to end. A kaefer-demo admin uploads and publishes a coating
// template, then evaluates a below-threshold DFT answer: the server returns the shared
// AnswerEvaluation and the measurement shows up in `failed`. A tenant-b user evaluating the same
// revision is refused with a 404 (RLS hides it). The evaluator has no page in R1 — FORMS-03 renders
// it and runs the axe check — so there is no accessibility assertion here.
//
// Like the other journey specs, this runs only where the fixture credentials and a real stack exist
// (E2E_USER_*/E2E_PASS_*); without them the suite skips. It runs in the `web` skeleton project.
import { expect, test, type Page } from "@playwright/test";
import { CSRF_COOKIE, loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

// A coating ITR whose DFT fails below 0.25 mm, so a 0.18 answer lands in `failed`.
const SCHEMA = {
  schemaVersion: 1,
  sections: [
    {
      key: "coating",
      label: "Coating",
      fields: [
        {
          key: "dft_avg",
          type: "measurement",
          label: "Average DFT",
          unit: "mm",
          failWhen: { "<": [{ var: "answers.dft_avg.value" }, 0.25] },
        },
      ],
    },
  ],
};

async function apiJson(
  page: Page,
  method: "POST",
  path: string,
  body: unknown,
): Promise<{ status: number; json: Record<string, unknown> }> {
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

(users ? test.describe : test.describe.skip)("FORMS-02 evaluate API journey", () => {
  test("@skeleton tenant A evaluates a failing DFT; tenant B cannot reach the revision", async ({
    browser,
  }) => {
    const u = users!;
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    try {
      await loginAs(pageA, u.a);

      // (a) Upload and publish a template.
      const code = `coating-itr-${runId()}`.slice(0, 63);
      const created = await apiJson(pageA, "POST", "/api/v1/forms/templates", {
        code,
        name: "Coating ITR (evaluate e2e)",
        kind: "inspection",
        schema: SCHEMA,
      });
      expect(created.status, "the template is created").toBe(201);
      const revisionId = (created.json.revision as Record<string, unknown>).id as string;
      const published = await apiJson(
        pageA,
        "POST",
        `/api/v1/forms/revisions/${revisionId}/publish`,
        {},
      );
      expect(published.status, "publish succeeds").toBe(200);

      // (b) Evaluate a below-threshold DFT: the measurement fails.
      const evaluated = await apiJson(
        pageA,
        "POST",
        `/api/v1/forms/revisions/${revisionId}/evaluate`,
        { answers: { dft_avg: { value: 0.18, unit: "mm" } }, mode: "submit" },
      );
      expect(evaluated.status, "evaluate answers 200").toBe(200);
      expect(evaluated.json.failed as string[]).toContain("dft_avg");

      // (c) A tenant-b user cannot evaluate tenant A's revision: RLS hides it as a 404.
      await loginAs(pageB, u.b);
      const denied = await apiJson(
        pageB,
        "POST",
        `/api/v1/forms/revisions/${revisionId}/evaluate`,
        { answers: {}, mode: "submit" },
      );
      expect(denied.status, "tenant B is refused the revision").toBe(404);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
