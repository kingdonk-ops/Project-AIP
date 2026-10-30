import { Checkbox, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@aip/ui";
import { useId } from "react";
import { labelOf } from "../labels";
import type { FieldOption } from "../logic/types";
import { ControlFrame, GroupFrame, NotAnswered, ReadOnlyFrame, type FieldProps } from "./FieldFrame";

function optionText(props: FieldProps, value: string): string {
  const option = (props.field.options ?? []).find((o: FieldOption) => o.value === value);
  return option ? labelOf(props.t, option) : value;
}

/** `dropdown` → `@aip/ui` Select over the field's options. */
export function DropdownField(props: FieldProps) {
  const { field, value, onChange, t, readOnly, frame } = props;
  const selected = typeof value === "string" ? value : undefined;
  if (readOnly) {
    return (
      <ReadOnlyFrame frame={frame}>{selected ? <span>{optionText(props, selected)}</span> : <NotAnswered t={t} />}</ReadOnlyFrame>
    );
  }
  const options = field.options ?? [];
  // An answer that is not an option (e.g. a stale value) leaves the trigger empty; the evaluator
  // reports NOT_AN_OPTION.
  const known = selected !== undefined && options.some((o) => o.value === selected) ? selected : "";
  return (
    <ControlFrame frame={frame}>
      {(control) => (
        <Select value={known} onValueChange={(next) => onChange(next)}>
          <SelectTrigger {...control}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {labelOf(t, option)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
    </ControlFrame>
  );
}

/** `multi_select` → a group of `Checkbox`es in a nested `<fieldset>`; the value keeps option order. */
export function MultiSelectField(props: FieldProps) {
  const { field, value, onChange, t, readOnly, frame } = props;
  const id = useId();
  const chosen = Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  if (readOnly) {
    return (
      <ReadOnlyFrame frame={frame}>
        {chosen.length ? (
          <ul className="aip-form-renderer__list">
            {chosen.map((v) => (
              <li key={v}>{optionText(props, v)}</li>
            ))}
          </ul>
        ) : (
          <NotAnswered t={t} />
        )}
      </ReadOnlyFrame>
    );
  }
  const options = field.options ?? [];
  const toggle = (optionValue: string, on: boolean) => {
    const next = options.map((o) => o.value).filter((v) => (v === optionValue ? on : chosen.includes(v)));
    // Keep answers that are not options so the evaluator can still report them.
    const unknown = chosen.filter((v) => !options.some((o) => o.value === v));
    const all = [...next, ...unknown];
    onChange(all.length ? all : undefined);
  };
  return (
    <GroupFrame frame={frame}>
      <div className="aip-form-renderer__choices">
        {options.map((option, index) => {
          const optionId = `${id}-${index}`;
          return (
            <span key={option.value} className="aip-form-renderer__choice">
              <Checkbox
                id={optionId}
                checked={chosen.includes(option.value)}
                onCheckedChange={(state) => toggle(option.value, state === true)}
              />
              <Label htmlFor={optionId}>{labelOf(t, option)}</Label>
            </span>
          );
        })}
      </div>
    </GroupFrame>
  );
}
