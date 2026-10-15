// UPLOADS-01: the presign journey end to end against a whole deployment (the compose stack in CI,
// the Coolify demo after a deploy). A kaefer-demo user creates an upload session, uploads
// e2e/fixtures/photo.jpg straight to the quarantine bucket through the server-issued presigned
// POST, and confirms — GET status then reads `uploaded`. A tenant-b user replaying the same
// presigned fields with a changed key is refused by the store, so nothing is written outside the
// one `tenant/<A>/quarantine/<token>` key the server signed.
//
// Like the walking skeleton, this runs only where the fixture credentials and a real stack exist
// (E2E_USER_*/E2E_PASS_*, and usually E2E_BASE_URL). Without them — the default `vite preview`
// lane — the whole suite skips, because the bytes go to a real object store, not the app.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { CSRF_COOKIE, loginAs } from "../fixtures/login";
import { runId } from "../fixtures/run-id";
import { tenantUsers } from "../fixtures/tenants";

const haveCredentials = Boolean(process.env.E2E_USER_A && process.env.E2E_USER_B);
const users = haveCredentials ? tenantUsers() : null;
const photo = readFileSync(fileURLToPath(new URL("../fixtures/photo.jpg", import.meta.url)));

interface SessionCreated {
  sessionId: string;
  url: string;
  fields: Record<string, string>;
  expiresAt: string;
}

/** POST/PATCH from inside the page, so the browser sends Origin and the app's CSRF header. */
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

/** Send a presigned browser POST to the object store (a different origin), with the file last. */
async function postToStore(
  page: Page,
  url: string,
  fields: Record<string, string>,
  file: Buffer,
): Promise<number> {
  const response = await page.request.post(url, {
    multipart: { ...fields, file: { name: "photo.jpg", mimeType: "image/jpeg", buffer: file } },
  });
  return response.status();
}

(users ? test.describe : test.describe.skip)("UPLOADS-01 presign journey", () => {
  test.describe.configure({ mode: "serial" });

  test("tenant A uploads to quarantine and confirms; tenant B's key tamper is refused", async ({
    browser,
  }) => {
    const u = users!;
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    try {
      await loginAs(pageA, u.a);

      // A project in tenant A to upload into (also proves the creator has project scope).
      const project = await apiJson(pageA, "POST", "/api/v1/projects", {
        code: `UPL-${runId()}`.slice(0, 32),
        name: "Uploads e2e",
      });
      expect(project.status, "a project is created to upload into").toBe(201);
      const projectId = project.json.id as string;

      // (a) Create the upload session.
      const created = await apiJson(pageA, "POST", "/api/v1/uploads/sessions", {
        projectId,
        filename: "photo.jpg",
        declaredMime: "image/jpeg",
        sizeBytes: photo.byteLength,
      });
      expect(created.status, "the upload session is created").toBe(201);
      const session = created.json as unknown as SessionCreated;
      expect(session.sessionId).toMatch(/^[0-9a-f-]{36}$/);

      // (b) Upload straight to the quarantine bucket through the presigned POST.
      const ok = await postToStore(pageA, session.url, session.fields, photo);
      expect([200, 204], "the store accepts the presigned upload").toContain(ok);

      // (c) Confirm, then read the status.
      const confirmed = await apiJson(
        pageA,
        "POST",
        `/api/v1/uploads/sessions/${session.sessionId}/confirm`,
        {},
      );
      expect(confirmed.status, "confirm succeeds").toBe(200);
      expect(confirmed.json.status).toBe("uploaded");

      const status = await pageA.request.get(
        `/api/v1/uploads/sessions/${session.sessionId}/status`,
      );
      expect(status.status()).toBe(200);
      expect((await status.json()).status).toBe("uploaded");

      // (d) Tenant B replays the exact same presigned fields with a changed key: the signed policy
      // pins the key, so the store refuses it and nothing lands outside the signed quarantine key.
      await loginAs(pageB, u.b);
      const originalKey = session.fields.key;
      expect(originalKey, "the presigned fields pin a key").toBeTruthy();
      const tamperedKey = originalKey!.replace(/\/[^/]+$/, "/tenant-b-attempt");
      expect(tamperedKey).not.toBe(originalKey);
      const refused = await postToStore(pageB, session.url, { ...session.fields, key: tamperedKey }, photo);
      expect([400, 403], "the store refuses a changed key").toContain(refused);
    } finally {
      await contextA.close();
      await contextB.close();
    }
  });
});
