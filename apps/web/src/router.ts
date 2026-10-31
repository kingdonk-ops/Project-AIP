import type { QueryClient } from "@tanstack/react-query";
import { createRoute, createRouter, lazyRouteComponent, type RouterHistory } from "@tanstack/react-router";
import { registerNavItem } from "./features/shell/nav-registry";
import type { SessionPort } from "./features/shell/session";
import { rootRoute } from "./routes/__root";
import { appRoute } from "./routes/_app";
import { platformDeadLetterRoute } from "./routes/_app/admin/platform/events/dead-letter";
import { platformEventDetailRoute } from "./routes/_app/admin/platform/events/$eventName";
import { platformEventsRoute } from "./routes/_app/admin/platform/events/index";
import { contentTypeDetailRoute } from "./routes/_app/admin/content-types/$contentTypeId/index";
import { itemTypeEditorRoute } from "./routes/_app/admin/content-types/$contentTypeId/item-types/$itemTypeId";
import { contentTypesIndexRoute } from "./routes/_app/admin/content-types/index";
import { portalUserDetailRoute } from "./routes/_app/admin/portal/users/$portalUserId";
import { portalUsersRoute } from "./routes/_app/admin/portal/users/index";
import { portalUsersNewRoute } from "./routes/_app/admin/portal/users/new";
import { assetEditRoute } from "./routes/_app/assets/edit";
import { assetsIndexRoute } from "./routes/_app/assets/index";
import { assetsNewRoute } from "./routes/_app/assets/new";
import { homeRoute } from "./routes/_app/index";
import { projectDetailRoute } from "./routes/_app/projects/$projectId";
import { projectsIndexRoute } from "./routes/_app/projects/index";
import { projectsNewRoute } from "./routes/_app/projects/new";
import { reportsRegisterRoute } from "./routes/_app/reports/register";
import { sitesIndexRoute } from "./routes/_app/sites/index";
import { templateDetailRoute } from "./routes/_app/templates/$templateId";
import { templatesIndexRoute } from "./routes/_app/templates/index";
import { billingRoute } from "./routes/_app/settings/billing";
import { flagsRoute } from "./routes/_app/settings/flags";
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

// DESIGN-15: no BIM page exists yet, so outside production a fixture nav item behind the `bim`
// release flag shows the gate working (e2e/web/release-flags.spec.ts). Dead code in a production build.
if (!import.meta.env.PROD) {
  registerNavItem({
    id: "bim-fixture",
    section: "documents",
    to: "/__fixtures/ui",
    icon: "folder",
    termKey: "shell.flags.fixture_nav",
    flag: "bim",
  });
}

// ITEMTYPES-03: content types and item types admin pages.
const itemTypesRoutes = [contentTypesIndexRoute, contentTypeDetailRoute, itemTypeEditorRoute] as const;
// ASSETS-03: the asset tree and register, and the create and edit form.
const assetsRoutes = [assetsIndexRoute, assetsNewRoute, assetEditRoute] as const;
// PORTAL-07: the external users register, invite form and detail.
const portalRoutes = [portalUsersRoute, portalUsersNewRoute, portalUserDetailRoute] as const;

export const routeTree = rootRoute.addChildren([
  loginRoute,
  appRoute.addChildren([homeRoute, projectsIndexRoute, projectsNewRoute, projectDetailRoute, sitesIndexRoute, sessionsRoute, billingRoute, flagsRoute, platformEventsRoute, platformDeadLetterRoute, platformEventDetailRoute, templatesIndexRoute, templateDetailRoute, ...itemTypesRoutes, ...assetsRoutes, reportsRegisterRoute, ...portalRoutes]),
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
