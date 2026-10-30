import type { Translate } from "@aip/ui";
import { useCallback, useId, useMemo, useState } from "react";
import type { RendererAdapters } from "./adapters";
import { ErrorSummary, type ErrorSummaryItem } from "./ErrorSummary";
import { FormSection } from "./FormSection";
import { labelOf, termParams } from "./labels";
import { evaluateAnswers } from "./logic/evaluate";
import type { AnswerError, Answers, AnswerValue, EvaluationContext, EvaluationMode, FormSchema } from "./logic/types";

export interface FormRendererProps {
  /** A frozen revision schema (FORMS-01). */
  schema: FormSchema;
  answers: Answers;
  /** The whole next answer set and the key that changed. */
  onChange: (next: Answers, changedKey: string) => void;
  mode: EvaluationMode;
  context?: EvaluationContext;
  /** The app's terminology lookup. */
  t: Translate;
  adapters?: RendererAdapters;
  readOnly?: boolean;
  /** `"touched"`: a field's error shows after it is blurred; `"all"`: every error (after a submit attempt). */
  showErrors?: "touched" | "all";
  /** Errors the API returned; shown like local ones, without waiting for a blur. */
  serverErrors?: readonly AnswerError[];
  id?: string;
}

const NO_ADAPTERS: RendererAdapters = {};
const NO_ERRORS: readonly AnswerError[] = [];

/**
 * Renders a frozen form revision as an accessible, editable or read-only form. Visibility, required
 * markers, errors and fail flags all come from `evaluateAnswers` (FORMS-02); the component never
 * computes them itself. It has no API knowledge: files and references go through `adapters`.
 */
export function FormRenderer({
  schema,
  answers,
  onChange,
  mode,
  context,
  t,
  adapters = NO_ADAPTERS,
  readOnly = false,
  showErrors = "touched",
  serverErrors = NO_ERRORS,
  id,
}: FormRendererProps) {
  const autoId = useId();
  const formId = id ?? autoId;
  const [touched, setTouched] = useState<ReadonlySet<string>>(() => new Set());

  const evaluation = useMemo(
    () => evaluateAnswers(schema, answers, { mode, ...(context ? { context } : {}) }),
    [schema, answers, mode, context],
  );

  const fieldDomId = useCallback((fieldKey: string) => `${formId}-field-${fieldKey}`, [formId]);

  // At most one error per field: the local one (once shown), else the server's.
  const shownErrors = useMemo(() => {
    const shown = new Map<string, AnswerError>();
    for (const error of evaluation.errors) {
      if (evaluation.visible[error.fieldKey] !== true) continue; // e.g. UNKNOWN_FIELD
      if (showErrors === "all" || touched.has(error.fieldKey)) shown.set(error.fieldKey, error);
    }
    for (const error of serverErrors) {
      if (evaluation.visible[error.fieldKey] === true && !shown.has(error.fieldKey)) shown.set(error.fieldKey, error);
    }
    return shown;
  }, [evaluation, serverErrors, showErrors, touched]);

  const message = useCallback((error: AnswerError) => t(error.messageKey, termParams(error.params)), [t]);
  const errorFor = useCallback(
    (fieldKey: string) => {
      const error = shownErrors.get(fieldKey);
      return error ? message(error) : undefined;
    },
    [shownErrors, message],
  );

  const onFieldChange = useCallback(
    (fieldKey: string, value: AnswerValue | undefined) => {
      const next: Answers = { ...answers };
      if (value === undefined) delete next[fieldKey];
      else next[fieldKey] = value;
      onChange(next, fieldKey);
    },
    [answers, onChange],
  );

  const onFieldBlur = useCallback((fieldKey: string) => {
    setTouched((prev) => (prev.has(fieldKey) ? prev : new Set(prev).add(fieldKey)));
  }, []);

  const summary: ErrorSummaryItem[] = [];
  if (!readOnly && showErrors === "all") {
    for (const section of schema.sections) {
      for (const field of section.fields) {
        const error = shownErrors.get(field.key);
        if (error) {
          summary.push({ fieldKey: field.key, label: labelOf(t, field), message: message(error), targetId: fieldDomId(field.key) });
        }
      }
    }
  }

  return (
    <div id={formId} className="aip-form-renderer" data-read-only={readOnly || undefined}>
      {summary.length ? <ErrorSummary items={summary} t={t} /> : null}
      {schema.sections.map((section) => (
        <FormSection
          key={section.key}
          section={section}
          evaluation={evaluation}
          answers={answers}
          t={t}
          adapters={adapters}
          readOnly={readOnly}
          errorFor={errorFor}
          onFieldChange={onFieldChange}
          onFieldBlur={onFieldBlur}
          fieldDomId={fieldDomId}
        />
      ))}
    </div>
  );
}
