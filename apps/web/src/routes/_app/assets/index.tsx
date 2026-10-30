import { createRoute } from "@tanstack/react-router";
import "../../../features/assets/assets.css";
import { AssetsPage } from "../../../features/assets/AssetsPage";
import "../../../features/assets/nav";
import { validateAssetsSearch } from "../../../features/assets/search";
import { appRoute } from "../../_app";

export const assetsIndexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/assets",
  validateSearch: validateAssetsSearch,
  component: AssetsIndexPage,
});

function AssetsIndexPage() {
  const search = assetsIndexRoute.useSearch();
  const navigate = assetsIndexRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <AssetsPage
      search={search}
      permissions={session.permissions}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
      // ASSETS-05 repoints this to the asset detail page.
      onOpenAsset={(asset) => void navigate({ to: "/assets/$assetId/edit", params: { assetId: asset.id } })}
    />
  );
}
