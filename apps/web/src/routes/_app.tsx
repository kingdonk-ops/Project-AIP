import { createRoute, Outlet, redirect } from "@tanstack/react-router";
import { AppShell } from "../features/shell/AppShell";
import { sessionQuery } from "../features/shell/session";
import { rootRoute } from "./__root";

/** Authenticated layout route: no session, no render. The shell wraps every child route. */
export const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "_app",
  beforeLoad: async ({ context, location }) => {
    const session = await context.queryClient.ensureQueryData(sessionQuery(context.sessionPort));
    if (session === null) {
      throw redirect({ to: "/login", search: { next: location.href } });
    }
    return { session };
  },
  component: AppLayout,
});

function AppLayout() {
  const { session } = appRoute.useRouteContext();
  return (
    <AppShell session={session}>
      <Outlet />
    </AppShell>
  );
}
