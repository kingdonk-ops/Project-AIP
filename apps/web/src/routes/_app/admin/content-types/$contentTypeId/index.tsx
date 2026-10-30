import { createRoute } from "@tanstack/react-router";
import { ContentTypeDetail, validateContentTypeSearch } from "../../../../../features/item_types/ContentTypeDetail";
import "../../../../../features/item_types/item-types.css";
import "../../../../../features/item_types/nav";
import { appRoute } from "../../../../_app";

export const contentTypeDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/content-types/$contentTypeId",
  validateSearch: validateContentTypeSearch,
  component: ContentTypeDetailPage,
});

function ContentTypeDetailPage() {
  const { contentTypeId } = contentTypeDetailRoute.useParams();
  const { tab } = contentTypeDetailRoute.useSearch();
  const navigate = contentTypeDetailRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <ContentTypeDetail
      contentTypeId={contentTypeId}
      permissions={session.permissions}
      tab={tab}
      onTabChange={(next) => void navigate({ search: { tab: next }, replace: true })}
    />
  );
}
