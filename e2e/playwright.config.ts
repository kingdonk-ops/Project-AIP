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
    command: `pnpm --filter web build && pnpm --filter web exec vite preview --port ${webPort} --strictPort`,
    cwd: "..",
    url: `http://localhost:${webPort}`,
    env: { AIP_API_URL: `http://localhost:${apiPort}` },
    reuseExistingServer: reuse,
    timeout: 120_000,
  },
  {
    name: "web-dev",
    command: `pnpm --filter web exec vite --port ${devPort} --strictPort`,
    cwd: "..",
    url: devBaseURL,
    reuseExistingServer: reuse,
    timeout: 120_000,
  },
];

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
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chrome", use: { ...devices["Pixel 7"] } },
    { name: "ipad-webkit", use: { ...devices["iPad (gen 7)"] } },
  ],
  ...(external ? {} : { webServer }),
});
