// Shared types for the form evaluator (FORMS-02). camelCase matches the JSON Schema contract
// (packages/contracts/forms/form-template.schema.json) and the Python dataclasses.

/** Any JSON value, as parsed from a frozen revision schema or an answer. */
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

export type FieldType =
  | "text"
  | "number"
  | "decimal"
  | "date"
  | "dropdown"
  | "multi_select"
  | "measurement"
  | "boolean"
  | "photo"
  | "signature"
  | "asset_ref"
  | "user_ref";

export interface FieldOption {
  value: string;
  label: string;
  labelKey?: string;
}

export interface FieldValidations {
  min?: number;
  max?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
}

export interface FormRule {
  rule: Json;
  messageKey: string;
  message: string;
}

export interface FormField {
  key: string;
  type: FieldType;
  label: string;
  labelKey?: string;
  helpKey?: string;
  required?: boolean;
  visibleIf?: Json;
  requiredIf?: Json;
  failWhen?: Json;
  failMessageKey?: string;
  options?: FieldOption[];
  unit?: string;
  validations?: FieldValidations;
  rules?: FormRule[];
}

/** A check across a section's answers (FORMS-10, schemaVersion 2): `expr` must be true to pass. */
export interface SectionRule {
  key: string;
  expr: Json;
  label?: string;
  labelKey?: string;
}

export interface FormSection {
  key: string;
  label: string;
  labelKey?: string;
  visibleIf?: Json;
  fields: FormField[];
  rules?: SectionRule[];
}

export interface FormSchema {
  schemaVersion: number;
  sections: FormSection[];
}

export type AnswerValue = Json;
export type Answers = Record<string, AnswerValue>;

export type EvaluationMode = "draft" | "submit";

export interface EvaluationContext {
  kind: string;
  assetId?: string;
  projectId?: string;
}

export type ExpressionKind = "visibleIf" | "requiredIf" | "failWhen" | "rule";

export interface AnswerError {
  fieldKey: string;
  code: string;
  messageKey: string;
  params: Record<string, unknown>;
}

export interface ExpressionError {
  fieldKey: string;
  expression: ExpressionKind;
  message: string;
}

/**
 * One section's verdict (FORMS-10). `failed` (failWhen outcomes) never makes a section incomplete:
 * a failed reading is a valid answer.
 */
export interface SectionResult {
  visible: boolean;
  missingRequired: string[];
  invalid: string[];
  failed: string[];
  ruleFailures: string[];
  complete: boolean;
}

export interface AnswerEvaluation {
  visible: Record<string, boolean>;
  required: Record<string, boolean>;
  errors: AnswerError[];
  failed: string[];
  ignored: string[];
  expressionErrors: ExpressionError[];
  complete: boolean;
  sections: Record<string, SectionResult>;
}
