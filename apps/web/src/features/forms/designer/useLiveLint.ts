/**
 * Lint as you go (FORMS-11): `LINT_DELAY_MS` after the last change the schema goes to the server's
 * lint (`POST /forms/lint`, through the generated client). A newer change cancels the older call, so
 * typing sends one request, not one per keystroke. A save or publish refused with 422 reports its
 * issues through `report`, which stands until the next check.
 */
import { formsLint, type LintBodySchema } from "@aip/api-client";
import type { FormSchema } from "@aip/form-renderer";
import { useCallback, useEffect, useState } from "react";
import { lintIssues, requestIssues, type Issue } from "../issues";

export const LINT_DELAY_MS = 800;

export type LintStatus = "idle" | "checking" | "clean" | "issues" | "failed";

export interface LintState {
  status: LintStatus;
  issues: Issue[];
}

export function useLiveLint(schema: FormSchema, enabled: boolean): LintState & { report: (issues: Issue[]) => void } {
  const [state, setState] = useState<LintState>({ status: enabled ? "checking" : "idle", issues: [] });

  useEffect(() => {
    if (!enabled) return;
    setState((current) => (current.status === "checking" ? current : { ...current, status: "checking" }));
    const controller = new AbortController();
    const timer = setTimeout(() => {
      formsLint({ schema: schema as unknown as LintBodySchema }, { signal: controller.signal })
        .then((response) => {
          if (controller.signal.aborted) return;
          if (response.status === 200) {
            const issues = lintIssues(response.data);
            setState({ status: issues.length ? "issues" : "clean", issues });
            return;
          }
          const issues = requestIssues(response.data);
          setState(issues.length ? { status: "issues", issues } : { status: "failed", issues: [] });
        })
        .catch(() => {
          if (!controller.signal.aborted) setState({ status: "failed", issues: [] });
        });
    }, LINT_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [schema, enabled]);

  const report = useCallback((issues: Issue[]) => {
    setState({ status: issues.length ? "issues" : "clean", issues });
  }, []);

  return { ...state, report };
}
