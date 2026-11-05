/**
 * The form designer's model (FORMS-11): pure, immutable operations on a FORMS-01 template schema.
 * Each returns a new schema and never mutates its input. Properties the designer does not know
 * (and the logic it cannot edit yet: `visibleIf`, `requiredIf`, `failWhen`, `rules`, term keys) are
 * copied through unchanged, so what the designer saves is what a JSON upload of the same template
 * would save. Whether the result is valid is the server lint's call, not this module's.
 *
 * Logic reads answers as `{"var": "answers.<key>"}` (or `answers.<key>.<part>`), so renaming a key
 * rewrites those references, and removing an item reports the keys whose logic still reads it.
 */
import fieldTypes from "@aip/contracts/field-types";
import unitContract from "@aip/contracts/units";
import type {
  FieldOption,
  FieldType,
  FieldValidations,
  FormField,
  FormSchema,
  FormSection,
  Json,
} from "@aip/form-renderer";
import type { IssuePath } from "../issues";
import { isValidKey, keyFromLabel } from "./keys";

/** The field types a form may use, in the contract's order (12 in R1). */
export const FORM_FIELD_TYPES: readonly FieldType[] = fieldTypes.fieldTypes
  .filter((entry) => entry.usableIn.includes("form"))
  .map((entry) => entry.key as FieldType);

/** The units the server lint accepts for a measurement (TERMS-03's unit contract). */
export const MEASUREMENT_UNITS: readonly string[] = Object.keys(unitContract.units);

export const OPTION_TYPES: ReadonlySet<FieldType> = new Set<FieldType>(["dropdown", "multi_select"]);

type ValidationKey = keyof FieldValidations;

/** The validations the lint allows per type; any other type takes none. */
export const VALIDATION_KEYS: Readonly<Partial<Record<FieldType, readonly ValidationKey[]>>> = {
  number: ["min", "max"],
  decimal: ["min", "max"],
  measurement: ["min", "max"],
  text: ["minLength", "maxLength"],
  multi_select: ["minItems", "maxItems"],
  photo: ["minItems", "maxItems"],
};

/** Field properties the designer keeps but cannot edit yet (FORMS-12 adds their builders). */
export const FIELD_LOGIC_PROPS = [
  "visibleIf",
  "requiredIf",
  "failWhen",
  "rules",
  "labelKey",
  "helpKey",
  "failMessageKey",
] as const;
export const SECTION_LOGIC_PROPS = ["visibleIf", "rules", "labelKey"] as const;

export type Selection = { kind: "section" | "field"; key: string } | null;

/** Labels the UI passes in (from terms); the model never invents user-facing text of its own. */
export interface NewFieldLabels {
  field?: string;
  option?: string;
}

// --- reading ------------------------------------------------------------------------------------

/** Every section, field and section-rule key: one namespace in the contract. */
export function allKeys(schema: FormSchema): string[] {
  const keys: string[] = [];
  for (const section of schema.sections) {
    keys.push(section.key);
    for (const field of section.fields) keys.push(field.key);
    for (const rule of section.rules ?? []) keys.push(rule.key);
  }
  return keys;
}

export interface FieldLocation {
  section: FormSection;
  sectionIndex: number;
  field: FormField;
  fieldIndex: number;
}

export function findField(schema: FormSchema, key: string): FieldLocation | undefined {
  for (const [sectionIndex, section] of schema.sections.entries()) {
    const fieldIndex = section.fields.findIndex((f) => f.key === key);
    if (fieldIndex >= 0) return { section, sectionIndex, field: section.fields[fieldIndex]!, fieldIndex };
  }
  return undefined;
}

export function findSection(schema: FormSchema, key: string): FormSection | undefined {
  return schema.sections.find((s) => s.key === key);
}

/** Which logic properties of a field or section are set (shown as "Logic set" chips). */
export function logicSet(item: object, props: readonly string[]): string[] {
  return props.filter((prop) => prop in item && (item as Record<string, unknown>)[prop] !== undefined);
}

function forEachVar(node: unknown, visit: (path: string) => void): void {
  if (Array.isArray(node)) {
    for (const item of node) forEachVar(item, visit);
    return;
  }
  if (typeof node !== "object" || node === null) return;
  const entries = Object.entries(node);
  if (entries.length === 1 && entries[0]![0] === "var") {
    const arg = entries[0]![1];
    const path = Array.isArray(arg) ? arg[0] : arg;
    if (typeof path === "string") visit(path);
    return;
  }
  for (const [, value] of entries) forEachVar(value, visit);
}

function readsKey(expr: unknown, key: string): boolean {
  let found = false;
  forEachVar(expr, (path) => {
    if (path === `answers.${key}` || path.startsWith(`answers.${key}.`)) found = true;
  });
  return found;
}

/** Each item's expressions: a field's conditions and rules, a section's `visibleIf` and its rules. */
function expressionsByOwner(schema: FormSchema): { owner: string; section: string; exprs: unknown[] }[] {
  const out: { owner: string; section: string; exprs: unknown[] }[] = [];
  for (const section of schema.sections) {
    out.push({ owner: section.key, section: section.key, exprs: [section.visibleIf] });
    for (const rule of section.rules ?? []) out.push({ owner: rule.key, section: section.key, exprs: [rule.expr] });
    for (const field of section.fields) {
      out.push({
        owner: field.key,
        section: section.key,
        exprs: [field.visibleIf, field.requiredIf, field.failWhen, ...(field.rules ?? []).map((r) => r.rule)],
      });
    }
  }
  return out;
}

/** The keys of the items whose logic reads `key` (excluding the item itself). */
export function referencesTo(schema: FormSchema, key: string): string[] {
  return expressionsByOwner(schema)
    .filter(({ owner, exprs }) => owner !== key && exprs.some((e) => readsKey(e, key)))
    .map(({ owner }) => owner);
}

// --- helpers ------------------------------------------------------------------------------------

function clamp(at: number, length: number): number {
  return Math.max(0, Math.min(Number.isFinite(at) ? Math.trunc(at) : length, length));
}

function insert<T>(items: readonly T[], at: number, item: T): T[] {
  const next = [...items];
  next.splice(clamp(at, items.length), 0, item);
  return next;
}

/** Copy `item` with `patch` applied; a key set to `undefined` is removed. */
function patched<T extends object>(item: T, patch: Partial<T>): T {
  const next: Record<string, unknown> = { ...item };
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined) delete next[key];
    else next[key] = value;
  }
  return next as T;
}

function mapSections(schema: FormSchema, fn: (section: FormSection) => FormSection): FormSchema {
  return { ...schema, sections: schema.sections.map(fn) };
}

function defaultOptions(labels: NewFieldLabels): FieldOption[] {
  const label = labels.option ?? "Option 1";
  return [{ value: keyFromLabel(label, []), label }];
}

// --- sections -----------------------------------------------------------------------------------

export function addSection(schema: FormSchema, at: number, label = "Section"): { schema: FormSchema; key: string } {
  const key = keyFromLabel(label, allKeys(schema));
  const section: FormSection = { key, label, fields: [] };
  return { schema: { ...schema, sections: insert(schema.sections, at, section) }, key };
}

export function moveSection(schema: FormSchema, key: string, to: number): FormSchema {
  const from = schema.sections.findIndex((s) => s.key === key);
  if (from < 0) return schema;
  const rest = schema.sections.filter((s) => s.key !== key);
  const target = clamp(to, rest.length);
  if (target === from) return schema;
  return { ...schema, sections: insert(rest, target, schema.sections[from]!) };
}

/** Removes a section and its fields; `referencedBy` lists the outside keys whose logic read them. */
export function removeSection(schema: FormSchema, key: string): { schema: FormSchema; referencedBy: string[] } {
  const section = findSection(schema, key);
  if (!section) return { schema, referencedBy: [] };
  const inside = new Set(allKeys({ ...schema, sections: [section] }));
  const referencedBy = new Set<string>();
  for (const removed of inside) {
    for (const owner of referencesTo(schema, removed)) if (!inside.has(owner)) referencedBy.add(owner);
  }
  return { schema: { ...schema, sections: schema.sections.filter((s) => s.key !== key) }, referencedBy: [...referencedBy] };
}

export function updateSection(schema: FormSchema, key: string, patch: Partial<FormSection>): FormSchema {
  if (!findSection(schema, key)) return schema;
  return mapSections(schema, (s) => (s.key === key ? patched(s, patch) : s));
}

// --- fields -------------------------------------------------------------------------------------

export function newField(type: FieldType, key: string, label: string, labels: NewFieldLabels = {}): FormField {
  const field: FormField = { key, type, label };
  if (OPTION_TYPES.has(type)) field.options = defaultOptions(labels);
  if (type === "measurement") field.unit = MEASUREMENT_UNITS[0]!;
  return field;
}

export function addField(
  schema: FormSchema,
  type: FieldType,
  sectionKey: string,
  at: number,
  labels: NewFieldLabels = {},
): { schema: FormSchema; key: string } {
  if (!findSection(schema, sectionKey)) return { schema, key: "" };
  const label = labels.field ?? type;
  const key = keyFromLabel(label, allKeys(schema));
  const field = newField(type, key, label, labels);
  const next = mapSections(schema, (s) => (s.key === sectionKey ? { ...s, fields: insert(s.fields, at, field) } : s));
  return { schema: next, key };
}

export function moveField(schema: FormSchema, key: string, toSection: string, to: number): FormSchema {
  const location = findField(schema, key);
  if (!location || !findSection(schema, toSection)) return schema;
  if (location.section.key === toSection) {
    const rest = location.section.fields.filter((f) => f.key !== key);
    const target = clamp(to, rest.length);
    if (target === location.fieldIndex) return schema;
  }
  const without = mapSections(schema, (s) =>
    s.key === location.section.key ? { ...s, fields: s.fields.filter((f) => f.key !== key) } : s,
  );
  return mapSections(without, (s) => (s.key === toSection ? { ...s, fields: insert(s.fields, to, location.field) } : s));
}

export function removeField(schema: FormSchema, key: string): { schema: FormSchema; referencedBy: string[] } {
  const location = findField(schema, key);
  if (!location) return { schema, referencedBy: [] };
  const referencedBy = referencesTo(schema, key);
  const next = mapSections(schema, (s) =>
    s.key === location.section.key ? { ...s, fields: s.fields.filter((f) => f.key !== key) } : s,
  );
  return { schema: next, referencedBy };
}

export function updateField(schema: FormSchema, key: string, patch: Partial<FormField>): FormSchema {
  if (!findField(schema, key)) return schema;
  return mapSections(schema, (s) =>
    s.fields.some((f) => f.key === key)
      ? { ...s, fields: s.fields.map((f) => (f.key === key ? patched(f, patch) : f)) }
      : s,
  );
}

/** Sets one validation (`undefined` removes it; an empty `validations` is dropped). */
export function setValidation(schema: FormSchema, key: string, name: ValidationKey, value: number | undefined): FormSchema {
  const location = findField(schema, key);
  if (!location) return schema;
  const validations = patched<FieldValidations>(location.field.validations ?? {}, { [name]: value });
  return updateField(schema, key, { validations: Object.keys(validations).length ? validations : undefined });
}

/**
 * Changes a field's type: drops `options`, `unit` and `validations` the new type does not take,
 * adds the new type's defaults (one option, a unit), and keeps the field's logic.
 */
export function changeFieldType(
  schema: FormSchema,
  key: string,
  type: FieldType,
  labels: NewFieldLabels = {},
): FormSchema {
  const location = findField(schema, key);
  if (!location || location.field.type === type) return schema;
  const field = location.field;
  const patch: Partial<FormField> = { type };
  if (OPTION_TYPES.has(type)) {
    if (!field.options?.length) patch.options = defaultOptions(labels);
  } else patch.options = undefined;
  if (type === "measurement") {
    if (!field.unit) patch.unit = MEASUREMENT_UNITS[0]!;
  } else patch.unit = undefined;
  const allowed = new Set(VALIDATION_KEYS[type] ?? []);
  const kept = Object.fromEntries(
    Object.entries(field.validations ?? {}).filter(([name]) => allowed.has(name as ValidationKey)),
  ) as FieldValidations;
  patch.validations = Object.keys(kept).length ? kept : undefined;
  return updateField(schema, key, patch);
}

// --- keys ---------------------------------------------------------------------------------------

function rewriteVars(node: Json | undefined, from: string, to: string): Json | undefined {
  if (node === undefined || node === null || typeof node !== "object") return node;
  if (Array.isArray(node)) return node.map((item) => rewriteVars(item, from, to) as Json);
  const entries = Object.entries(node);
  const rename = (path: Json): Json => {
    if (typeof path !== "string") return path;
    const old = `answers.${from}`;
    if (path === old) return `answers.${to}`;
    if (path.startsWith(`${old}.`)) return `answers.${to}${path.slice(old.length)}`;
    return path;
  };
  if (entries.length === 1 && entries[0]![0] === "var") {
    const arg = entries[0]![1];
    if (Array.isArray(arg) && arg.length > 0) return { var: [rename(arg[0]!), ...arg.slice(1)] };
    return { var: rename(arg) };
  }
  return Object.fromEntries(entries.map(([k, v]) => [k, rewriteVars(v, from, to) as Json]));
}

function rewriteField(field: FormField, from: string, to: string): FormField {
  const next: FormField = { ...field };
  for (const prop of ["visibleIf", "requiredIf", "failWhen"] as const) {
    if (next[prop] !== undefined) next[prop] = rewriteVars(next[prop], from, to)!;
  }
  if (next.rules) next.rules = next.rules.map((r) => ({ ...r, rule: rewriteVars(r.rule, from, to)! }));
  return next;
}

/**
 * Renames a section, field or section-rule key and rewrites every `answers.<old>` reference in
 * every field's and section's logic. Returns the schema unchanged when `from` is not a key.
 * Validity of `to` (pattern, uniqueness) is the caller's check (`keyError`).
 */
export function renameKey(schema: FormSchema, from: string, to: string): FormSchema {
  if (from === to || !allKeys(schema).includes(from)) return schema;
  return mapSections(schema, (section) => {
    const next: FormSection = {
      ...section,
      key: section.key === from ? to : section.key,
      fields: section.fields.map((f) => rewriteField(f.key === from ? { ...f, key: to } : f, from, to)),
    };
    if (section.visibleIf !== undefined) next.visibleIf = rewriteVars(section.visibleIf, from, to)!;
    if (section.rules) {
      next.rules = section.rules.map((r) => ({
        ...r,
        key: r.key === from ? to : r.key,
        expr: rewriteVars(r.expr, from, to)!,
      }));
    }
    return next;
  });
}

/** Why `to` cannot replace `from` as a key: `"invalid"` (pattern), `"taken"`, or null when it can. */
export function keyError(schema: FormSchema, from: string, to: string): "invalid" | "taken" | null {
  if (to === from) return null;
  if (!isValidKey(to)) return "invalid";
  return allKeys(schema).includes(to) ? "taken" : null;
}

// --- lint issues --------------------------------------------------------------------------------

/** The section or field a lint issue's path points into, if any. */
export function issueTarget(schema: FormSchema, path: IssuePath): Selection {
  if (path[0] !== "sections" || typeof path[1] !== "number") return null;
  const section = schema.sections[path[1]];
  if (!section) return null;
  if (path[2] === "fields" && typeof path[3] === "number") {
    const field = section.fields[path[3]];
    if (field) return { kind: "field", key: field.key };
  }
  return { kind: "section", key: section.key };
}

/** Issue count per section or field key (a field's issues are not also counted on its section). */
export function issueCounts(schema: FormSchema, paths: readonly IssuePath[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const path of paths) {
    const target = issueTarget(schema, path);
    if (target) counts.set(target.key, (counts.get(target.key) ?? 0) + 1);
  }
  return counts;
}

/** The schema a template starts with in the designer (labels come from terms). */
export function starterSchema(sectionLabel: string, fieldLabel: string): FormSchema {
  return {
    schemaVersion: 2,
    sections: [{ key: "section_1", label: sectionLabel, fields: [{ key: "field_1", type: "text", label: fieldLabel }] }],
  };
}
