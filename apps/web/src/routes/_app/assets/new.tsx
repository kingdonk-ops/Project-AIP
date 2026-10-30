import { createRoute } from "@tanstack/react-router";
import "../../../features/assets/assets.css";
import { AssetForm } from "../../../features/assets/AssetForm";
import "../../../features/assets/nav";
import { isUuid } from "../../../features/assets/search";
import { appRoute } from "../../_app";

export interface NewAssetSearch {
  /** The parent to preselect (the register's "Add child", or the tree scope). */
  parentId?: string;
}

export const assetsNewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/assets/new",
  validateSearch: (search: Record<string, unknown>): NewAssetSearch => (isUuid(search.parentId) ? { parentId: search.parentId } : {}),
  component: AssetsNewPage,
});

function AssetsNewPage() {
  const { parentId } = assetsNewRoute.useSearch();
  const navigate = assetsNewRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <AssetForm
      // A new parentId (another "Add child") starts a fresh form.
      key={parentId ?? "top"}
      mode={{ kind: "create", parentId }}
      permissions={session.permissions}
      onCreated={(asset) =>
        void navigate({
          to: "/assets",
          search: { ...(asset.parentId ? { under: asset.parentId } : {}), created: asset.internalTag },
        })
      }
      onSaved={() => undefined}
    />
  );
}
