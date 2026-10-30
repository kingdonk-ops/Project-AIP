// Playwright projects (AGENTS.md "Web testing"): desktop Chromium, mobile Chrome, iPad WebKit.
// Locally and in CI it starts the API (uvicorn) and the web app (`vite preview`, which proxies
// /api to the API). Set E2E_BASE_URL to test a deployed environment instead.
import { defineConfig, devices, type PlaywrightTestConfig } from "@playwright/test";

const apiPort = Number(process.env.E2E_API_PORT ?? 8000);
const webPort = Number(process.env.E2E_WEB_PORT ?? 4173);
const devPort = Number(process.env.E2E_DEV_PORT ?? 5174);
// DESIGN-01: the dev-only /__fixtures/ui route exists only under the Vite dev server.
export const devBaseURL = process.env.E2E_DEV_URL ?? `http://localhost:${devPort}`;
const external = process.env.E2E_BASE_URL;
const reuse = !process.env.CI;

const webServer: PlaywrightTestConfig["webServer"] = [
  {
    name: "api",
    command: `uv run uvicorn aip.main:create_app --factory --port ${apiPort}`,
    cwd: "..",
    url: `http://localhost:${apiPort}/api/v1/health`,
    reuseExistingServer: reuse,
    timeout: 60_000,
  },
  {
    name: "web",
    command: `pnpm --filter "web..." build && pnpm --filter web exec vite preview --port ${webPort} --strictPort`,
    cwd: "..",
    url: `http://localhost:${webPort}`,
    env: { AIP_API_URL: `http://localhost:${apiPort}` },
    reuseExistingServer: reuse,
    timeout: 120_000,
  },
  {
    name: "web-dev",
    command: `pnpm --filter "web^..." build && pnpm --filter web exec vite --port ${devPort} --strictPort`,
    cwd: "..",
    url: devBaseURL,
    // DESIGN-02: the fixture-backed session stub exists only in the dev server (never in `vite preview`).
    env: { AIP_API_URL: `http://localhost:${apiPort}`, VITE_AIP_DEV_SESSION: "stub" },
    reuseExistingServer: reuse,
    timeout: 120_000,
  },
];

// TESTING-09: the walking skeleton runs only in its own projects, against a whole deployment:
// `web` against the compose stack (CI job e2e-skeleton, E2E_BASE_URL=http://localhost:8080) and
// `staging` against the Coolify demo after a deploy. Both need E2E_SKELETON=1 and the E2E_USER_*
// / E2E_PASS_* variables, so the default run never needs Keycloak. `unit` runs the fixture tests.
// The UPLOADS-01 presign journey runs in the skeleton lane too (review 11 M11); without these
// projects it would skip in every lane. TESTING-12's real-session journeys need Keycloak too, and
// TESTING-13's workflow transition journeys need the stack's seeded `demo` workflow.
const SKELETON = [
  "web/walking-skeleton.spec.ts",
  "web/uploads-presign.spec.ts",
  "web/sessions.spec.ts",
  "web/approvals-transition.spec.ts",
  "web/item-types.spec.ts", // ITEMTYPES-03: needs both tenants signed in for real
];
const UNIT = "fixtures/*.spec.ts";
const skeletonProjects: PlaywrightTestConfig["projects"] = process.env.E2E_SKELETON
  ? [
      // 5 minutes: a sign-in may wait out the login/start rate-limit window (fixtures/login.ts).
      { name: "web", testMatch: SKELETON, retries: 0, timeout: 300_000, use: { ...devices["Desktop Chrome"], actionTimeout: 15_000 } },
      // No trace on the demo: a trace records typed values, and its credentials come from secrets.
      // The demo is a remote deployment: its first loads through Keycloak can exceed 5 s.
      {
        name: "staging",
        testMatch: SKELETON,
        retries: 0,
        timeout: 120_000,
        expect: { timeout: 15_000 },
        use: { ...devices["Desktop Chrome"], actionTimeout: 15_000, trace: "off" },
      },
    ]
  : [];

export default defineConfig({
  testDir: ".",
  testMatch: "**/*.spec.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: external ?? `http://localhost:${webPort}`,
    trace: "retain-on-failure",
    // Axe reads a toast mid fade-in as near-invisible text; the app drops the animation under reduced motion.
    contextOptions: { reducedMotion: "reduce" },
  },
  projects: [
    { name: "unit", testMatch: UNIT },
    { name: "desktop-chromium", testIgnore: [...SKELETON, UNIT], use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chrome", testIgnore: [...SKELETON, UNIT], use: { ...devices["Pixel 7"] } },
    { name: "ipad-webkit", testIgnore: [...SKELETON, UNIT], use: { ...devices["iPad (gen 7)"] } },
    ...(skeletonProjects ?? []),
  ],
  ...(external ? {} : { webServer }),
});
