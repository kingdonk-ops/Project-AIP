import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { defineConfig } from "vitest/config";

// `/api` goes to the FastAPI app in dev and in `vite preview` (the e2e server), so the browser talks
// to one origin and the API's `__Host-` cookie is first-party. In staging/production CloudFront
// path-routes `/api/*` to the ALB. `API_INTERNAL_URL` is the documented name; `AIP_API_URL` is the
// older alias the e2e config sets.
const apiTarget = process.env.API_INTERNAL_URL ?? process.env.AIP_API_URL ?? "http://localhost:8000";
const apiProxy = { "/api": apiTarget };

// Security headers are defined once in security-headers.json (CloudFront and nginx read the same file).
const { headers: securityHeaders } = JSON.parse(
  readFileSync(new URL("./security-headers.json", import.meta.url), "utf8"),
) as { headers: Record<string, string> };
// The dev server injects an inline React Refresh preamble, which the strict script-src would block,
// so `vite dev` gets every header except the CSP. `vite preview` serves the production build and
// gets all of them.
const devHeaders = Object.fromEntries(
  Object.entries(securityHeaders).filter(([name]) => name !== "Content-Security-Policy"),
);

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: apiProxy,
    headers: devHeaders,
  },
  preview: {
    proxy: apiProxy,
    headers: securityHeaders,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["./src/test-setup.ts"],
  },
});
