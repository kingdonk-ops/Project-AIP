import { createRoute } from "@tanstack/react-router";
import "../../../../../../features/item_types/item-types.css";
import { ItemTypeEditor, validateItemTypeSearch } from "../../../../../../features/item_types/ItemTypeEditor";
import "../../../../../../features/item_types/nav";
import { appRoute } from "../../../../../_app";

export const itemTypeEditorRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/content-types/$contentTypeId/item-types/$itemTypeId",
  validateSearch: validateItemTypeSearch,
  component: ItemTypeEditorPage,
});

function ItemTypeEditorPage() {
  const { contentTypeId, itemTypeId } = itemTypeEditorRoute.useParams();
  const { tab } = itemTypeEditorRoute.useSearch();
  const navigate = itemTypeEditorRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <ItemTypeEditor
      // A new item type starts with a fresh editor (no unsaved text carried over).
      key={itemTypeId}
      contentTypeId={contentTypeId}
      itemTypeId={itemTypeId}
      permissions={session.permissions}
      tab={tab}
      onTabChange={(next) => void navigate({ search: { tab: next }, replace: true })}
    />
  );
}
