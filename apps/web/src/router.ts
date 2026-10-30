import type { QueryClient } from "@tanstack/react-query";
import { createRoute, createRouter, lazyRouteComponent, type RouterHistory } from "@tanstack/react-router";
import type { SessionPort } from "./features/shell/session";
import { rootRoute } from "./routes/__root";
import { appRoute } from "./routes/_app";
import { platformDeadLetterRoute } from "./routes/_app/admin/platform/events/dead-letter";
import { platformEventDetailRoute } from "./routes/_app/admin/platform/events/$eventName";
import { platformEventsRoute } from "./routes/_app/admin/platform/events/index";
import { contentTypeDetailRoute } from "./routes/_app/admin/content-types/$contentTypeId/index";
import { itemTypeEditorRoute } from "./routes/_app/admin/content-types/$contentTypeId/item-types/$itemTypeId";
import { contentTypesIndexRoute } from "./routes/_app/admin/content-types/index";
import { homeRoute } from "./routes/_app/index";
import { projectDetailRoute } from "./routes/_app/projects/$projectId";
import { projectsIndexRoute } from "./routes/_app/projects/index";
import { projectsNewRoute } from "./routes/_app/projects/new";
import { sitesIndexRoute } from "./routes/_app/sites/index";
import { templateDetailRoute } from "./routes/_app/templates/$templateId";
import { templatesIndexRoute } from "./routes/_app/templates/index";
import { billingRoute } from "./routes/_app/settings/billing";
import { sessionsRoute } from "./routes/_app/settings/profile/sessions";
import { loginRoute } from "./routes/login";

// DESIGN-01 component fixture: dev-only. In a production build this branch is dead code, so the
// route is not registered and its lazy chunk is never emitted.
const devRoutes = import.meta.env.PROD
  ? []
  : [
      createRoute({
        getParentRoute: () => rootRoute,
        path: "/__fixtures/ui",
        component: lazyRouteComponent(() => import("./routes/__fixtures/ui"), "UiFixture"),
      }),
      createRoute({
        getParentRoute: () => rootRoute,
        path: "/__fixtures/record",
        component: lazyRouteComponent(() => import("./routes/__fixtures/record"), "RecordFixture"),
      }),
      // FORMS-03: the form renderer fixture (e2e/web/form-renderer.spec.ts).
      createRoute({
        getParentRoute: () => rootRoute,
        path: "/__fixtures/form",
        component: lazyRouteComponent(() => import("./routes/__fixtures/form"), "FormFixture"),
      }),
    ];

// ITEMTYPES-03: content types and item types admin pages.
const itemTypesRoutes = [contentTypesIndexRoute, contentTypeDetailRoute, itemTypeEditorRoute] as const;

export const routeTree = rootRoute.addChildren([
  loginRoute,
  appRoute.addChildren([homeRoute, projectsIndexRoute, projectsNewRoute, projectDetailRoute, sitesIndexRoute, sessionsRoute, billingRoute, platformEventsRoute, platformDeadLetterRoute, platformEventDetailRoute, templatesIndexRoute, templateDetailRoute, ...itemTypesRoutes]),
  ...devRoutes,
]);

export interface AppRouterDeps {
  queryClient: QueryClient;
  sessionPort: SessionPort;
}

export function createAppRouter(context: AppRouterDeps, history?: RouterHistory) {
  return createRouter({ routeTree, context, ...(history ? { history } : {}) });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
