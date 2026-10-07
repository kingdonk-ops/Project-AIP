// Public entry of @aip/api-client (STACK-03). Everything under ./generated is produced by
// `pnpm --filter api-client generate` from openapi.json; never edit it by hand.
export * from "./generated/endpoints";
export * from "./generated/model";
export type { components, operations, paths } from "./generated/schema";
