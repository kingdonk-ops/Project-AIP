import { useId, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { Label } from "./label";

export interface FormFieldControlProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

export interface FormFieldProps {
  /** Visible label text (from `t()`). Every input is reachable by its label. */
  label: string;
  hint?: string;
  error?: string;
  className?: string;
  /** Render prop: spread the props onto the control so label, hint and error are wired up. */
  children: (control: FormFieldControlProps) => ReactNode;
}

export function FormField({ label, hint, error, className, children }: FormFieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  const control: FormFieldControlProps = { id };
  if (describedBy) control["aria-describedby"] = describedBy;
  if (error) control["aria-invalid"] = true;
  return (
    <div className={cn("aip-form-field", className)}>
      <Label htmlFor={id}>{label}</Label>
      {children(control)}
      {hint ? (
        <p id={hintId} className="aip-form-field__hint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="aip-form-field__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
