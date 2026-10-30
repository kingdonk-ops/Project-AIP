import { Input } from "@aip/ui";
import { ControlFrame, NotAnswered, ReadOnlyFrame, type FieldProps } from "./FieldFrame";

/**
 * `date` → native `<input type="date">`. The value is the `YYYY-MM-DD` string as given: no Date
 * object, so no time-zone shift (ADR 0025). Read-only shows the stored string unchanged.
 */
export function DateField({ value, onChange, t, readOnly, frame }: FieldProps) {
  const text = typeof value === "string" ? value : "";
  if (readOnly) {
    return <ReadOnlyFrame frame={frame}>{text ? <span>{text}</span> : <NotAnswered t={t} />}</ReadOnlyFrame>;
  }
  return (
    <ControlFrame frame={frame}>
      {(control) => (
        <Input {...control} type="date" value={text} onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)} />
      )}
    </ControlFrame>
  );
}
