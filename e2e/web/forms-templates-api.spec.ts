// FORMS-01: the form-template API end to end against a whole deployment (the compose stack in CI,
// the Coolify demo after a deploy). A kaefer-demo admin uploads a template, lints a broken schema,
// and publishes a revision (which freezes it with a sha256 hash); a tenant-b user cannot read that
// revision. There is no page in this task (the register and designer arrive in FORMS-04), so no
// axe check here.
//
// Like the other journey specs, this runs only where the fixture credentials and a real stack
// exist (E2E_USER_*/E2E_PASS_*); without them the suite skips. It runs in the `web` skeleton
// project (tagged @skeleton).
import { expect, test, type Page } from "@playwright/test";
import { CSRF_COOKIE, loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;

// A minimal valid coating ITR: one section, a boolean and a measurement in millimetres.
const SCHEMA = {
  schemaVersion: 1,
  sections: [
    {
      key: "preparation",
      label: "Surface preparation",
      fields: [
        { key: "surface_prepared", type: "boolean", label: "Surface prepared" },
        { key: "dft_avg", type: "measurement", label: "Average DFT", unit: "mm" },
      ],
    },
  ],
};

// The same shape, but with a field type the registry does not have.
const BAD_SCHEMA = {
  schemaVersion: 1,
  sections: [
    {
      key: "s",
      label: "S",
      fields: [{ key: "scan", type: "barcode", label: "Barcode" }],
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

(users ? test.describe : test.describe.skip)("FORMS-01 template API journey", () => {
  test("@skeleton tenant A uploads, lints and publishes; tenant B cannot read the revision", async ({
    browser,
  }) => {
    const u = users!;
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    try {
      await loginAs(pageA, u.a);

      // (a) Upload a draft template.
      const code = `coating-itr-${runId()}`.slice(0, 63);
      const created = await apiJson(pageA, "POST", "/api/v1/forms/templates", {
        code,
        name: "Coating ITR (e2e)",
        kind: "inspection",
        schema: SCHEMA,
      });
      expect(created.status, "the template is created").toBe(201);
      const revision = created.json.revision as Record<string, unknown>;
      const revisionId = revision.id as string;
      expect(revisionId).toMatch(/^[0-9a-f-]{36}$/);

      // (b) Lint a broken schema without writing: one UNKNOWN_FIELD_TYPE issue.
      const linted = await apiJson(pageA, "POST", "/api/v1/forms/lint", { schema: BAD_SCHEMA });
      expect(linted.status, "lint answers 200").toBe(200);
      const issues = linted.json.issues as Array<Record<string, unknown>>;
      expect(issues).toHaveLength(1);
      expect(issues[0]!.code).toBe("UNKNOWN_FIELD_TYPE");

      // (c) Publish the revision: it freezes with a 64-hex sha256 hash.
      const published = await apiJson(
        pageA,
        "POST",
        `/api/v1/forms/revisions/${revisionId}/publish`,
        {},
      );
      expect(published.status, "publish succeeds").toBe(200);
      const publishedRevision = published.json.revision as Record<string, unknown>;
      expect(publishedRevision.status).toBe("published");
      expect(publishedRevision.schemaHash as string).toMatch(/^[0-9a-f]{64}$/);

      // (d) A tenant-b user cannot read tenant A's revision: RLS hides it as a 404.
      await loginAs(pageB, u.b);
      const denied = await pageB.request.get(`/api/v1/forms/revisions/${revisionId}`);
      expect(denied.status(), "tenant B is refused the revision").toBe(404);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
