import { createRoute } from "@tanstack/react-router";
import "../../../../../features/portal/nav";
import "../../../../../features/portal/portal.css";
import { PortalUsersRegister } from "../../../../../features/portal/PortalUsersRegister";
import { portalUsersQuery, toSearch, validatePortalUsersSearch } from "../../../../../features/portal/search";
import { appRoute } from "../../../../_app";

export const portalUsersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/portal/users",
  validateSearch: validatePortalUsersSearch,
  component: PortalUsersPage,
});

function PortalUsersPage() {
  const search = portalUsersRoute.useSearch();
  const navigate = portalUsersRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <PortalUsersRegister
      query={portalUsersQuery(search)}
      permissions={session.permissions}
      onQueryChange={(next) => void navigate({ search: toSearch(next), replace: true })}
      onOpenUser={(user) => void navigate({ to: "/admin/portal/users/$portalUserId", params: { portalUserId: user.id } })}
    />
  );
}
