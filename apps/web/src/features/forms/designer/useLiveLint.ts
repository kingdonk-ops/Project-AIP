/**
 * Lint as you go (FORMS-11): `LINT_DELAY_MS` after the last change the schema goes to the server's
 * lint (`POST /forms/lint`, through the generated client). A newer change cancels the older call, so
 * typing sends one request, not one per keystroke. Each result remembers the schema it was for:
 * while the shown schema has no result yet the state is "checking". A save or publish refused with
 * 422 reports its issues for the schema it sent through `report`.
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

interface Result extends LintState {
  schema: FormSchema | null;
}

const IDLE: LintState = { status: "idle", issues: [] };
const CHECKING: LintState = { status: "checking", issues: [] };

export function useLiveLint(
  schema: FormSchema,
  enabled: boolean,
): LintState & { report: (issues: Issue[], schema: FormSchema) => void } {
  const [result, setResult] = useState<Result>({ schema: null, ...CHECKING });

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      formsLint({ schema: schema as unknown as LintBodySchema }, { signal: controller.signal })
        .then((response) => {
          if (controller.signal.aborted) return;
          if (response.status === 200) {
            const issues = lintIssues(response.data);
            setResult({ schema, status: issues.length ? "issues" : "clean", issues });
            return;
          }
          const issues = requestIssues(response.data);
          setResult(issues.length ? { schema, status: "issues", issues } : { schema, status: "failed", issues: [] });
        })
        .catch(() => {
          if (!controller.signal.aborted) setResult({ schema, status: "failed", issues: [] });
        });
    }, LINT_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [schema, enabled]);

  const report = useCallback((issues: Issue[], reported: FormSchema) => {
    setResult({ schema: reported, status: issues.length ? "issues" : "clean", issues });
  }, []);

  let state: LintState = IDLE;
  if (enabled) state = result.schema === schema ? { status: result.status, issues: result.issues } : CHECKING;
  return { ...state, report };
}
