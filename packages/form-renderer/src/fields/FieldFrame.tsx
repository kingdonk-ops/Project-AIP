import { FormField, type FormFieldControlProps, type Translate } from "@aip/ui";
import { useId, type ReactNode } from "react";
import type { RendererAdapters } from "../adapters";
import type { AnswerValue, FormField as FormFieldDef } from "../logic/types";

/** Label, hint, error and required state of one field, already translated by FormRenderer. */
export interface FrameProps {
  label: string;
  hint?: string;
  error?: string;
  required: boolean;
}

/** What every field component receives (fields/registry.ts maps a registry type to one). */
export interface FieldProps {
  field: FormFieldDef;
  /** The stored answer, `undefined` when absent. */
  value: AnswerValue | undefined;
  /** `undefined` removes the answer (an empty field). */
  onChange: (value: AnswerValue | undefined) => void;
  t: Translate;
  adapters: RendererAdapters;
  readOnly: boolean;
  frame: FrameProps;
}

export interface ControlProps extends FormFieldControlProps {
  "aria-required"?: true;
}

/** A single-control field: `@aip/ui` FormField wires label, hint and error to the control by id. */
export function ControlFrame({ frame, children }: { frame: FrameProps; children: (control: ControlProps) => ReactNode }) {
  return (
    <FormField label={frame.label} {...(frame.hint ? { hint: frame.hint } : {})} {...(frame.error ? { error: frame.error } : {})}>
      {(control) => children(frame.required ? { ...control, "aria-required": true } : control)}
    </FormField>
  );
}

/**
 * A multi-control field (radios, checkboxes, media): a `<fieldset>` named by its legend, with the
 * same hint/error wiring and classes as FormField. `role="radiogroup"` carries `aria-required`;
 * a plain group cannot (ARIA), so its required state is the visible marker only.
 */
export function GroupFrame({
  frame,
  role,
  className,
  children,
}: {
  frame: FrameProps;
  role?: "radiogroup";
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  const legendId = `${id}-legend`;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [frame.hint ? hintId : null, frame.error ? errorId : null].filter(Boolean).join(" ");
  return (
    <fieldset
      className={["aip-form-field", "aip-form-renderer__group", className].filter(Boolean).join(" ")}
      aria-labelledby={legendId}
      {...(role ? { role } : {})}
      {...(describedBy ? { "aria-describedby": describedBy } : {})}
      {...(role && frame.required ? { "aria-required": true } : {})}
      {...(role && frame.error ? { "aria-invalid": true } : {})}
    >
      <legend id={legendId} className="aip-label aip-form-renderer__legend">
        {frame.label}
      </legend>
      {children}
      {frame.hint ? (
        <p id={hintId} className="aip-form-field__hint">
          {frame.hint}
        </p>
      ) : null}
      {frame.error ? (
        <p id={errorId} className="aip-form-field__error" role="alert">
          {frame.error}
        </p>
      ) : null}
    </fieldset>
  );
}

/** Read-only display: the label and the value as text, no controls. */
export function ReadOnlyFrame({ frame, children }: { frame: FrameProps; children: ReactNode }) {
  const id = useId();
  return (
    <div className="aip-form-field aip-form-renderer__readonly" role="group" aria-labelledby={id}>
      <span id={id} className="aip-label">
        {frame.label}
      </span>
      <div className="aip-form-renderer__value">{children}</div>
    </div>
  );
}

/** The "not answered" text for an empty read-only value. */
export function NotAnswered({ t }: { t: Translate }) {
  return <span className="aip-form-renderer__empty">{t("forms.renderer.not_answered")}</span>;
}
