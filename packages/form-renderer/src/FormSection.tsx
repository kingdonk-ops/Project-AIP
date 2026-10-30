import { StatusChip, type Translate } from "@aip/ui";
import type { RendererAdapters } from "./adapters";
import { ReadOnlyFrame, type FrameProps } from "./fields/FieldFrame";
import { renderField } from "./fields/registry";
import { labelOf } from "./labels";
import type { AnswerEvaluation, Answers, AnswerValue, FormField, FormSection as FormSectionDef } from "./logic/types";

export interface FormSectionProps {
  section: FormSectionDef;
  evaluation: AnswerEvaluation;
  answers: Answers;
  t: Translate;
  adapters: RendererAdapters;
  readOnly: boolean;
  /** The translated error to show under a field now, if any. */
  errorFor: (fieldKey: string) => string | undefined;
  onFieldChange: (fieldKey: string, value: AnswerValue | undefined) => void;
  onFieldBlur: (fieldKey: string) => void;
  /** DOM id of a field's wrapper (the ErrorSummary links to it). */
  fieldDomId: (fieldKey: string) => string;
}

/**
 * One section as a `<fieldset>` + `<legend>`. Only fields the evaluator found visible are rendered;
 * a hidden field is absent from the DOM (and its answer is left untouched by the renderer).
 */
export function FormSection(props: FormSectionProps) {
  const { section, evaluation, t } = props;
  const fields = section.fields.filter((f) => evaluation.visible[f.key] === true);
  if (fields.length === 0) return null;
  return (
    <fieldset className="aip-form-renderer__section" data-section-key={section.key}>
      <legend className="aip-form-renderer__section-title">{labelOf(t, section)}</legend>
      {fields.map((field) => (
        <FieldRow key={field.key} field={field} {...props} />
      ))}
    </fieldset>
  );
}

function FieldRow({
  field,
  evaluation,
  answers,
  t,
  adapters,
  readOnly,
  errorFor,
  onFieldChange,
  onFieldBlur,
  fieldDomId,
}: FormSectionProps & { field: FormField }) {
  const required = evaluation.required[field.key] === true;
  const failed = evaluation.failed.includes(field.key);
  const error = readOnly ? undefined : errorFor(field.key);
  const frame: FrameProps = {
    label: labelOf(t, field),
    required,
    ...(field.helpKey ? { hint: t(field.helpKey) } : {}),
    ...(error ? { error } : {}),
  };
  const value = Object.hasOwn(answers, field.key) ? answers[field.key] : undefined;
  const control = renderField({
    field,
    value,
    onChange: (next) => onFieldChange(field.key, next),
    t,
    adapters,
    readOnly,
    frame,
  });

  return (
    <div
      id={fieldDomId(field.key)}
      className="aip-form-renderer__field"
      data-field-key={field.key}
      onBlur={() => onFieldBlur(field.key)}
    >
      {control ?? (
        <ReadOnlyFrame frame={frame}>
          <span className="aip-form-renderer__empty">{t("forms.renderer.unsupported_field", { type: field.type })}</span>
        </ReadOnlyFrame>
      )}
      {required || failed ? (
        <div className="aip-form-renderer__meta">
          {required && !readOnly ? <span className="aip-form-renderer__required">{t("forms.renderer.required")}</span> : null}
          {failed ? <StatusChip tone="danger" icon="alert" label={t("forms.answer.failed")} /> : null}
        </div>
      ) : null}
      {failed && field.failMessageKey ? <p className="aip-form-renderer__fail-message">{t(field.failMessageKey)}</p> : null}
    </div>
  );
}
