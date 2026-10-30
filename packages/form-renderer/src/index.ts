// Public surface of @aip/form-renderer. FORMS-02: the shared JSONLogic evaluator and the form answer
// evaluator. FORMS-03: the React renderer and the adapter types (its only way out; no network code).
// There is deliberately no way to register a JSONLogic operator: the allow-list is the whole point
// (ADR 0035 §1). Styles: import "@aip/form-renderer/styles.css" next to "@aip/ui/styles.css".

export { ALLOWED_OPERATORS, GuardError, evaluateGuard, truthy, validateGuard } from "./logic/jsonlogic";
export { EVALUATOR_VERSION, evaluateAnswers } from "./logic/evaluate";
export { FormRenderer } from "./FormRenderer";

export type { FormRendererProps } from "./FormRenderer";
export type {
  MediaAdapter,
  MediaKind,
  PickedFile,
  ReferenceAdapter,
  ReferenceItem,
  ReferenceKind,
  RendererAdapters,
} from "./adapters";
export type { EvaluateOptions } from "./logic/evaluate";
export type {
  AnswerError,
  AnswerEvaluation,
  Answers,
  AnswerValue,
  EvaluationContext,
  EvaluationMode,
  ExpressionError,
  ExpressionKind,
  FieldOption,
  FieldType,
  FieldValidations,
  FormField,
  FormRule,
  FormSchema,
  FormSection,
  Json,
} from "./logic/types";
