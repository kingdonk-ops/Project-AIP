import { createRoute } from "@tanstack/react-router";
import "../../../features/forms/forms.css";
import "../../../features/forms/nav";
import { DesignerPage } from "../../../features/forms/designer/Designer";
import { appRoute } from "../../_app";

/** FORMS-11: the form designer for revision `$rev` (its number) of a template. */
export const templateDesignerRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/templates/$templateId/revisions/$rev/design",
  component: TemplateDesignerPage,
});

function TemplateDesignerPage() {
  const { templateId, rev } = templateDesignerRoute.useParams();
  const navigate = templateDesignerRoute.useNavigate();
  const { session } = appRoute.useRouteContext();
  // A `rev` that is not a positive whole number matches no revision: the not-found state.
  const n = /^[1-9][0-9]{0,8}$/.test(rev) ? Number(rev) : -1;
  return (
    <DesignerPage
      key={`${templateId}-${rev}`}
      templateId={templateId}
      rev={n}
      permissions={session.permissions}
      onBack={(revisionNo) =>
        void navigate({ to: "/templates/$templateId", params: { templateId }, search: revisionNo ? { rev: revisionNo } : {} })
      }
      onOpenRevision={(revisionNo) =>
        void navigate({ to: "/templates/$templateId/revisions/$rev/design", params: { templateId, rev: String(revisionNo) } })
      }
    />
  );
}
