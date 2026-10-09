// DESIGN-02: signs a page in through the dev-only session stub (apps/web/src/features/shell/dev).
// The stub exists only in the Vite dev server (VITE_AIP_DEV_SESSION=stub), never in a production
// build, and goes away when IDENTITY-03 issues real sessions (then use a real Keycloak login).
import type { Page } from "@playwright/test";

export async function signInAsStub(page: Page, email: string): Promise<void> {
  await page.addInitScript((value) => {
    // Seed once per tab so that signing out (which clears the key) is not undone by the next navigation.
    if (window.sessionStorage.getItem("e2e-stub-seeded")) return;
    window.sessionStorage.setItem("e2e-stub-seeded", "1");
    window.localStorage.setItem("aip.dev-session-stub", value);
  }, email);
}
