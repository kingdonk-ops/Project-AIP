import { Input } from "@aip/ui";
import type { Json } from "../logic/types";
import { ControlFrame, NotAnswered, ReadOnlyFrame, type FieldProps } from "./FieldFrame";
import { numericText, parseNumeric, useNumericText } from "./NumberField";

function storedNumber(value: Json | undefined): Json | undefined {
  if (value && typeof value === "object" && !Array.isArray(value)) return value["value"];
  return undefined;
}

/**
 * `measurement` → `Input inputMode="decimal"` with the unit symbol (`forms.unit.<unit>`) as a visible
 * suffix. The value is `{value, unit: field.unit}` in the field's SI storage unit (no display-unit
 * conversion in R1).
 */
export function MeasurementField({ field, value, onChange, t, readOnly, frame }: FieldProps) {
  const unit = field.unit ?? "";
  const unitText = t(`forms.unit.${unit}`);
  const stored = storedNumber(value);
  const [text, setText] = useNumericText(stored);
  if (readOnly) {
    const shown = numericText(stored);
    return (
      <ReadOnlyFrame frame={frame}>
        {shown ? (
          <span>
            {shown} {unitText}
          </span>
        ) : (
          <NotAnswered t={t} />
        )}
      </ReadOnlyFrame>
    );
  }
  return (
    <ControlFrame frame={frame}>
      {(control) => (
        <span className="aip-form-renderer__measure">
          <Input
            {...control}
            inputMode="decimal"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              const parsed = parseNumeric(e.target.value);
              onChange(parsed === null ? undefined : { value: parsed, unit });
            }}
          />
          <span className="aip-form-renderer__unit">{unitText}</span>
        </span>
      )}
    </ControlFrame>
  );
}
