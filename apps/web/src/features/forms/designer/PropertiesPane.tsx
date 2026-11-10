/**
 * The designer's properties pane (FORMS-11). A section: label and key. A field: label, key, type,
 * required, the section it is in, and by type its options, unit and validations. Logic the designer
 * cannot edit yet shows as read-only "Logic set" chips with its JSON behind a `<details>`.
 *
 * A key edit is applied (through `renameKey`, which rewrites logic) only when it is valid and free;
 * otherwise the input shows why and the schema keeps the old key.
 */
import type { FieldType, FormField, FormSchema, FormSection } from "@aip/form-renderer";
import { FormField as Field, Input, NativeSelect } from "@aip/ui";
import { useId, useState } from "react";
import { t } from "../../shell/t";
import {
  changeFieldType,
  FIELD_LOGIC_PROPS,
  findField,
  findSection,
  FORM_FIELD_TYPES,
  keyError,
  logicSet,
  MEASUREMENT_UNITS,
  moveField,
  OPTION_TYPES,
  SECTION_LOGIC_PROPS,
  setValidation,
  updateField,
  VALIDATION_KEYS,
  type Selection,
} from "./model";
import { OptionsEditor } from "./OptionsEditor";

export interface PropertiesPaneProps {
  schema: FormSchema;
  selection: Selection;
  readOnly: boolean;
  /** Apply a new schema; edits with the same `group` within a second are one undo step. */
  edit: (next: FormSchema, group?: string) => void;
  /** Change a label (the designer also moves a following key). */
  setLabel: (selection: NonNullable<Selection>, label: string) => void;
  /** Rename a key (already checked by `keyError`). */
  rename: (from: string, to: string) => void;
  /** Labels for a new field type's defaults. */
  optionLabel: string;
}

export function unitLabel(unit: string): string {
  return ["mm", "in", "bar", "psi", "degC", "degF"].includes(unit) ? t(`forms.unit.${unit}`) : unit;
}

function KeyInput({ value, schema, readOnly, onRename }: { value: string; schema: FormSchema; readOnly: boolean; onRename: (to: string) => void }) {
  const [draft, setDraft] = useState(value);
  // A new key from outside (another item selected, undo, label-follow) replaces the draft.
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    setShown(value);
    setDraft(value);
  }
  const error = keyError(schema, value, draft);
  return (
    <Field
      label={t("forms.designer.prop.key")}
      hint={t("forms.designer.prop.key_hint")}
      {...(error ? { error: t(`forms.designer.prop.key_${error}`) } : {})}
    >
      {(control) => (
        <Input
          {...control}
          className="forms-mono"
          autoComplete="off"
          spellCheck={false}
          value={draft}
          disabled={readOnly}
          onChange={(e) => {
            const next = e.target.value;
            setDraft(next);
            if (next !== value && keyError(schema, value, next) === null) onRename(next);
          }}
        />
      )}
    </Field>
  );
}

function NumberInput({
  label,
  value,
  readOnly,
  onChange,
}: {
  label: string;
  value: number | undefined;
  readOnly: boolean;
  onChange: (value: number | undefined) => void;
}) {
  const [draft, setDraft] = useState(value === undefined ? "" : String(value));
  const [shown, setShown] = useState(value);
  if (value !== shown) {
    // A value from outside (undo, another field): show it unless the draft already means it.
    setShown(value);
    if (!(draft.trim() !== "" && Number(draft) === value)) setDraft(value === undefined ? "" : String(value));
  }
  const invalid = draft.trim() !== "" && !Number.isFinite(Number(draft));
  return (
    <Field label={label} {...(invalid ? { error: t("forms.designer.prop.number_invalid") } : {})}>
      {(control) => (
        <Input
          {...control}
          inputMode="decimal"
          autoComplete="off"
          value={draft}
          disabled={readOnly}
          onChange={(e) => {
            const text = e.target.value;
            setDraft(text);
            if (text.trim() === "") onChange(undefined);
            else if (Number.isFinite(Number(text))) onChange(Number(text));
          }}
        />
      )}
    </Field>
  );
}

function LogicChips({ item, props }: { item: object; props: readonly string[] }) {
  const set = logicSet(item, props);
  if (set.length === 0) return null;
  return (
    <div className="dsg-logic">
      <h3 className="dsg-props__subheading">{t("forms.designer.prop.logic")}</h3>
      <p className="dsg-props__hint">{t("forms.designer.prop.logic_hint")}</p>
      {set.map((name) => (
        <details key={name} className="dsg-logic__item">
          <summary>
            <span className="dsg-chip dsg-chip--logic">{t("forms.designer.canvas.logic")}</span>{" "}
            <code className="forms-mono">{name}</code>
          </summary>
          <pre className="forms-mono dsg-logic__json">{JSON.stringify((item as Record<string, unknown>)[name], null, 2)}</pre>
        </details>
      ))}
    </div>
  );
}

function SectionProperties({ section, ...props }: PropertiesPaneProps & { section: FormSection }) {
  const { schema, readOnly, setLabel, rename } = props;
  return (
    <>
      <Field label={t("forms.designer.prop.label")}>
        {(control) => (
          <Input
            {...control}
            value={section.label}
            disabled={readOnly}
            onChange={(e) => setLabel({ kind: "section", key: section.key }, e.target.value)}
          />
        )}
      </Field>
      <KeyInput value={section.key} schema={schema} readOnly={readOnly} onRename={(to) => rename(section.key, to)} />
      <LogicChips item={section} props={SECTION_LOGIC_PROPS} />
    </>
  );
}

function FieldProperties({ field, sectionKey, ...props }: PropertiesPaneProps & { field: FormField; sectionKey: string }) {
  const { schema, readOnly, edit, setLabel, rename, optionLabel } = props;
  const requiredId = useId();
  const group = (prop: string) => `${field.key}:${prop}`;
  return (
    <>
      <Field label={t("forms.designer.prop.label")}>
        {(control) => (
          <Input {...control} value={field.label} disabled={readOnly} onChange={(e) => setLabel({ kind: "field", key: field.key }, e.target.value)} />
        )}
      </Field>
      <KeyInput value={field.key} schema={schema} readOnly={readOnly} onRename={(to) => rename(field.key, to)} />
      <Field label={t("forms.designer.prop.type")}>
        {(control) => (
          <NativeSelect
            {...control}
            value={field.type}
            disabled={readOnly}
            onChange={(e) => edit(changeFieldType(schema, field.key, e.target.value as FieldType, { option: optionLabel }))}
          >
            {FORM_FIELD_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`item_types.field_type.${type}`)}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <label className="dsg-check" htmlFor={requiredId}>
        <input
          id={requiredId}
          type="checkbox"
          checked={field.required === true}
          disabled={readOnly}
          onChange={(e) => edit(updateField(schema, field.key, { required: e.target.checked ? true : undefined }))}
        />
        {t("forms.designer.prop.required")}
      </label>
      <Field label={t("forms.designer.prop.move_to")}>
        {(control) => (
          <NativeSelect
            {...control}
            value={sectionKey}
            disabled={readOnly || schema.sections.length < 2}
            onChange={(e) => {
              const target = findSection(schema, e.target.value);
              if (target) edit(moveField(schema, field.key, target.key, target.fields.length));
            }}
          >
            {schema.sections.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label || s.key}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      {OPTION_TYPES.has(field.type) ? (
        <OptionsEditor
          options={field.options ?? []}
          readOnly={readOnly}
          onChange={(options, g) => edit(updateField(schema, field.key, { options }), g ? group(g) : undefined)}
        />
      ) : null}
      {field.type === "measurement" ? (
        <Field label={t("forms.designer.prop.unit")}>
          {(control) => (
            <NativeSelect
              {...control}
              value={field.unit ?? ""}
              disabled={readOnly}
              onChange={(e) => edit(updateField(schema, field.key, { unit: e.target.value }))}
            >
              {field.unit && !MEASUREMENT_UNITS.includes(field.unit) ? <option value={field.unit}>{field.unit}</option> : null}
              {MEASUREMENT_UNITS.map((unit) => (
                <option key={unit} value={unit}>
                  {unitLabel(unit)}
                </option>
              ))}
            </NativeSelect>
          )}
        </Field>
      ) : null}
      {(VALIDATION_KEYS[field.type] ?? []).map((name) => (
        <NumberInput
          key={`${field.key}-${name}`}
          label={t(`forms.designer.prop.${name}`)}
          value={field.validations?.[name]}
          readOnly={readOnly}
          onChange={(value) => edit(setValidation(schema, field.key, name, value), group(name))}
        />
      ))}
      <LogicChips item={field} props={FIELD_LOGIC_PROPS} />
    </>
  );
}

export function PropertiesPane(props: PropertiesPaneProps) {
  const { schema, selection } = props;
  if (selection?.kind === "section") {
    const section = findSection(schema, selection.key);
    if (section) {
      return (
        <div className="dsg-props" data-testid="designer-properties">
          <h3 className="dsg-props__heading">
            {t("forms.designer.prop.section")} <code className="forms-mono">{section.key}</code>
          </h3>
          <SectionProperties {...props} section={section} />
        </div>
      );
    }
  }
  if (selection?.kind === "field") {
    const location = findField(schema, selection.key);
    if (location) {
      return (
        <div className="dsg-props" data-testid="designer-properties">
          <h3 className="dsg-props__heading">
            {t("forms.designer.prop.field")} <code className="forms-mono">{location.field.key}</code>
          </h3>
          <FieldProperties {...props} field={location.field} sectionKey={location.section.key} />
        </div>
      );
    }
  }
  return (
    <p className="dsg-props__empty" data-testid="designer-properties">
      {t("forms.designer.properties.empty")}
    </p>
  );
}
