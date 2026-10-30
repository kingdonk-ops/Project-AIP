import { createRoute } from "@tanstack/react-router";
import "../../../../features/item_types/item-types.css";
import "../../../../features/item_types/nav";
import {
  ContentTypesRegister,
  contentTypesQuery,
  toContentTypesSearch,
  validateContentTypesSearch,
} from "../../../../features/item_types/ContentTypesRegister";
import { appRoute } from "../../../_app";

export const contentTypesIndexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/admin/content-types",
  validateSearch: validateContentTypesSearch,
  component: ContentTypesIndexPage,
});

function ContentTypesIndexPage() {
  const search = contentTypesIndexRoute.useSearch();
  const navigate = contentTypesIndexRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <ContentTypesRegister
      query={contentTypesQuery(search)}
      permissions={session.permissions}
      onQueryChange={(next) => void navigate({ search: toContentTypesSearch(next), replace: true })}
      onOpen={(contentType) =>
        void navigate({ to: "/admin/content-types/$contentTypeId", params: { contentTypeId: contentType.id } })
      }
    />
  );
}
