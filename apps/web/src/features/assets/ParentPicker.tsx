/**
 * Parent asset picker (ASSETS-03): a `Combobox` that searches `GET /assets?q=` (20 at a time) as the
 * user types and shows each option as its breadcrumb (`Site A > Unit 1 > P-101`). The first option
 * is "top level" (no parent). In the move dialog `exclude` is the moving asset: it and its subtree
 * (`GET /assets?under=<id>`) are left out; the server still refuses a cycle.
 */
import { useAssetsGet, useAssetsList, type AssetListItem } from "@aip/api-client";
import { Combobox, type ComboboxOption } from "@aip/ui";
import { useEffect, useMemo, useState } from "react";
import { crumb } from "./data";

export const PARENT_SEARCH_LIMIT = 20;
const SEARCH_DELAY_MS = 300;
const SUBTREE_LIMIT = 200;

export interface ParentPickerProps {
  /** The input id (from `FormField`), so the visible label names the combobox. */
  id: string;
  /** Accessible name of the input and its option list. */
  label: string;
  /** The chosen parent's id; `""` is the top level. */
  value: string;
  onChange: (parentId: string) => void;
  /** Label of the "no parent" option. */
  topLevelLabel: string;
  /** The asset being moved: it and its subtree are not offered. */
  exclude?: string | undefined;
  placeholder?: string;
}

function useDebounced(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function ParentPicker({ id, label, value, onChange, topLevelLabel, exclude, placeholder }: ParentPickerProps) {
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), SEARCH_DELAY_MS);
  const search = useAssetsList({ limit: PARENT_SEARCH_LIMIT, ...(q ? { q } : {}) });
  const subtree = useAssetsList(
    { under: exclude ?? "", limit: SUBTREE_LIMIT },
    { query: { enabled: Boolean(exclude) } },
  );
  const selected = useAssetsGet(value, { query: { enabled: Boolean(value), retry: false } });

  const excluded = useMemo(() => {
    const ids = new Set<string>(exclude ? [exclude] : []);
    if (subtree.data?.status === 200) for (const a of subtree.data.data.items) ids.add(a.id);
    return ids;
  }, [exclude, subtree.data]);

  const found: readonly AssetListItem[] = useMemo(
    () => (search.data?.status === 200 ? search.data.data.items.filter((a) => !excluded.has(a.id)) : []),
    [search.data, excluded],
  );

  const options = useMemo<ComboboxOption[]>(() => {
    const out: ComboboxOption[] = [{ value: "", label: topLevelLabel }];
    const seen = new Set([""]);
    const add = (option: ComboboxOption) => {
      if (seen.has(option.value)) return;
      seen.add(option.value);
      out.push(option);
    };
    if (value && selected.data?.status === 200) {
      const detail = selected.data.data;
      add({ value: detail.id, label: crumb([...detail.ancestors.map((a) => a.name), detail.name]) });
    }
    for (const asset of found) {
      add({ value: asset.id, label: crumb([...asset.ancestorNames, asset.name]) });
    }
    return out;
  }, [topLevelLabel, value, selected.data, found]);

  return (
    <Combobox
      id={id}
      aria-label={label}
      options={options}
      value={value}
      onValueChange={onChange}
      onInputChange={setText}
      {...(placeholder ? { placeholder } : {})}
    />
  );
}
