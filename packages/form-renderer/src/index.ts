// Public surface of @aip/form-renderer (FORMS-02): the shared JSONLogic evaluator and the form
// answer evaluator. No React in this task — FORMS-03 adds the components. There is deliberately no
// way to register a JSONLogic operator: the allow-list is the whole point (ADR 0035 §1).

export { ALLOWED_OPERATORS, GuardError, evaluateGuard, truthy, validateGuard } from "./logic/jsonlogic";
export { EVALUATOR_VERSION, evaluateAnswers } from "./logic/evaluate";

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
