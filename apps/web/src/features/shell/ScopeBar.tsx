import { Badge } from "@aip/ui";
import { t } from "./t";

export interface ScopeBarProps {
  tenantName: string;
  /** Selected project, once the project switcher exists (PROJECTS-03). */
  projectName?: string | undefined;
}

/** Shows the current scope as chips. The asset-subtree chip is added later, after the project chip. */
export function ScopeBar({ tenantName, projectName }: ScopeBarProps) {
  return (
    <section className="shell-scope" aria-label={t("shell.scope.label")}>
      <Badge tone="outline" data-scope="tenant">
        <span className="shell-scope__kind">{t("shell.scope.tenant")}</span> {tenantName}
      </Badge>
      {projectName ? (
        <Badge tone="outline" data-scope="project">
          <span className="shell-scope__kind">{t("shell.scope.project")}</span> {projectName}
        </Badge>
      ) : null}
    </section>
  );
}
