import { createRootRoute, Outlet } from "@tanstack/react-router";

export const rootRoute = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return <Outlet />;
}
