import { createRoute } from "@tanstack/react-router";
import "../../../features/forms/forms.css";
import "../../../features/forms/nav";
import { templatesQuery, toTemplatesSearch, validateTemplatesSearch } from "../../../features/forms/search";
import { TemplatesRegister } from "../../../features/forms/TemplatesRegister";
import { appRoute } from "../../_app";

export const templatesIndexRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/templates",
  validateSearch: validateTemplatesSearch,
  component: TemplatesIndexPage,
});

function TemplatesIndexPage() {
  const search = templatesIndexRoute.useSearch();
  const navigate = templatesIndexRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <TemplatesRegister
      query={templatesQuery(search)}
      permissions={session.permissions}
      onQueryChange={(next) => void navigate({ search: toTemplatesSearch(next), replace: true })}
      onOpenTemplate={(templateId) => void navigate({ to: "/templates/$templateId", params: { templateId } })}
    />
  );
}
