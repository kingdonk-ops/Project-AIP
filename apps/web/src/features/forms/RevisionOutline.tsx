/**
 * A read-only outline of one revision (FORMS-04): each section with its fields (label, key, field
 * type, Required / Conditional), the schema hash once published, and the raw JSON behind a toggle.
 * It never renders form inputs: previewing the form itself is FORMS-03's renderer (a follow-up).
 */
import type { RevisionOut } from "@aip/api-client";
import { useId } from "react";
import { t } from "../shell/t";
import { RevisionStatusChip } from "./columns";

/** FORMS-01's field types; each has an `item_types.field_type.<type>` term (ITEMTYPES-01). */
const FIELD_TYPES = new Set([
  "text",
  "number",
  "decimal",
  "date",
  "dropdown",
  "multi_select",
  "measurement",
  "boolean",
  "photo",
  "signature",
  "asset_ref",
  "user_ref",
]);

type Obj = Record<string, unknown>;

function isObject(value: unknown): value is Obj {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function fieldTypeLabel(type: string): string {
  return FIELD_TYPES.has(type) ? t(`item_types.field_type.${type}`) : type;
}

function OutlineSection({ section }: { section: Obj }) {
  const id = useId();
  const fields = (Array.isArray(section.fields) ? section.fields : []).filter(isObject);
  const label = str(section.label) || str(section.key);
  return (
    <section className="forms-outline__section" aria-labelledby={id}>
      <h4 id={id} className="forms-outline__section-title">
        {label}
        {" "}
        <code className="forms-mono">{str(section.key)}</code>
      </h4>
      <div className="aip-table__wrap">
        <table className="aip-table forms-outline__table">
          <caption className="aip-table__caption">{t("forms.templates.outline.fields", { section: label })}</caption>
          <thead className="aip-table__header">
            <tr className="aip-table__row">
              <th scope="col" className="aip-table__head">
                {t("forms.templates.outline.field_label")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.outline.field_key")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.outline.field_type")}
              </th>
              <th scope="col" className="aip-table__head">
                {t("forms.templates.outline.field_flags")}
              </th>
            </tr>
          </thead>
          <tbody className="aip-table__body">
            {fields.map((field, index) => {
              const flags = [
                field.required === true ? t("forms.templates.outline.required") : null,
                field.visibleIf !== undefined || field.requiredIf !== undefined
                  ? t("forms.templates.outline.conditional")
                  : null,
              ].filter(Boolean);
              return (
                <tr key={`${index}-${str(field.key)}`} className="aip-table__row">
                  <td className="aip-table__cell">{str(field.label)}</td>
                  <td className="aip-table__cell forms-mono">{str(field.key)}</td>
                  <td className="aip-table__cell">{fieldTypeLabel(str(field.type))}</td>
                  <td className="aip-table__cell">{flags.join(", ")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RevisionOutline({ revision }: { revision: RevisionOut }) {
  const id = useId();
  const schema: Obj = isObject(revision.schema) ? revision.schema : {};
  const sections = (Array.isArray(schema.sections) ? schema.sections : []).filter(isObject);
  return (
    <section className="forms-outline" aria-labelledby={id}>
      <div className="forms-outline__header">
        <h3 id={id}>{t("forms.templates.outline.title", { n: revision.revisionNo })}</h3>
        <RevisionStatusChip status={revision.status} />
      </div>
      {revision.schemaHash ? (
        <dl className="forms-outline__meta">
          <dt>{t("forms.templates.outline.hash")}</dt>
          <dd className="forms-mono forms-outline__hash">{revision.schemaHash}</dd>
        </dl>
      ) : null}
      {sections.map((section, index) => (
        <OutlineSection key={`${index}-${str(section.key)}`} section={section} />
      ))}
      <details className="forms-outline__json">
        <summary>{t("forms.templates.outline.json")}</summary>
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must take focus so keyboard users can scroll it (axe scrollable-region-focusable) */}
        <pre className="forms-mono" tabIndex={0}>
          {JSON.stringify(revision.schema, null, 2)}
        </pre>
      </details>
    </section>
  );
}
