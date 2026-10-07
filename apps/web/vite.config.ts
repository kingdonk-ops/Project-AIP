import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `/api` goes to the FastAPI app both in dev and in `vite preview` (the e2e server, STACK-03).
const apiProxy = { "/api": process.env.AIP_API_URL ?? "http://localhost:8000" };

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
