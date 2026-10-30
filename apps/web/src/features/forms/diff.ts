/**
 * Structural compare of two form revisions (FORMS-04): which sections and fields were added,
 * removed, changed or moved, not a text diff. Sections match by `key`; fields match by `key` across
 * the whole revision, because section and field keys share one namespace (FORMS-01), so a field
 * that changes section is one "moved" field, not a removal plus an addition.
 *
 * Every property except `key` (and a section's `fields`) is compared as canonical JSON, so changes
 * to labels, types, `required`, `options`, `unit`, `validations`, `visibleIf`, `requiredIf`,
 * `failWhen` and `rules` all show, and key order inside the JSON never does.
 */
import type { TemplateSchema } from "./templateJson";

export type ChangeKind = "added" | "removed" | "changed" | "moved";
export type ItemKind = "template" | "section" | "field";

export interface PropertyChange {
  name: string;
  /** `undefined` when the property is absent on that side. */
  before: unknown;
  after: unknown;
}

export interface SchemaChange {
  item: ItemKind;
  key: string;
  change: ChangeKind;
  /** The section the item is in (the target's; the source's for a removal). */
  section?: string;
  /** A field that changed section. */
  fromSection?: string;
  toSection?: string;
  /** Its position among the keys both revisions share changed. */
  reordered?: boolean;
  properties: PropertyChange[];
}

export interface SchemaDiff {
  changes: SchemaChange[];
  counts: Record<ChangeKind, number>;
}

type Obj = Record<string, unknown>;

interface Field {
  key: string;
  props: Obj;
  section: string;
}

interface Section {
  key: string;
  props: Obj;
  fields: Field[];
}

function isObject(value: unknown): value is Obj {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** JSON with object keys sorted, so `{"a":1,"b":2}` equals `{"b":2,"a":1}`. */
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (isObject(value)) {
    const keys = Object.keys(value)
      .filter((k) => value[k] !== undefined)
      .sort();
    return `{${keys.map((k) => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
  }
  return value === undefined ? "undefined" : JSON.stringify(value);
}

function sectionsOf(schema: TemplateSchema): Section[] {
  const raw = Array.isArray(schema.sections) ? schema.sections : [];
  return raw.flatMap((s: unknown) => {
    if (!isObject(s) || typeof s.key !== "string") return [];
    const sectionKey = s.key;
    const fields = (Array.isArray(s.fields) ? s.fields : []).flatMap((f: unknown) =>
      isObject(f) && typeof f.key === "string" ? [{ key: f.key, props: f, section: sectionKey }] : [],
    );
    return [{ key: sectionKey, props: s, fields }];
  });
}

function propertyChanges(before: Obj, after: Obj, skip: readonly string[]): PropertyChange[] {
  const names = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter((n) => !skip.includes(n)).sort();
  return names.flatMap((name) =>
    canonical(before[name]) === canonical(after[name]) ? [] : [{ name, before: before[name], after: after[name] }],
  );
}

/** Keys of `a` whose position among the keys `a` and `b` share differs in `b`. */
function reorderedKeys(a: readonly string[], b: readonly string[]): Set<string> {
  const inB = new Set(b);
  const inA = new Set(a);
  const commonA = a.filter((k) => inB.has(k));
  const commonB = b.filter((k) => inA.has(k));
  return new Set(commonA.filter((k, i) => commonB[i] !== k));
}

const SECTION_SKIP = ["key", "fields"] as const;
const FIELD_SKIP = ["key"] as const;

export function diffSchemas(from: TemplateSchema, to: TemplateSchema): SchemaDiff {
  const changes: SchemaChange[] = [];

  const top = propertyChanges(from, to, ["sections"]);
  if (top.length) changes.push({ item: "template", key: "", change: "changed", properties: top });

  const a = sectionsOf(from);
  const b = sectionsOf(to);
  const aSections = new Map(a.map((s) => [s.key, s]));
  const bSections = new Map(b.map((s) => [s.key, s]));
  const aFields = new Map(a.flatMap((s) => s.fields).map((f) => [f.key, f]));
  const bFields = new Map(b.flatMap((s) => s.fields).map((f) => [f.key, f]));
  const movedSections = reorderedKeys(
    a.map((s) => s.key),
    b.map((s) => s.key),
  );

  const removedFieldsOf = (section: Section) => {
    for (const field of section.fields) {
      if (!bFields.has(field.key)) {
        changes.push({ item: "field", key: field.key, change: "removed", section: section.key, properties: [] });
      }
    }
  };

  for (const section of b) {
    const old = aSections.get(section.key);
    if (!old) {
      changes.push({ item: "section", key: section.key, change: "added", section: section.key, properties: [] });
    } else {
      const properties = propertyChanges(old.props, section.props, SECTION_SKIP);
      const reordered = movedSections.has(section.key);
      if (reordered || properties.length) {
        changes.push({
          item: "section",
          key: section.key,
          change: reordered ? "moved" : "changed",
          section: section.key,
          ...(reordered ? { reordered } : {}),
          properties,
        });
      }
    }

    // Fields that stayed in this section and changed position among themselves.
    const stayed = (fields: readonly Field[]) =>
      fields.filter((f) => aFields.get(f.key)?.section === section.key && bFields.get(f.key)?.section === section.key);
    const movedFields = reorderedKeys(
      stayed(old?.fields ?? []).map((f) => f.key),
      stayed(section.fields).map((f) => f.key),
    );

    for (const field of section.fields) {
      const before = aFields.get(field.key);
      if (!before) {
        changes.push({ item: "field", key: field.key, change: "added", section: section.key, properties: [] });
        continue;
      }
      const properties = propertyChanges(before.props, field.props, FIELD_SKIP);
      if (before.section !== section.key) {
        changes.push({
          item: "field",
          key: field.key,
          change: "moved",
          section: section.key,
          fromSection: before.section,
          toSection: section.key,
          properties,
        });
      } else if (movedFields.has(field.key)) {
        changes.push({ item: "field", key: field.key, change: "moved", section: section.key, reordered: true, properties });
      } else if (properties.length) {
        changes.push({ item: "field", key: field.key, change: "changed", section: section.key, properties });
      }
    }
    if (old) removedFieldsOf(old);
  }

  for (const section of a) {
    if (bSections.has(section.key)) continue;
    changes.push({ item: "section", key: section.key, change: "removed", section: section.key, properties: [] });
    removedFieldsOf(section);
  }

  const counts: Record<ChangeKind, number> = { added: 0, removed: 0, changed: 0, moved: 0 };
  for (const c of changes) counts[c.change] += 1;
  return { changes, counts };
}
