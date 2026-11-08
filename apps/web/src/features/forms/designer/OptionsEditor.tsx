/**
 * A dropdown's or multi-select's options (FORMS-11): add, remove and reorder, a label and a value
 * each. A value follows its label (through `keyFromLabel`) while it still equals the value the old
 * label gave; once edited by hand it stays. Values must be unique (the lint's DUPLICATE_OPTION).
 */
import type { FieldOption } from "@aip/form-renderer";
import { Button, Input } from "@aip/ui";
import { useId } from "react";
import { t } from "../../shell/t";
import { isValidKey, keyFromLabel } from "./keys";

export interface OptionsEditorProps {
  options: readonly FieldOption[];
  readOnly: boolean;
  /** `group` names the input, so typing in it is one undo step. */
  onChange: (options: FieldOption[], group?: string) => void;
}

function otherValues(options: readonly FieldOption[], index: number): string[] {
  return options.filter((_, i) => i !== index).map((o) => o.value);
}

export function OptionsEditor({ options, readOnly, onChange }: OptionsEditorProps) {
  const id = useId();
  const values = options.map((o) => o.value);
  const duplicate = values.some((v, i) => values.indexOf(v) !== i);

  function setLabel(index: number, label: string) {
    const option = options[index]!;
    const others = otherValues(options, index);
    const follows = option.value === keyFromLabel(option.label, others);
    const next = options.map((o, i) =>
      i === index ? { ...o, label, ...(follows && label.trim() ? { value: keyFromLabel(label, others) } : {}) } : o,
    );
    onChange(next, `option-label-${index}`);
  }

  function setValue(index: number, value: string) {
    onChange(
      options.map((o, i) => (i === index ? { ...o, value } : o)),
      `option-value-${index}`,
    );
  }

  function move(index: number, delta: number) {
    const to = index + delta;
    if (to < 0 || to >= options.length) return;
    const next = [...options];
    const [item] = next.splice(index, 1);
    next.splice(to, 0, item!);
    onChange(next);
  }

  function add() {
    const label = t("forms.designer.options.new", { n: options.length + 1 });
    onChange([...options, { value: keyFromLabel(label, values), label }]);
  }

  return (
    <fieldset className="dsg-options" aria-describedby={duplicate ? `${id}-error` : undefined}>
      <legend className="dsg-options__legend">{t("forms.designer.options.title")}</legend>
      <ol className="dsg-options__list">
        {options.map((option, index) => {
          const n = index + 1;
          const badValue = !isValidKey(option.value) || values.indexOf(option.value) !== index;
          return (
            // Options are edited in place; their index is their identity while editing.
            <li key={index} className="dsg-options__row" data-option={index}>
              <Input
                aria-label={t("forms.designer.options.label", { n })}
                value={option.label}
                disabled={readOnly}
                onChange={(e) => setLabel(index, e.target.value)}
              />
              <Input
                aria-label={t("forms.designer.options.value", { n })}
                className="forms-mono"
                value={option.value}
                disabled={readOnly}
                {...(badValue ? { "aria-invalid": true as const } : {})}
                onChange={(e) => setValue(index, e.target.value)}
              />
              {readOnly ? null : (
                <span className="dsg-options__actions">
                  <Button type="button" variant="ghost" size="icon" aria-label={t("forms.designer.options.up", { n })} disabled={index === 0} onClick={() => move(index, -1)}>
                    {"↑"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t("forms.designer.options.down", { n })}
                    disabled={index === options.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    {"↓"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t("forms.designer.options.remove", { n })}
                    disabled={options.length <= 1}
                    onClick={() => onChange(options.filter((_, i) => i !== index))}
                  >
                    {"×"}
                  </Button>
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {duplicate ? (
        <p id={`${id}-error`} className="aip-form-field__error">
          {t("forms.designer.options.value_taken")}
        </p>
      ) : null}
      {readOnly ? null : (
        <Button type="button" variant="secondary" onClick={add}>
          {t("forms.designer.options.add")}
        </Button>
      )}
    </fieldset>
  );
}
