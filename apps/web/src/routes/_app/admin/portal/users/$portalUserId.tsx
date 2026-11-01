import { createRoute } from "@tanstack/react-router";
import "../../../../../features/portal/nav";
import "../../../../../features/portal/portal.css";
import { PortalUserDetail } from "../../../../../features/portal/PortalUserDetail";
import { appRoute } from "../../../../_app";

export const portalUserDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/portal/users/$portalUserId",
  component: PortalUserDetailPage,
});

function PortalUserDetailPage() {
  const { portalUserId } = portalUserDetailRoute.useParams();
  const { session } = appRoute.useRouteContext();
  // A new id starts a fresh page (a pending step-up and the dialogs belong to one user).
  return <PortalUserDetail key={portalUserId} portalUserId={portalUserId} permissions={session.permissions} />;
}
