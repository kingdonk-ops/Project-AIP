// Test fixture shared by the register tests (not exported from the package).
import { useState } from "react";
import { RegisterTable, type RegisterTableProps } from "./RegisterTable";
import type { RegisterColumn, RegisterFilter, RegisterPage, RegisterQuery, RegisterQueryResult, Translate } from "./types";

export interface Row {
  id: string;
  code: string;
  name: string;
  region: string;
}

const LABELS: Record<string, string> = {
  "register.search": "Search",
  "register.clearAll": "Clear all",
  "register.columns": "Columns",
  "register.restoreDefaults": "Restore defaults",
  "register.export": "Export CSV",
  "register.previous": "Previous",
  "register.next": "Next",
  "register.pageSize": "Rows per page",
  "register.pagination": "Pages",
  "register.selectPage": "Select all on this page",
  "register.selectRow": "Select {row}",
  "register.selected": "{count} selected",
  "register.bulkActions": "Bulk actions",
  "register.empty": "Nothing matches these filters.",
  "register.loading": "Loading…",
  "register.error": "The list could not be loaded.",
  "register.retry": "Try again",
  "register.any": "Any",
  "register.dateFrom": "From",
  "register.dateTo": "To",
  "fx.caption": "Projects",
  "fx.code": "Code",
  "fx.name": "Name",
  "fx.region": "Region",
  "fx.status": "Status",
  "fx.status.active": "Active",
  "fx.status.draft": "Draft",
  "fx.archive": "Archive",
  "fx.export": "Export",
};

export const t: Translate = (key, params) =>
  (LABELS[key] ?? `⟦${key}⟧`).replace(/\{(\w+)\}/g, (m, name: string) => (params && name in params ? String(params[name]) : m));

export const columns: RegisterColumn<Row>[] = [
  { id: "code", headerKey: "fx.code", cell: (r) => r.code, sortable: true, mono: true },
  { id: "name", headerKey: "fx.name", cell: (r) => r.name, sortable: ["asc"] },
  { id: "region", headerKey: "fx.region", cell: (r) => r.region },
];

export const filters: RegisterFilter[] = [
  {
    id: "status",
    kind: "multi",
    labelKey: "fx.status",
    quick: true,
    options: [
      { value: "active", labelKey: "fx.status.active" },
      { value: "draft", labelKey: "fx.status.draft" },
    ],
  },
];

export function rows(n: number, from = 0): Row[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `r${from + i}`,
    code: `P${String(from + i).padStart(3, "0")}`,
    name: `Project ${from + i}`,
    region: "WA",
  }));
}

export type Pages = (query: RegisterQuery) => RegisterQueryResult<Row>;

export function result(page: RegisterPage<Row> | undefined, extra: Partial<RegisterQueryResult<Row>> = {}): RegisterQueryResult<Row> {
  return { data: page, isPending: false, isError: false, refetch: () => undefined, ...extra };
}

export function Harness(
  props: Partial<RegisterTableProps<Row>> & { pages: Pages; initial?: RegisterQuery; seen?: RegisterQuery[] },
) {
  const { pages, initial, seen, ...rest } = props;
  const [query, setQuery] = useState<RegisterQuery>(initial ?? { filters: {}, limit: 50 });
  return (
    <RegisterTable<Row>
      id="fixture"
      captionKey="fx.caption"
      columns={columns}
      filters={filters}
      query={query}
      onQueryChange={(next) => {
        seen?.push(next);
        setQuery(next);
      }}
      useQuery={pages}
      rowId={(r) => r.id}
      translate={t}
      prefs={{ get: () => null, set: () => undefined }}
      {...rest}
    />
  );
}
