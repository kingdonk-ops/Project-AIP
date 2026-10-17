// DESIGN-14 (review 11 M14): a 60-character company name never pushes the header controls off
// screen, at 1440px and at 390px. Runs on the production build (`vite preview`) with GET /api/v1/me
// and the abilities call answered by page.route, so the tenant name can be one no fixture has.
import { expect, test, type Page } from "@playwright/test";

const LONG_NAME = "Kaefer Integrated Services, Insulation Scaffolding Australia";

async function signInWithTenantName(page: Page, name: string): Promise<void> {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({
      json: {
        aal: 2,
        amr: ["fed"],
        memberships: [],
        tenant: { id: "00000000-0000-4000-8000-0000000000aa", name, slug: "kaefer-demo" },
        user: {
          displayName: "Alice Anderson",
          email: "alice@kaefer.test",
          id: "00000000-0000-4000-8000-0000000000a1",
          status: "active",
          userClass: "staff",
        },
      },
    }),
  );
  await page.route("**/api/v1/access/me/abilities**", (route) =>
    route.fulfill({ json: { permissions: ["project.view"] } }),
  );
}

test("the long company name fixture is 60 characters", () => {
  expect(LONG_NAME).toHaveLength(60);
});

for (const { width, height } of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`a 60-character company name keeps the header controls on screen at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await signInWithTenantName(page, LONG_NAME);
    await page.goto("/");
    const banner = page.getByRole("banner");
    await expect(banner.getByRole("link", { name: `${LONG_NAME} AIP, home` })).toBeVisible();

    const account = banner.getByRole("button", { name: "Account menu" });
    await expect(account).toBeVisible();
    const controls = [account, banner.getByRole("link", { name: /, home$/ })];
    if (width < 768) controls.push(banner.getByRole("button", { name: "Menu", exact: true }));
    for (const control of controls) {
      const box = await control.boundingBox();
      expect(box, "the control is laid out").not.toBeNull();
      expect(box!.x, "the control starts inside the viewport").toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width, "the control ends inside the viewport").toBeLessThanOrEqual(width);
    }
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, "the page does not scroll sideways").toBeLessThanOrEqual(0);
  });
}
