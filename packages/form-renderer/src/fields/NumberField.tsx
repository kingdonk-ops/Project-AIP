import { Input } from "@aip/ui";
import { useState } from "react";
import type { Json } from "../logic/types";
import { ControlFrame, NotAnswered, ReadOnlyFrame, type FieldProps } from "./FieldFrame";

/**
 * Typed text → stored value: `""` is empty (`null`), a finite `Number(text)` is that number, and
 * anything else is kept as the raw string so the evaluator reports `WRONG_TYPE` (never dropped).
 */
export function parseNumeric(text: string): number | string | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : text;
}

export function numericText(value: Json | undefined): string {
  if (value === undefined || value === null) return "";
  return typeof value === "number" || typeof value === "string" ? String(value) : JSON.stringify(value);
}

function same(a: Json | undefined, b: Json | undefined): boolean {
  return (a ?? null) === (b ?? null);
}

/**
 * The text the user typed, kept locally so "0." or "-" survive while typing. It resyncs from the
 * stored value only when the host changes that value to something the text does not mean.
 */
export function useNumericText(value: Json | undefined): [string, (text: string) => void] {
  const [text, setText] = useState(() => numericText(value));
  const [seen, setSeen] = useState<Json | undefined>(value);
  if (!same(seen, value)) {
    setSeen(value);
    if (!same(parseNumeric(text), value)) setText(numericText(value));
  }
  return [text, setText];
}

/** `number` → `Input inputMode="numeric"`; `decimal` → `inputMode="decimal"`. */
export function NumberField({ field, value, onChange, t, readOnly, frame }: FieldProps) {
  const [text, setText] = useNumericText(value);
  if (readOnly) {
    const shown = numericText(value);
    return <ReadOnlyFrame frame={frame}>{shown ? <span>{shown}</span> : <NotAnswered t={t} />}</ReadOnlyFrame>;
  }
  return (
    <ControlFrame frame={frame}>
      {(control) => (
        <Input
          {...control}
          inputMode={field.type === "number" ? "numeric" : "decimal"}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            const parsed = parseNumeric(e.target.value);
            onChange(parsed === null ? undefined : parsed);
          }}
        />
      )}
    </ControlFrame>
  );
}
