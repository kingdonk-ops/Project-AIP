import { createRoute } from "@tanstack/react-router";
import "../../../../../features/portal/nav";
import "../../../../../features/portal/portal.css";
import { InviteForm } from "../../../../../features/portal/InviteForm";
import { appRoute } from "../../../../_app";

export const portalUsersNewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/portal/users/new",
  component: PortalUsersNewPage,
});

function PortalUsersNewPage() {
  const navigate = portalUsersNewRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <InviteForm
      permissions={session.permissions}
      onInvited={(portalUserId) => void navigate({ to: "/admin/portal/users/$portalUserId", params: { portalUserId } })}
    />
  );
}
