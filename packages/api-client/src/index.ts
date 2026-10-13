// Public entry of @aip/api-client (STACK-03). Everything under ./generated is produced by
// `pnpm --filter api-client generate` from openapi.json; never edit it by hand.
export * from "./generated/endpoints";
export { CSRF_COOKIE, CSRF_HEADER, onSessionExpired, readCookie, withCsrf } from "./fetcher";
export * from "./generated/model";
// Zod schemas of the same contract (request bodies, params, responses), namespaced so their names
// never collide with the hooks: `schemas.projectsCreateBody`.
export * as schemas from "./generated/zod/index.zod";
export type { components, operations, paths } from "./generated/schema";
