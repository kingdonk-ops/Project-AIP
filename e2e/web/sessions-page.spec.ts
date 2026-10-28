// TESTING-12: the Active sessions page (IDENTITY-03) on every device project (desktop Chromium,
// mobile Chrome, iPad WebKit), on the Vite dev server with the session stub. The list API is
// answered with page.route; the real-session journey, the server's revocation and the cross-tenant
// check run against Keycloak in the skeleton lane (sessions.spec.ts).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { devBaseURL } from "../playwright.config";
import { signInAsStub } from "./stub-session";

test.use({ baseURL: process.env.E2E_DEV_URL ?? devBaseURL });

const CURRENT = "00000000-0000-7000-8000-0000000000c1";
const OTHER = "00000000-0000-7000-8000-0000000000c2";
const OTHER_DEVICE = "Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0";

function session(id: string, userAgent: string | null, current: boolean) {
  return {
    id,
    audience: "staff",
    aal: 1,
    ip: current ? "203.0.113.10" : "198.51.100.7",
    userAgent,
    createdAt: "2026-10-27T01:00:00Z",
    lastSeenAt: "2026-10-28T02:30:00Z",
    current,
  };
}

/** A fake of GET /me/sessions and DELETE /me/sessions/{id} that honours the revocation. */
async function serveSessions(page: Page): Promise<string[]> {
  const live = [session(CURRENT, "Playwright browser", true), session(OTHER, OTHER_DEVICE, false)];
  const revoked: string[] = [];
  await page.route(
    (url) => url.pathname === "/api/v1/me/sessions",
    (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: live.filter((s) => !revoked.includes(s.id)) }) }),
  );
  await page.route(
    (url) => url.pathname.startsWith("/api/v1/me/sessions/"),
    (route) => {
      if (route.request().method() !== "DELETE") return route.fallback();
      revoked.push(route.request().url().split("/").pop() ?? "");
      return route.fulfill({ status: 204 });
    },
  );
  return revoked;
}

test("Active sessions: open it from the Account menu, see this device, sign another out; axe clean", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  const revoked = await serveSessions(page);
  await page.goto("/projects");
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Active sessions" }).click();
  await expect(page).toHaveURL(/\/settings\/profile\/sessions$/);
  await expect(page.getByRole("heading", { name: "Active sessions", level: 1 })).toBeVisible();

  const table = page.getByRole("table", { name: "Active sessions" });
  await expect(table.getByRole("row")).toHaveCount(3); // header + two sessions
  const current = table.getByRole("row").filter({ hasText: "(This device)" });
  await expect(current).toHaveCount(1);
  await expect(current).toContainText("203.0.113.10");
  const other = table.getByRole("row").filter({ hasText: OTHER_DEVICE });
  await expect(other).toHaveCount(1);
  await expectNoBlockingAxe(page);

  await page.getByRole("button", { name: `Sign out the session on ${OTHER_DEVICE}`, exact: true }).click();
  await expect(other).toHaveCount(0);
  await expect(current).toHaveCount(1);
  expect(revoked).toEqual([OTHER]);
});

test("Active sessions: a failed revocation says so and keeps the row", async ({ page }) => {
  await signInAsStub(page, "alice@kaefer.test");
  await serveSessions(page);
  await page.route(
    (url) => url.pathname === `/api/v1/me/sessions/${OTHER}`,
    (route) => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
  );
  await page.goto("/settings/profile/sessions");
  await page.getByRole("button", { name: `Sign out the session on ${OTHER_DEVICE}`, exact: true }).click();
  await expect(page.getByText("That session could not be signed out. Try again.")).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: OTHER_DEVICE })).toHaveCount(1);
  await expectNoBlockingAxe(page);
});

async function expectNoBlockingAxe(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking).toEqual([]);
}
