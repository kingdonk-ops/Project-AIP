/**
 * Read-only preview of an item type's attributes (ITEMTYPES-03): one row per attribute, in order,
 * with its label, key, field-type label, a Required chip, and the range, unit or options that
 * matter for its type. It is a list, not a form: it renders no inputs and deliberately does not
 * use the form renderer package. An attribute whose field type is not usable as an attribute
 * renders a warning row instead of failing.
 */
import { StatusChip } from "@aip/ui";
import { t } from "../shell/t";
import { attributeFieldType } from "./fieldTypes";

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function rangeText(config: Record<string, unknown>): string | undefined {
  const min = num(config.min);
  const max = num(config.max);
  if (min !== undefined && max !== undefined) return t("item_types.preview.range", { min, max });
  if (min !== undefined) return t("item_types.preview.range_min", { min });
  if (max !== undefined) return t("item_types.preview.range_max", { max });
  return undefined;
}

function unitText(unit: unknown): string | undefined {
  return typeof unit === "string" && unit ? t(`item_types.unit.${unit}`) : undefined;
}

function optionLabels(config: Record<string, unknown>): string[] {
  const options = Array.isArray(config.options) ? (config.options as unknown[]) : [];
  return options
    .map((o) => (typeof o === "object" && o !== null ? (o as Record<string, unknown>) : {}))
    .map((o) => (typeof o.label === "string" ? o.label : typeof o.value === "string" ? o.value : ""))
    .filter(Boolean);
}

function Details({ fieldType, config }: { fieldType: string; config: Record<string, unknown> }) {
  if (fieldType === "measurement") {
    const range = rangeText(config);
    const unit = unitText(config.unit);
    const text = range && unit ? t("item_types.preview.range_unit", { range, unit }) : (range ?? unit);
    return text ? <span className="item-types-preview__detail">{text}</span> : null;
  }
  if (fieldType === "decimal" || fieldType === "number") {
    const range = rangeText(config);
    return range ? <span className="item-types-preview__detail">{range}</span> : null;
  }
  if (fieldType === "dropdown" || fieldType === "multi_select") {
    const labels = optionLabels(config);
    if (labels.length === 0) return null;
    return (
      <ul className="item-types-preview__options" aria-label={t("item_types.preview.options")}>
        {labels.map((label, i) => (
          <li key={`${i}-${label}`}>{label}</li>
        ))}
      </ul>
    );
  }
  return null;
}

export interface FieldPreviewProps {
  attributes: readonly unknown[];
  /** Accessible name of the list (defaults to the preview title). */
  labelledBy?: string;
}

export function FieldPreview({ attributes, labelledBy }: FieldPreviewProps) {
  if (attributes.length === 0) {
    return <p className="item-types-preview__empty">{t("item_types.preview.empty")}</p>;
  }
  return (
    <ol
      className="item-types-preview"
      {...(labelledBy ? { "aria-labelledby": labelledBy } : { "aria-label": t("item_types.preview.title") })}
    >
      {attributes.map((raw, index) => {
        const attribute = typeof raw === "object" && raw !== null ? (raw as Record<string, unknown>) : {};
        const key = typeof attribute.key === "string" ? attribute.key : "";
        const label = typeof attribute.label === "string" && attribute.label ? attribute.label : key;
        const kind = typeof attribute.fieldType === "string" ? attribute.fieldType : "";
        const entry = attributeFieldType(kind);
        if (!entry) {
          return (
            <li key={index} className="item-types-preview__row item-types-preview__row--warning">
              <StatusChip tone="warning" icon="alert" label={t("item_types.preview.unknown_field_type", { fieldType: kind || "—" })} />
              {key ? <code className="item-types-mono">{key}</code> : null}
            </li>
          );
        }
        const config =
          typeof attribute.config === "object" && attribute.config !== null ? (attribute.config as Record<string, unknown>) : {};
        return (
          <li key={index} className="item-types-preview__row">
            <span className="item-types-preview__label">{label}</span>
            <code className="item-types-mono">{key}</code>
            <span className="item-types-preview__type">{t(entry.termKey)}</span>
            {attribute.required === true ? <StatusChip tone="info" icon="check" label={t("item_types.preview.required")} /> : null}
            <Details fieldType={entry.key} config={config} />
          </li>
        );
      })}
    </ol>
  );
}
