// DESIGN-02: signs a page in through the dev-only session stub (apps/web/src/features/shell/dev).
// The stub exists only in the Vite dev server (VITE_AIP_DEV_SESSION=stub), never in a production
// build. Real sessions exist (IDENTITY-03): journeys that need the API use loginAs (fixtures/login.ts)
// in the skeleton lane; the stub stays for what the browser alone decides.
import type { Page } from "@playwright/test";

export async function signInAsStub(page: Page, email: string): Promise<void> {
  // DESIGN-15: the shell reads the release flags on every page. The stub has no API session, so the real
  // API would answer 401; answer "every flag off" instead. A spec that routes the flags API itself
  // registers later, and Playwright tries the most recent route first.
  await page.route("**/api/v1/settings/flags", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ flags: [{ flag: "ai", enabled: false }, { flag: "bim", enabled: false }] }),
    }),
  );
  await page.addInitScript((value) => {
    // Seed once per tab so that signing out (which clears the key) is not undone by the next navigation.
    if (window.sessionStorage.getItem("e2e-stub-seeded")) return;
    window.sessionStorage.setItem("e2e-stub-seeded", "1");
    window.localStorage.setItem("aip.dev-session-stub", value);
  }, email);
}
