import { createRoute } from "@tanstack/react-router";
import "../../../features/forms/forms.css";
import "../../../features/forms/nav";
import { validateTemplateSearch } from "../../../features/forms/search";
import { TemplateDetail } from "../../../features/forms/TemplateDetail";
import { appRoute } from "../../_app";

export const templateDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/templates/$templateId",
  validateSearch: validateTemplateSearch,
  component: TemplateDetailPage,
});

function TemplateDetailPage() {
  const { templateId } = templateDetailRoute.useParams();
  const search = templateDetailRoute.useSearch();
  const navigate = templateDetailRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  return (
    <TemplateDetail
      key={templateId}
      templateId={templateId}
      permissions={session.permissions}
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
