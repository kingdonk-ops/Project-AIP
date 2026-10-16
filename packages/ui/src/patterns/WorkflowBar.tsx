/**
 * Workflow bar (DESIGN-04): the record's steps with the current one marked, and the next allowed
 * actions. The caller passes both in from the workflow API; nothing is computed here.
 */
import { Button } from "../components/button";
import { cn } from "../lib/cn";
import type { Translate } from "../register/types";

export interface WorkflowStep {
  id: string;
  labelKey: string;
}

export interface WorkflowAction {
  id: string;
  labelKey: string;
  onSelect: () => void;
  tone?: "default" | "danger";
}

export interface WorkflowBarProps {
  steps: readonly WorkflowStep[];
  /** Id of the current step. */
  current: string;
  /** The next allowed actions, as the server reports them. */
  actions: readonly WorkflowAction[];
  translate: Translate;
}

export function WorkflowBar({ steps, current, actions, translate }: WorkflowBarProps) {
  const at = steps.findIndex((step) => step.id === current);
  return (
    <nav className="aip-workflow" aria-label={translate("ui.workflow.label")}>
      <ol className="aip-workflow__steps">
        {steps.map((step, i) => {
          const state = i < at ? "done" : i === at ? "current" : "todo";
          return (
            <li
              key={step.id}
              className={cn("aip-workflow__step", `aip-workflow__step--${state}`)}
              data-state={state}
              aria-current={state === "current" ? "step" : undefined}
            >
              {translate(step.labelKey)}
            </li>
          );
        })}
      </ol>
      {actions.length > 0 && (
        <div className="aip-workflow__actions">
          {actions.map((action, i) => (
            <Button
              key={action.id}
              variant={action.tone === "danger" ? "danger" : i === 0 ? "primary" : "secondary"}
              onClick={action.onSelect}
            >
              {translate(action.labelKey)}
            </Button>
          ))}
        </div>
      )}
    </nav>
  );
}
