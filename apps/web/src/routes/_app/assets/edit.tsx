import { createRoute } from "@tanstack/react-router";
import "../../../features/assets/assets.css";
import { AssetForm } from "../../../features/assets/AssetForm";
import "../../../features/assets/nav";
import { appRoute } from "../../_app";

export const assetEditRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/assets/$assetId/edit",
  component: AssetEditPage,
});

function AssetEditPage() {
  const { assetId } = assetEditRoute.useParams();
  const navigate = assetEditRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <AssetForm
      key={assetId}
      mode={{ kind: "edit", assetId }}
      permissions={session.permissions}
      onCreated={() => undefined}
      onSaved={(asset) => void navigate({ to: "/assets", search: asset.parentId ? { under: asset.parentId } : {} })}
    />
  );
}
