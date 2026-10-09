import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";
import type { SessionPort } from "../features/shell/session";
import { t } from "../features/shell/t";

export interface RouterContext {
  queryClient: QueryClient;
  sessionPort: SessionPort;
}

export const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
  errorComponent: RootError,
});

function RootLayout() {
  return <Outlet />;
}

/** A failed session lookup (network, 5xx) is not "signed out": say so instead of redirecting. */
function RootError() {
  return (
    <main className="shell-fallback">
      <p role="alert">{t("shell.error.sessionUnavailable")}</p>
    </main>
  );
}
