import { createRoute, createRouter, lazyRouteComponent } from "@tanstack/react-router";
import { rootRoute } from "./routes/__root";
import { indexRoute } from "./routes/index";

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

export const routeTree = rootRoute.addChildren([indexRoute, ...devRoutes]);

export function createAppRouter() {
  return createRouter({ routeTree });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
