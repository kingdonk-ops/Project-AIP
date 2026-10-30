/**
 * Inputs for an asset's attributes, generated from an item-type version's attribute definitions
 * (ASSETS-03). ITEMTYPES-03's field preview is a read-only list inside the web app, not a package
 * renderer, so this renders the field-type keys of `packages/contracts/field-types` itself: `text`,
 * `number`, `decimal`, `date`, `dropdown`, `multi_select`, `measurement` and `boolean`. `photo`,
 * `signature`, `asset_ref` and `user_ref` show a read-only note (uploads and reference pickers
 * arrive with ASSETS-05 / ITEMTYPES-04); their stored values are kept as they are.
 *
 * Labels and option labels come from the definitions, never from code. Form state holds the raw
 * input values (`RawValues`); `toAttributes` turns them into the API's JSON on save.
 */
import { FormField, Input } from "@aip/ui";
import { useId } from "react";
import { t } from "../shell/t";

export interface AttributeDefinition {
  key: string;
  label: string;
  fieldType: string;
  required: boolean;
  config: Record<string, unknown>;
}

export interface Option {
  value: string;
  label: string;
}

/** What the inputs hold: text for text-like inputs, a list for multi-select, a flag for boolean. */
export type RawValue = string | readonly string[] | boolean | undefined;
export type RawValues = Readonly<Record<string, RawValue>>;

const READ_ONLY_TYPES: ReadonlySet<string> = new Set(["photo", "signature", "asset_ref", "user_ref"]);
const NUMERIC_TYPES: ReadonlySet<string> = new Set(["number", "decimal", "measurement"]);

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

/** The usable definitions of a version's `attributes` array (malformed entries are skipped). */
export function parseDefinitions(raw: readonly unknown[]): AttributeDefinition[] {
  return raw.flatMap((entry) => {
    const a = record(entry);
    if (typeof a.key !== "string" || !a.key || typeof a.fieldType !== "string") return [];
    return [
      {
        key: a.key,
        label: typeof a.label === "string" && a.label ? a.label : a.key,
        fieldType: a.fieldType,
        required: a.required === true,
        config: record(a.config),
      },
    ];
  });
}

export function optionsOf(definition: AttributeDefinition): Option[] {
  const options = Array.isArray(definition.config.options) ? (definition.config.options as unknown[]) : [];
  return options.flatMap((o) => {
    const option = record(o);
    if (typeof option.value !== "string") return [];
    return [{ value: option.value, label: typeof option.label === "string" ? option.label : option.value }];
  });
}

/** Stored attribute values as input values. */
export function toRawValues(definitions: readonly AttributeDefinition[], stored: Record<string, unknown>): RawValues {
  const out: Record<string, RawValue> = {};
  for (const d of definitions) {
    const value = stored[d.key];
    if (value === undefined || value === null || READ_ONLY_TYPES.has(d.fieldType)) continue;
    if (d.fieldType === "boolean") out[d.key] = value === true;
    else if (d.fieldType === "multi_select") out[d.key] = Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
    else out[d.key] = String(value);
  }
  return out;
}

/**
 * The API's `attributes` for the inputs: empty inputs are left out, numbers are numbers, an unset
 * checkbox is `false`. Read-only fields keep their stored value; keys the version does not define
 * are dropped (the server validates against the version).
 */
export function toAttributes(
  definitions: readonly AttributeDefinition[],
  raw: RawValues,
  stored: Record<string, unknown> = {},
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const d of definitions) {
    if (READ_ONLY_TYPES.has(d.fieldType)) {
      if (stored[d.key] !== undefined) out[d.key] = stored[d.key];
      continue;
    }
    const value = raw[d.key];
    if (d.fieldType === "boolean") {
      out[d.key] = value === true;
    } else if (d.fieldType === "multi_select") {
      if (Array.isArray(value) && value.length > 0) out[d.key] = [...(value as readonly string[])];
    } else if (typeof value === "string" && value.trim() !== "") {
      out[d.key] = NUMERIC_TYPES.has(d.fieldType) ? Number(value) : value;
    }
  }
  return out;
}

export interface AttributeFieldsProps {
  definitions: readonly AttributeDefinition[];
  values: RawValues;
  /** Messages by attribute key. */
  errors: Readonly<Record<string, string>>;
  onChange: (key: string, value: RawValue) => void;
}

function fieldLabel(d: AttributeDefinition): string {
  const unit = d.fieldType === "measurement" && typeof d.config.unit === "string" ? d.config.unit : undefined;
  const label = unit ? t("assets.form.unit_suffix", { label: d.label, unit: t(`item_types.unit.${unit}`) }) : d.label;
  return d.required ? t("assets.form.required_label", { label }) : label;
}

function errorProp(message: string | undefined): { error?: string } {
  return message ? { error: message } : {};
}

function numberLimits(d: AttributeDefinition): { min?: number; max?: number } {
  const limits: { min?: number; max?: number } = {};
  if (typeof d.config.min === "number") limits.min = d.config.min;
  if (typeof d.config.max === "number") limits.max = d.config.max;
  return limits;
}

function MultiSelect({
  definition,
  value,
  error,
  onChange,
}: {
  definition: AttributeDefinition;
  value: readonly string[];
  error: string | undefined;
  onChange: (value: readonly string[]) => void;
}) {
  const id = useId();
  return (
    <fieldset className="aip-form-field assets-form__choices" aria-describedby={error ? `${id}-error` : undefined}>
      <legend className="aip-label">{fieldLabel(definition)}</legend>
      {optionsOf(definition).map((option, index) => (
        <label key={option.value} htmlFor={`${id}-${index}`} className="assets-form__choice">
          <input
            id={`${id}-${index}`}
            type="checkbox"
            checked={value.includes(option.value)}
            onChange={(e) => onChange(e.target.checked ? [...value, option.value] : value.filter((v) => v !== option.value))}
          />
          {option.label}
        </label>
      ))}
      {error ? (
        <p id={`${id}-error`} className="aip-form-field__error" role="alert">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}

function AttributeField({
  definition: d,
  value,
  error,
  onChange,
}: {
  definition: AttributeDefinition;
  value: RawValue;
  error: string | undefined;
  onChange: (value: RawValue) => void;
}) {
  const text = typeof value === "string" ? value : "";
  if (READ_ONLY_TYPES.has(d.fieldType)) {
    return (
      <div className="aip-form-field">
        <p className="aip-label">{fieldLabel(d)}</p>
        <p className="aip-form-field__hint">{t("assets.form.attribute_on_asset_page")}</p>
      </div>
    );
  }
  if (d.fieldType === "multi_select") {
    return <MultiSelect definition={d} value={Array.isArray(value) ? value : []} error={error} onChange={onChange} />;
  }
  return (
    <FormField label={fieldLabel(d)} {...errorProp(error)}>
      {(control) => {
        switch (d.fieldType) {
          case "dropdown":
            return (
              <select {...control} className="assets-form__select" value={text} onChange={(e) => onChange(e.target.value || undefined)}>
                <option value="">{t("assets.form.choose")}</option>
                {optionsOf(d).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            );
          case "boolean":
            return (
              <input {...control} type="checkbox" className="assets-form__checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} />
            );
          case "number":
            return <Input {...control} type="number" step={1} inputMode="numeric" {...numberLimits(d)} value={text} onChange={(e) => onChange(e.target.value)} />;
          case "decimal":
          case "measurement":
            return <Input {...control} type="number" step="any" inputMode="decimal" {...numberLimits(d)} value={text} onChange={(e) => onChange(e.target.value)} />;
          case "date":
            return <Input {...control} type="date" value={text} onChange={(e) => onChange(e.target.value)} />;
          default: {
            const maxLength = typeof d.config.maxLength === "number" ? d.config.maxLength : undefined;
            return <Input {...control} {...(maxLength ? { maxLength } : {})} value={text} onChange={(e) => onChange(e.target.value)} />;
          }
        }
      }}
    </FormField>
  );
}

export function AttributeFields({ definitions, values, errors, onChange }: AttributeFieldsProps) {
  if (definitions.length === 0) return <p className="assets-form__note">{t("assets.form.attributes_none")}</p>;
  return (
    <>
      {definitions.map((d) => (
        <AttributeField key={d.key} definition={d} value={values[d.key]} error={errors[d.key]} onChange={(v) => onChange(d.key, v)} />
      ))}
    </>
  );
}
