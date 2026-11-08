/**
 * The designer's lint panel (FORMS-11), under the canvas: the server lint's issues with FORMS-04's
 * text (`issueText`) and path. Clicking an issue selects the section or field its path points to.
 * The state ("No issues", "Checking…") is announced in a `role="status"`.
 */
import type { FormSchema } from "@aip/form-renderer";
import { Panel } from "@aip/ui";
import { t } from "../../shell/t";
import { issueText } from "../IssueList";
import { formatPath, isLintCode } from "../issues";
import { issueTarget, type Selection } from "./model";
import type { LintState } from "./useLiveLint";

export interface LintPanelProps {
  lint: LintState;
  schema: FormSchema;
  onSelect: (selection: NonNullable<Selection>) => void;
}

export function LintPanel({ lint, schema, onSelect }: LintPanelProps) {
  let status = "";
  if (lint.status === "clean") status = t("forms.designer.lint.clean");
  else if (lint.status === "checking") status = t("forms.designer.lint.checking");
  else if (lint.status === "failed") status = t("forms.designer.lint.failed");
  else if (lint.status === "issues") status = t("forms.templates.issues.title", { count: lint.issues.length });

  return (
    <Panel heading={t("forms.designer.lint.title")} headingLevel={2} className="dsg-lint" data-testid="designer-lint">
      <p role="status" className="dsg-lint__status" data-lint-status={lint.status}>
        {status}
      </p>
      {lint.status === "issues" ? (
        <ul className="dsg-lint__list">
          {lint.issues.map((issue, index) => {
            const path = formatPath(issue.path);
            const target = issueTarget(schema, issue.path);
            const text = issueText(issue);
            return (
              // Issues have no id; the server's order is stable for one response.
              <li key={`${index}-${issue.code}-${path}`} className="dsg-lint__item">
                {target ? (
                  <button type="button" className="dsg-lint__button" onClick={() => onSelect(target)}>
                    {text}
                  </button>
                ) : (
                  <span>{text}</span>
                )}
                {path ? <code className="forms-mono dsg-lint__path">{path}</code> : null}
                {isLintCode(issue.code) && issue.message ? <span className="dsg-lint__detail">{issue.message}</span> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </Panel>
  );
}
