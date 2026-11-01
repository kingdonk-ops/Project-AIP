// The shared form answer evaluator (FORMS-02; per-section results and section rules, FORMS-10): the
// TypeScript twin of apps/api/aip/modules/forms/evaluator.py. Given a frozen revision schema and a
// set of answers it decides which fields are visible and required, which answers are invalid and
// which fail, and whether each section is complete. It is
// pure (no I/O) and reaches JSONLogic only through ./jsonlogic. The golden vectors in
// packages/contracts/jsonlogic-vectors/forms prove it identical to the Python evaluator; that
// folder's README is the authoritative spec.

import { evaluateGuard, GuardError, truthy } from "./jsonlogic";
import type {
  AnswerError,
  AnswerEvaluation,
  Answers,
  AnswerValue,
  EvaluationContext,
  EvaluationMode,
  ExpressionError,
  ExpressionKind,
  FieldType,
  FormField,
  FormSchema,
  FormSection,
  Json,
  SectionResult,
} from "./types";

export const EVALUATOR_VERSION = "2";

const MISSING = Symbol("missing");
type Answer = AnswerValue | typeof MISSING;

const OPTION_TYPES: ReadonlySet<FieldType> = new Set(["dropdown", "multi_select"]);
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// --- answer helpers --------------------------------------------------------------------------

function isEmpty(value: Answer, ftype: FieldType): boolean {
  if (value === MISSING || value === null || value === "") return true;
  if (Array.isArray(value) && value.length === 0) return true;
  if (ftype === "measurement" && isObject(value)) {
    return value["value"] === null || value["value"] === undefined;
  }
  return false;
}

function isIntegerNumber(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value);
}

function isFiniteNumber(value: unknown): boolean {
  return typeof value === "number" && Number.isFinite(value);
}

function isRealDate(value: unknown): boolean {
  if (typeof value !== "string" || !DATE_RE.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  if (month < 1 || month > 12) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= (days[month - 1] as number);
}

function isUuid(value: unknown): boolean {
  return typeof value === "string" && UUID_RE.test(value);
}

function isFileRef(value: unknown): boolean {
  return (
    isObject(value) &&
    Object.keys(value).length === 1 &&
    Object.hasOwn(value, "fileId") &&
    isUuid(value["fileId"])
  );
}

function typeOk(ftype: FieldType, value: unknown, unit: string | undefined): boolean {
  switch (ftype) {
    case "text":
    case "dropdown":
      return typeof value === "string";
    case "number":
      return isIntegerNumber(value);
    case "decimal":
      return isFiniteNumber(value);
    case "date":
      return isRealDate(value);
    case "multi_select":
      return (
        Array.isArray(value) &&
        value.every((v) => typeof v === "string") &&
        new Set(value).size === value.length
      );
    case "measurement":
      return isObject(value) && isFiniteNumber(value["value"]) && value["unit"] === unit;
    case "boolean":
      return typeof value === "boolean";
    case "photo":
      return Array.isArray(value) && value.every((v) => isFileRef(v));
    case "signature":
      return isFileRef(value);
    case "asset_ref":
    case "user_ref":
      return isUuid(value);
    default:
      return false;
  }
}

// --- field model and ordering ----------------------------------------------------------------

interface FieldNode {
  key: string;
  sectionKey: string;
  type: FieldType;
  spec: FormField;
  docIndex: number;
}

interface Ordered {
  order: string[];
  fields: Map<string, FieldNode>;
  sections: Map<string, FormSection>;
}

function buildOrder(schema: FormSchema): Ordered {
  const fields = new Map<string, FieldNode>();
  const sections = new Map<string, FormSection>();
  const doc = new Map<string, number>();
  let next = 0;
  for (const section of schema.sections) {
    sections.set(section.key, section);
    doc.set(section.key, next++);
    for (const spec of section.fields) {
      doc.set(spec.key, next++);
      fields.set(spec.key, {
        key: spec.key,
        sectionKey: section.key,
        type: spec.type,
        spec,
        docIndex: doc.get(spec.key) as number,
      });
    }
  }

  const fieldKeys = new Set(fields.keys());
  const deps = new Map<string, Set<string>>();
  for (const [key, section] of sections) deps.set(key, reads(section.visibleIf, fieldKeys));
  for (const [key, node] of fields) {
    const r = reads(node.spec.visibleIf, fieldKeys);
    for (const k of reads(node.spec.requiredIf, fieldKeys)) r.add(k);
    r.add(node.sectionKey); // a field is placed after its own section
    deps.set(key, r);
  }

  return { order: toposort(deps, doc), fields, sections };
}

function toposort(deps: Map<string, Set<string>>, doc: Map<string, number>): string[] {
  const done = new Set<string>();
  const order: string[] = [];
  const remaining = new Set(deps.keys());
  const byDoc = (a: string, b: string): number => (doc.get(a) as number) - (doc.get(b) as number);
  while (remaining.size > 0) {
    let ready = [...remaining]
      .filter((n) => [...(deps.get(n) as Set<string>)].every((d) => done.has(d)))
      .sort(byDoc);
    if (ready.length === 0) {
      // a residual cycle: break it by document order, deterministically
      ready = [[...remaining].sort(byDoc)[0] as string];
    }
    for (const node of ready) {
      order.push(node);
      done.add(node);
      remaining.delete(node);
    }
  }
  return order;
}

function reads(expr: Json | undefined, fieldKeys: Set<string>): Set<string> {
  const out = new Set<string>();
  for (const v of iterVars(expr)) {
    if (typeof v === "string" && v.startsWith("answers.")) {
      const key = v.slice("answers.".length).split(".")[0] as string;
      if (fieldKeys.has(key)) out.add(key);
    }
  }
  return out;
}

function iterVars(node: unknown): unknown[] {
  const out: unknown[] = [];
  const walk = (n: unknown): void => {
    if (isObject(n)) {
      const keys = Object.keys(n);
      if (keys.length === 1 && keys[0] === "var") {
        const arg = n["var"];
        out.push(Array.isArray(arg) && arg.length > 0 ? arg[0] : arg);
        return;
      }
      for (const value of Object.values(n)) walk(value);
    } else if (Array.isArray(n)) {
      for (const item of n) walk(item);
    }
  };
  walk(node);
  return out;
}

/** Evaluate `expr` for truthiness; on a GuardError return `[true, message]` (fail closed). */
function guard(expr: Json, data: Record<string, Json>): [boolean, string | null] {
  try {
    return [truthy(evaluateGuard(expr, data)), null];
  } catch (error) {
    if (error instanceof GuardError) return [true, error.message];
    throw error;
  }
}

// --- the evaluation --------------------------------------------------------------------------

export interface EvaluateOptions {
  mode?: EvaluationMode;
  context?: EvaluationContext | Record<string, Json> | null;
}

export function evaluateAnswers(
  schema: FormSchema,
  answers: Answers,
  options: EvaluateOptions = {},
): AnswerEvaluation {
  const mode = options.mode ?? "submit";
  const ctx = (options.context ?? {}) as Record<string, Json>;
  const { order, fields, sections } = buildOrder(schema);

  const visible: Record<string, boolean> = {};
  const required: Record<string, boolean> = {};
  const sectionVisible: Record<string, boolean> = {};
  const expressionErrors: ExpressionError[] = [];
  const visibleAnswers: Record<string, Json> = {};

  const data = (): Record<string, Json> => ({ answers: { ...visibleAnswers }, context: ctx });

  const recordExpr = (fieldKey: string, expression: ExpressionKind, message: string): void => {
    expressionErrors.push({ fieldKey, expression, message });
  };

  // Pass 1: visibility and required, topologically, accumulating visible answers.
  for (const node of order) {
    const section = sections.get(node);
    if (section !== undefined) {
      if (section.visibleIf === undefined) {
        sectionVisible[node] = true;
      } else {
        const [ok, message] = guard(section.visibleIf, data());
        sectionVisible[node] = ok;
        if (message !== null) recordExpr(node, "visibleIf", message);
      }
      continue;
    }

    const field = fields.get(node) as FieldNode;
    let fieldVis = true;
    if (field.spec.visibleIf !== undefined) {
      const [ok, message] = guard(field.spec.visibleIf, data());
      fieldVis = ok;
      if (message !== null) recordExpr(field.key, "visibleIf", message);
    }
    const isVisible = (sectionVisible[field.sectionKey] ?? true) && fieldVis;
    visible[field.key] = isVisible;

    // Own keys only: a field keyed e.g. "constructor" must not read Object.prototype.
    if (isVisible && Object.hasOwn(answers, field.key)) {
      visibleAnswers[field.key] = answers[field.key] as Json;
    }

    let req = false;
    if (isVisible) {
      if (field.spec.required === true) {
        req = true;
      } else if (field.spec.requiredIf !== undefined) {
        const [ok, message] = guard(field.spec.requiredIf, data());
        req = ok;
        if (message !== null) recordExpr(field.key, "requiredIf", message);
      }
    }
    required[field.key] = req;
  }

  // Pass 2: errors, failed and ignored, in document order.
  const errors: AnswerError[] = [];
  const failed: string[] = [];
  const ignored: string[] = [];
  const fieldKeys = new Set(fields.keys());
  const ordered = [...fields.values()].sort((a, b) => a.docIndex - b.docIndex);
  for (const field of ordered) {
    const answer: Answer = Object.hasOwn(answers, field.key) ? (answers[field.key] as Json) : MISSING;
    if (!visible[field.key]) {
      if (answer !== MISSING) ignored.push(field.key);
      continue;
    }

    const error = fieldError(field, answer, required[field.key] ?? false, mode, data(), recordExpr);
    if (error !== null) errors.push(error);

    if (!isEmpty(answer, field.type) && field.spec.failWhen !== undefined) {
      const [failing, message] = guard(field.spec.failWhen, data());
      if (failing) failed.push(field.key);
      if (message !== null) recordExpr(field.key, "failWhen", message);
    }
  }

  for (const key of Object.keys(answers).filter((k) => !fieldKeys.has(k)).sort()) {
    errors.push({ fieldKey: key, code: "UNKNOWN_FIELD", messageKey: "forms.answer.UNKNOWN_FIELD", params: {} });
  }

  // Pass 3: per-section results and section rules, in document order.
  const sectionResults = buildSectionResults(
    sections,
    fields,
    answers,
    { sectionVisible, visible, required, errors, failed },
    data(),
    recordExpr,
  );
  const rulesPass = Object.values(sectionResults).every((r) => r.ruleFailures.length === 0);

  return {
    visible,
    required,
    errors,
    failed,
    ignored,
    expressionErrors,
    complete: errors.length === 0 && rulesPass,
    sections: sectionResults,
  };
}

interface FieldVerdicts {
  sectionVisible: Record<string, boolean>;
  visible: Record<string, boolean>;
  required: Record<string, boolean>;
  errors: AnswerError[];
  failed: string[];
}

/**
 * Each section's result. `missingRequired` ignores `mode` (a section tick always checks required
 * answers); a rule runs only in a visible section and fails closed on a GuardError.
 */
function buildSectionResults(
  sections: Map<string, FormSection>,
  fields: Map<string, FieldNode>,
  answers: Answers,
  verdicts: FieldVerdicts,
  data: Record<string, Json>,
  recordExpr: (fieldKey: string, expression: ExpressionKind, message: string) => void,
): Record<string, SectionResult> {
  const invalidKeys = new Set(
    verdicts.errors
      .filter((e) => e.code !== "REQUIRED" && e.code !== "UNKNOWN_FIELD")
      .map((e) => e.fieldKey),
  );
  const failedKeys = new Set(verdicts.failed);
  const results: Record<string, SectionResult> = {};
  for (const [sectionKey, section] of sections) {
    const keys = section.fields.map((spec) => spec.key);
    const isVisible = verdicts.sectionVisible[sectionKey] ?? true;
    const missingRequired = keys.filter((k) => {
      const answer: Answer = Object.hasOwn(answers, k) ? (answers[k] as Json) : MISSING;
      return (
        verdicts.visible[k] === true &&
        verdicts.required[k] === true &&
        isEmpty(answer, (fields.get(k) as FieldNode).type)
      );
    });
    const ruleFailures: string[] = [];
    if (isVisible) {
      for (const rule of section.rules ?? []) {
        const [passing, message] = guard(rule.expr, data);
        if (message !== null) {
          recordExpr(rule.key, "rule", message);
          ruleFailures.push(rule.key);
        } else if (!passing) {
          ruleFailures.push(rule.key);
        }
      }
    }
    const invalid = keys.filter((k) => invalidKeys.has(k));
    results[sectionKey] = {
      visible: isVisible,
      missingRequired,
      invalid,
      failed: keys.filter((k) => failedKeys.has(k)),
      ruleFailures,
      complete: isVisible && missingRequired.length === 0 && invalid.length === 0 && ruleFailures.length === 0,
    };
  }
  return results;
}

function fieldError(
  field: FieldNode,
  answer: Answer,
  isRequired: boolean,
  mode: EvaluationMode,
  data: Record<string, Json>,
  recordExpr: (fieldKey: string, expression: ExpressionKind, message: string) => void,
): AnswerError | null {
  const { key, type } = field;
  if (isEmpty(answer, type)) {
    if (mode === "submit" && isRequired) return error(key, "REQUIRED");
    return null;
  }

  if (!typeOk(type, answer, field.spec.unit)) return error(key, "WRONG_TYPE");

  const optionError = checkOption(field, answer as Json);
  if (optionError !== null) return optionError;

  const boundError = checkBound(field, answer as Json);
  if (boundError !== null) return boundError;

  return ruleError(field, data, recordExpr);
}

function error(fieldKey: string, code: string, params: Record<string, unknown> = {}): AnswerError {
  return { fieldKey, code, messageKey: `forms.answer.${code}`, params };
}

function checkOption(field: FieldNode, answer: Json): AnswerError | null {
  if (!OPTION_TYPES.has(field.type)) return null;
  const values = new Set((field.spec.options ?? []).map((option) => option.value));
  const chosen = Array.isArray(answer) ? answer : [answer];
  if (chosen.some((value) => typeof value !== "string" || !values.has(value))) {
    return error(field.key, "NOT_AN_OPTION");
  }
  return null;
}

function checkBound(field: FieldNode, answer: Json): AnswerError | null {
  const v = field.spec.validations ?? {};
  if (field.type === "number" || field.type === "decimal" || field.type === "measurement") {
    const value =
      field.type === "measurement" ? (answer as Record<string, Json>)["value"] : answer;
    return rangeError(field.key, value as number, v.min, v.max, "BELOW_MIN", "ABOVE_MAX", "min", "max");
  }
  if (field.type === "text") {
    const length = typeof answer === "string" ? [...answer].length : 0;
    return rangeError(
      field.key,
      length,
      v.minLength,
      v.maxLength,
      "TOO_SHORT",
      "TOO_LONG",
      "minLength",
      "maxLength",
    );
  }
  if (field.type === "multi_select" || field.type === "photo") {
    const count = Array.isArray(answer) ? answer.length : 0;
    return rangeError(field.key, count, v.minItems, v.maxItems, "TOO_FEW", "TOO_MANY", "minItems", "maxItems");
  }
  return null;
}

function rangeError(
  key: string,
  value: number,
  low: number | undefined,
  high: number | undefined,
  lowCode: string,
  highCode: string,
  lowParam: string,
  highParam: string,
): AnswerError | null {
  if (low !== undefined && value < low) return error(key, lowCode, { [lowParam]: low });
  if (high !== undefined && value > high) return error(key, highCode, { [highParam]: high });
  return null;
}

function ruleError(
  field: FieldNode,
  data: Record<string, Json>,
  recordExpr: (fieldKey: string, expression: ExpressionKind, message: string) => void,
): AnswerError | null {
  for (const rule of field.spec.rules ?? []) {
    const [passing, message] = guard(rule.rule, data);
    if (message !== null) {
      recordExpr(field.key, "rule", message);
      return { fieldKey: field.key, code: "RULE_FAILED", messageKey: rule.messageKey, params: {} };
    }
    if (!passing) {
      return { fieldKey: field.key, code: "RULE_FAILED", messageKey: rule.messageKey, params: {} };
    }
  }
  return null;
}
