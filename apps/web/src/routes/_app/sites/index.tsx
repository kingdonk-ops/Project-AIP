import { createRoute } from "@tanstack/react-router";
import { SitesRegister } from "../../../features/projects/SitesRegister";
import "../../../features/projects/sites-nav";
import { sitesQuery, toSitesSearch, validateSitesSearch } from "../../../features/projects/sites-search";
import { appRoute } from "../../_app";

export const sitesIndexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/sites",
  validateSearch: validateSitesSearch,
  component: SitesIndexPage,
});

function SitesIndexPage() {
  const search = sitesIndexRoute.useSearch();
  const navigate = sitesIndexRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <SitesRegister
      query={sitesQuery(search)}
      permissions={session.permissions}
      onQueryChange={(next) => void navigate({ search: toSitesSearch(next), replace: true })}
    />
  );
}
