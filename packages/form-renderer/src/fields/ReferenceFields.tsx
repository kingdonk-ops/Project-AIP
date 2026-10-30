import { Combobox, type ComboboxOption } from "@aip/ui";
import { useEffect, useRef, useState } from "react";
import type { ReferenceAdapter, ReferenceItem, ReferenceKind } from "../adapters";
import { ControlFrame, NotAnswered, ReadOnlyFrame, type ControlProps, type FieldProps } from "./FieldFrame";

/** Search is debounced so typing does not call the host's adapter on every keystroke. */
export const REFERENCE_SEARCH_DEBOUNCE_MS = 250;

/** `references.label(kind, id)` for the stored id; `null` until it resolves (or when unknown). */
function useReferenceLabel(references: ReferenceAdapter | undefined, kind: ReferenceKind, id: string | null): string | null {
  const [resolved, setResolved] = useState<{ id: string; label: string | null } | null>(null);
  useEffect(() => {
    if (!references || !id) return;
    let live = true;
    references.label(kind, id).then(
      (label) => live && setResolved({ id, label }),
      () => live && setResolved({ id, label: null }),
    );
    return () => {
      live = false;
    };
  }, [references, kind, id]);
  return resolved && resolved.id === id ? resolved.label : null;
}

/** Copies the FormField wiring onto the Combobox input, which takes only `id` and `aria-label`. */
function useInputWiring(control: ControlProps) {
  const ref = useRef<HTMLDivElement>(null);
  const describedBy = control["aria-describedby"];
  const invalid = control["aria-invalid"];
  const required = control["aria-required"];
  useEffect(() => {
    const input = ref.current?.querySelector("input");
    if (!input) return;
    const set = (name: string, v: string | undefined) => (v ? input.setAttribute(name, v) : input.removeAttribute(name));
    set("aria-describedby", describedBy);
    set("aria-invalid", invalid ? "true" : undefined);
    set("aria-required", required ? "true" : undefined);
  }, [describedBy, invalid, required]);
  return ref;
}

function ReferenceCombobox({
  control,
  references,
  kind,
  value,
  selectedLabel,
  label,
  placeholder,
  onChange,
}: {
  control: ControlProps;
  references: ReferenceAdapter;
  kind: ReferenceKind;
  value: string | null;
  selectedLabel: string | null;
  label: string;
  placeholder: string;
  onChange: (id: string) => void;
}) {
  const ref = useInputWiring(control);
  const [query, setQuery] = useState<string | null>(null);
  const [results, setResults] = useState<ReferenceItem[]>([]);

  useEffect(() => {
    if (query === null) return;
    let live = true;
    const timer = setTimeout(() => {
      references.search(kind, query).then(
        (items) => live && setResults(items),
        () => live && setResults([]),
      );
    }, REFERENCE_SEARCH_DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [references, kind, query]);

  const options: ComboboxOption[] = results.map((r) => ({ value: r.id, label: r.label }));
  if (value && !options.some((o) => o.value === value)) options.unshift({ value, label: selectedLabel ?? value });

  return (
    // The Combobox keeps its query to itself; its input's change event bubbles here.
    <div ref={ref} onChange={(e) => setQuery((e.target as HTMLInputElement).value)}>
      <Combobox
        id={control.id}
        aria-label={label}
        placeholder={placeholder}
        options={options}
        value={value}
        onValueChange={onChange}
      />
    </div>
  );
}

/**
 * `asset_ref` / `user_ref` → `@aip/ui` Combobox over `references.search` (debounced 250 ms), showing
 * `references.label` for the stored id. The value is the referenced id.
 */
export function ReferenceField({ field, value, onChange, t, adapters, readOnly, frame }: FieldProps) {
  const kind: ReferenceKind = field.type === "user_ref" ? "user" : "asset";
  const references = adapters.references;
  const id = typeof value === "string" && value ? value : null;
  const selectedLabel = useReferenceLabel(references, kind, id);

  if (readOnly) {
    return <ReadOnlyFrame frame={frame}>{id ? <span>{selectedLabel ?? id}</span> : <NotAnswered t={t} />}</ReadOnlyFrame>;
  }
  if (!references) {
    return (
      <ReadOnlyFrame frame={frame}>
        <span className="aip-form-renderer__empty">{t("forms.renderer.adapter_missing")}</span>
      </ReadOnlyFrame>
    );
  }
  return (
    <ControlFrame frame={frame}>
      {(control) => (
        <ReferenceCombobox
          control={control}
          references={references}
          kind={kind}
          value={id}
          selectedLabel={selectedLabel}
          label={frame.label}
          placeholder={t("forms.renderer.search_placeholder")}
          onChange={(next) => onChange(next)}
        />
      )}
    </ControlFrame>
  );
}
