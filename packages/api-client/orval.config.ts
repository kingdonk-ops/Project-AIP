// orval config (STACK-03): TanStack Query hooks + fetch client from the committed OpenAPI schema.
// Run `pnpm --filter api-client generate`; never edit src/generated/ by hand.
import { defineConfig } from "orval";

export default defineConfig({
  api: {
    input: { target: "./openapi.json" },
    output: {
      mode: "tags-split",
      target: "./src/generated/endpoints",
      schemas: "./src/generated/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      indexFiles: true,
      override: {
        // scripts/add-generated-header.mjs writes our own header; orval's names its version.
        header: false,
      },
    },
  },
});
