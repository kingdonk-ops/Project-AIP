import { decodeRegisterQuery, encodeRegisterQuery } from "@aip/ui";
import { createRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import { OperatorOnly } from "../../../../../features/platform-events/access";
import { CataloguePage } from "../../../../../features/platform-events/CataloguePage";
import "../../../../../features/platform-events/nav";
import "../../../../../features/platform-events/platform-events.css";
import { catalogueSpec } from "../../../../../features/platform-events/search";
import { appRoute } from "../../../../_app";

export const platformEventsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/platform/events",
  // The URL holds the encoded register query; links to the page need no search.
  validateSearch: (search: Record<string, unknown>): Record<string, string> =>
    encodeRegisterQuery(decodeRegisterQuery(search, catalogueSpec)),
  component: PlatformEventsPage,
});

function PlatformEventsPage() {
  const search = platformEventsRoute.useSearch();
  const navigate = platformEventsRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  const query = useMemo(() => decodeRegisterQuery(search, catalogueSpec), [search]);
  return (
    <OperatorOnly permissions={session.permissions} titleKey="arch.events.catalogue.title">
      <CataloguePage
        query={query}
        permissions={session.permissions}
        onQueryChange={(next) => void navigate({ search: encodeRegisterQuery(next), replace: true })}
      />
    </OperatorOnly>
  );
}
