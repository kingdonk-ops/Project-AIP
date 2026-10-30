/**
 * The server's template issues (FORMS-04): each issue's text from `forms.lint.<CODE>` when it is a
 * FORMS-01 lint code, otherwise the server's own message, with its path in mono.
 */
import { useId } from "react";
import { t } from "../shell/t";
import { formatPath, isLintCode, type Issue } from "./issues";

export interface IssueListProps {
  issues: readonly Issue[];
  /** A heading key to use instead of "The server found {count} issues". */
  titleKey?: string;
}

export function IssueList({ issues, titleKey }: IssueListProps) {
  const id = useId();
  if (issues.length === 0) return null;
  return (
    <section className="forms-issues" role="alert" aria-labelledby={id}>
      <h3 id={id} className="forms-issues__title">
        {titleKey ? t(titleKey) : t("forms.templates.issues.title", { count: issues.length })}
      </h3>
      <ul className="forms-issues__list">
        {issues.map((issue, index) => {
          const path = formatPath(issue.path);
          return (
            // Issues have no id; the server's order is stable for one response.
            <li key={`${index}-${issue.code}-${path}`} className="forms-issues__item">
              <span>{isLintCode(issue.code) ? t(`forms.lint.${issue.code}`) : issue.message || issue.code}</span>
              {path ? <code className="forms-mono forms-issues__path">{path}</code> : null}
              {isLintCode(issue.code) && issue.message ? (
                <span className="forms-issues__detail">{issue.message}</span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
