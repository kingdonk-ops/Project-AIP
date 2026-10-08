import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { cn } from "../lib/cn";

export interface ComboboxOption {
  value: string;
  label: string;
}

export interface ComboboxProps {
  options: readonly ComboboxOption[];
  value?: string | null;
  onValueChange?: (value: string) => void;
  /** Accessible name when no visible <Label htmlFor={id}> is used. */
  "aria-label"?: string;
  id?: string;
  placeholder?: string;
  className?: string;
}

/**
 * Filterable single-select following the WAI-ARIA 1.2 combobox pattern (input + listbox,
 * aria-activedescendant). Labels arrive through `options`; the component renders no literals.
 */
export function Combobox({
  options,
  value = null,
  onValueChange,
  "aria-label": ariaLabel,
  id,
  placeholder,
  className,
}: ComboboxProps) {
  const autoId = useId();
  const inputId = id ?? `${autoId}-input`;
  const listId = `${autoId}-list`;
  const selected = options.find((o) => o.value === value) ?? null;
  const [query, setQuery] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const filtered = useMemo(() => {
    const q = (query ?? "").trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : [...options];
  }, [options, query]);

  const choose = (option: ComboboxOption) => {
    onValueChange?.(option.value);
    setQuery(null);
    setOpen(false);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) setOpen(true);
      else setActive((i) => Math.min(i + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && open) {
      const option = filtered[active];
      if (option) {
        event.preventDefault();
        choose(option);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
      setQuery(null);
    }
  };

  const activeOption = open ? filtered[active] : undefined;
  const optionId = (index: number) => `${listId}-${index}`;

  return (
    <div className={cn("aip-combobox", className)}>
      <input
        id={inputId}
        className="aip-input"
        role="combobox"
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={activeOption ? optionId(active) : undefined}
        placeholder={placeholder}
        value={query ?? selected?.label ?? ""}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      <ul id={listId} role="listbox" aria-label={ariaLabel} className="aip-combobox__list" hidden={!open}>
        {filtered.map((option, index) => (
          <li
            key={option.value}
            id={optionId(index)}
            role="option"
            aria-selected={option.value === value}
            data-active={index === active || undefined}
            className="aip-combobox__option"
            onMouseDown={(e) => {
              e.preventDefault();
              choose(option);
            }}
          >
            {option.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
