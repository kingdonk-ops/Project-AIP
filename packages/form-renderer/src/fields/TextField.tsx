import { Input } from "@aip/ui";
import { ControlFrame, NotAnswered, ReadOnlyFrame, type FieldProps } from "./FieldFrame";

/** `text` → `Input`, `maxLength` from the field's validations. */
export function TextField({ field, value, onChange, t, readOnly, frame }: FieldProps) {
  const text = typeof value === "string" ? value : value === undefined || value === null ? "" : JSON.stringify(value);
  if (readOnly) {
    return <ReadOnlyFrame frame={frame}>{text ? <span>{text}</span> : <NotAnswered t={t} />}</ReadOnlyFrame>;
  }
  const maxLength = field.validations?.maxLength;
  return (
    <ControlFrame frame={frame}>
      {(control) => (
        <Input
          {...control}
          value={text}
          {...(maxLength !== undefined ? { maxLength } : {})}
          onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
        />
      )}
    </ControlFrame>
  );
}
