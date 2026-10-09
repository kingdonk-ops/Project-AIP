import type { QueryClient } from "@tanstack/react-query";
import { createRoute, createRouter, lazyRouteComponent, type RouterHistory } from "@tanstack/react-router";
import type { SessionPort } from "./features/shell/session";
import { rootRoute } from "./routes/__root";
import { appRoute } from "./routes/_app";
import { homeRoute } from "./routes/_app/index";
import { projectsRoute } from "./routes/_app/projects";
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
    ];

export const routeTree = rootRoute.addChildren([
  loginRoute,
  appRoute.addChildren([homeRoute, projectsRoute]),
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
