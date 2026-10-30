/**
 * `RegisterTable` (DESIGN-03): the one register every P1 list uses. A dense table (sticky header,
 * `--row-h` rows) on TanStack Table (headless) with a filter bar, URL-held state, server-side
 * cursor paging and sorting, a column chooser, multi-select bulk actions and CSV export through a
 * server endpoint. It never fetches: `useQuery(query)` is the caller's adapter over a generated
 * TanStack Query hook. It contains no literal text: every label is a term key passed to
 * `translate`.
 *
 * @example
 * ```tsx
 * const spec = { filters, sortable: { code: ["asc"] }, columns: columns.map((c) => c.id) };
 * // route: validateSearch: (s) => decodeRegisterQuery(s, spec)
 * <RegisterTable
 *   id="projects"
 *   captionKey="projects.register.caption"
 *   columns={columns}
 *   filters={filters}
 *   query={query}
 *   onQueryChange={(q) => navigate({ search: encodeRegisterQuery(q), replace: true })}
 *   useQuery={(q) => toResult(useProjectsList(toParams(q)))}
 *   rowId={(p) => p.id}
 *   onOpenRow={(p) => navigate({ to: "/projects/$id", params: { id: p.id } })}
 *   bulkActions={[{ id: "archive", labelKey: "projects.archive", permission: "project.archive", run }]}
 *   permissions={session.permissions}
 *   exportHref={(q) => `/api/v1/projects/export.csv?${new URLSearchParams(encodeRegisterQuery(q))}`}
 *   translate={t}
 * />
 * ```
 */
import {
  columnVisibilityFeature,
  rowSelectionFeature,
  tableFeatures,
  useTable,
  type ColumnDef,
  type ColumnVisibilityState,
  type RowData,
  type RowSelectionState,
} from "@tanstack/react-table";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "../components/button";
import { Checkbox } from "../components/checkbox";
import { Spinner } from "../components/spinner";
import { cn } from "../lib/cn";
import { ColumnChooser, defaultColumns, localStorageColumnPrefs, type ColumnPrefsStore } from "./ColumnChooser";
import { FilterBar } from "./FilterBar";
import { omit } from "./query-utils";
import {
  PAGE_SIZES,
  type BulkAction,
  type RegisterColumn,
  type RegisterFilter,
  type RegisterQuery,
  type RegisterQueryResult,
  type SortDir,
  type Translate,
} from "./types";

const SKELETON_ROWS = 5;

// Sorting and paging are the server's (cursor pages), so the table only selects rows and hides columns.
const features = tableFeatures({ rowSelectionFeature, columnVisibilityFeature });

export interface RegisterTableProps<T> {
  /** Stable register id (column preferences are kept per id). */
  id: string;
  captionKey: string;
  columns: readonly RegisterColumn<T>[];
  filters?: readonly RegisterFilter[];
  query: RegisterQuery;
  onQueryChange: (next: RegisterQuery) => void;
  useQuery: (query: RegisterQuery) => RegisterQueryResult<T>;
  rowId: (row: T) => string;
  /** Enter on a focused row (and a click on its first cell's link, if the caller renders one). */
  onOpenRow?: (row: T) => void;
  bulkActions?: readonly BulkAction<T>[];
  permissions?: readonly string[];
  /** A server endpoint that exports the same filtered rows the user may see. Hidden when omitted. */
  exportHref?: (query: RegisterQuery) => string;
  translate: Translate;
  prefs?: ColumnPrefsStore;
  pageSizes?: readonly number[];
  /** Show the free-text search (default true). */
  search?: boolean;
  /** Shown instead of `register.empty` when the page has no rows (e.g. a first-run call to action). */
  empty?: ReactNode;
}

function directions(column: RegisterColumn<unknown>): readonly SortDir[] {
  if (column.sortable === true) return ["asc", "desc"];
  return column.sortable || [];
}

function nextSort(column: RegisterColumn<unknown>, current: RegisterQuery["sort"]): RegisterQuery["sort"] {
  const dirs = directions(column);
  if (current?.id === column.id && dirs.length > 1) {
    return { id: column.id, dir: current.dir === "asc" ? "desc" : "asc" };
  }
  return { id: column.id, dir: dirs[0] ?? "asc" };
}

/** Everything in the query except the page position: when it changes, paging starts again. */
function pageKey(query: RegisterQuery): string {
  return JSON.stringify(omit(query, "cursor", "columns"));
}

export function RegisterTable<T extends RowData>({
  id,
  captionKey,
  columns,
  filters = [],
  query,
  onQueryChange,
  useQuery,
  rowId,
  onOpenRow,
  bulkActions = [],
  permissions = [],
  exportHref,
  translate: tr,
  prefs = localStorageColumnPrefs,
  pageSizes = PAGE_SIZES,
  search = true,
  empty,
}: RegisterTableProps<T>) {
  const result = useQuery(query);
  const pageSizeId = useId();
  const items = useMemo(() => (result.data ? [...result.data.items] : []), [result.data]);

  // Paging: the API pages forward only, so earlier cursors are remembered here for Previous.
  const [previous, setPrevious] = useState<(string | undefined)[]>([]);
  const key = pageKey(query);
  const lastKey = useRef(key);
  useEffect(() => {
    if (lastKey.current !== key) {
      lastKey.current = key;
      setPrevious([]);
    }
  }, [key]);

  // Columns: the URL wins, then the stored preference, then the defaults.
  const [stored, setStored] = useState<string[] | null>(() => prefs.get(id));
  const visible = query.columns ?? stored ?? defaultColumns(columns);
  const visibility: ColumnVisibilityState = Object.fromEntries(columns.map((c) => [c.id, visible.includes(c.id)]));

  const actions = bulkActions.filter((a) => !a.permission || permissions.includes(a.permission));
  const selectable = actions.length > 0;
  const [selection, setSelection] = useState<RowSelectionState>({});
  // Keyboard: one row is in the tab order (see onRowKey).
  const [active, setActive] = useState(0);
  // Another page or query starts with nothing selected and its first row active (reset while rendering).
  const shown = `${key}\n${query.cursor ?? ""}`;
  const [shownPage, setShownPage] = useState(shown);
  if (shownPage !== shown) {
    setShownPage(shown);
    setSelection({});
    setActive(0);
  }

  const defs = useMemo<ColumnDef<typeof features, T>[]>(
    () => columns.map((c) => ({ id: c.id, header: c.headerKey, cell: (ctx) => c.cell(ctx.row.original) })),
    [columns],
  );
  const table = useTable({
    features,
    data: items,
    columns: defs,
    getRowId: (row) => rowId(row),
    enableRowSelection: selectable,
    state: { columnVisibility: visibility, rowSelection: selection },
    onRowSelectionChange: setSelection,
  });
  const rows = table.getRowModel().rows;
  const shownColumns = columns.filter((c) => visibility[c.id]);
  const selectedRows = rows.filter((r) => r.getIsSelected()).map((r) => r.original);

  // Keyboard: arrows move between rows, Enter opens.
  const body = useRef<HTMLTableSectionElement>(null);
  function onRowKey(event: KeyboardEvent<HTMLTableRowElement>, index: number, row: T) {
    if (event.target !== event.currentTarget) return; // keys inside a cell control stay there
    let next: number;
    if (event.key === "ArrowDown") next = Math.min(index + 1, rows.length - 1);
    else if (event.key === "ArrowUp") next = Math.max(index - 1, 0);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = rows.length - 1;
    else if (event.key === "Enter" && onOpenRow) {
      event.preventDefault();
      onOpenRow(row);
      return;
    } else return;
    event.preventDefault();
    setActive(next);
    body.current?.querySelectorAll<HTMLTableRowElement>("tr[data-row]")[next]?.focus();
  }

  const change = (next: RegisterQuery) => onQueryChange(next);
  const setColumns = (next: readonly string[] | null) => {
    prefs.set(id, next);
    setStored(next ? [...next] : null);
    const rest = omit(query, "columns");
    change(next ? { ...rest, columns: next } : rest);
  };
  const goNext = () => {
    const cursor = result.data?.nextCursor;
    if (!cursor) return;
    setPrevious((stack) => [...stack, query.cursor]);
    change({ ...query, cursor });
  };
  // After a reload the earlier cursors are gone: Previous then returns to the first page.
  const goPrevious = () => {
    const stack = [...previous];
    const cursor = stack.pop();
    setPrevious(stack);
    const rest = omit(query, "cursor");
    change(cursor ? { ...rest, cursor } : rest);
  };

  const colSpan = shownColumns.length + (selectable ? 1 : 0);
  const pageSelected = rows.length > 0 && rows.every((r) => r.getIsSelected());
  const someSelected = rows.some((r) => r.getIsSelected());

  return (
    <div className="aip-register" data-register={id}>
      <div className="aip-register__toolbar">
        <FilterBar filters={filters} query={query} onChange={change} translate={tr} search={search} />
        <div className="aip-register__tools">
          <ColumnChooser columns={columns} visible={visible} onChange={setColumns} translate={tr} />
          {exportHref && (
            <a className="aip-button aip-button--secondary" href={exportHref(query)} download>
              {tr("register.export")}
            </a>
          )}
        </div>
      </div>

      {selectable && selectedRows.length > 0 && (
        <div className="aip-register__bulk" role="region" aria-label={tr("register.bulkActions")}>
          <span aria-live="polite">{tr("register.selected", { count: selectedRows.length })}</span>
          {actions.map((action) => (
            <Button key={action.id} variant="secondary" onClick={() => action.run(selectedRows)}>
              {tr(action.labelKey)}
            </Button>
          ))}
        </div>
      )}

      {/* DESIGN-08: its own scroll region, reachable by keyboard and named after the table. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must take focus so keyboard users can scroll it (axe scrollable-region-focusable) */}
      <div className="aip-table__wrap aip-register__scroll" role="region" aria-label={tr(captionKey)} tabIndex={0}>
        <table
          className="aip-table aip-register__table"
          aria-busy={result.isPending}
          {...(result.total !== undefined ? { "aria-rowcount": result.total + 1 } : {})}
        >
          <caption className="aip-table__caption">{tr(captionKey)}</caption>
          <thead className="aip-table__header aip-register__head">
            <tr className="aip-table__row">
              {selectable && (
                <th scope="col" className="aip-table__head aip-register__select">
                  <Checkbox
                    aria-label={tr("register.selectPage")}
                    checked={pageSelected ? true : someSelected ? "indeterminate" : false}
                    onCheckedChange={(value) => table.toggleAllRowsSelected(value === true)}
                  />
                </th>
              )}
              {shownColumns.map((column) => {
                const dirs = directions(column as RegisterColumn<unknown>);
                const sorted = query.sort?.id === column.id ? query.sort.dir : undefined;
                return (
                  <th
                    key={column.id}
                    scope="col"
                    className="aip-table__head"
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : dirs.length ? "none" : undefined}
                  >
                    {dirs.length ? (
                      <button
                        type="button"
                        className="aip-register__sort"
                        onClick={() => {
                          const sort = nextSort(column as RegisterColumn<unknown>, query.sort);
                          change(sort ? { ...omit(query, "cursor"), sort } : omit(query, "cursor", "sort"));
                        }}
                      >
                        {tr(column.headerKey)}
                        <span aria-hidden="true">{sorted === "asc" ? " ▲" : sorted === "desc" ? " ▼" : ""}</span>
                      </button>
                    ) : (
                      tr(column.headerKey)
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="aip-table__body" ref={body}>
            {result.isPending ? (
              Array.from({ length: SKELETON_ROWS }, (_, i) => (
                <tr key={`skeleton-${i}`} className="aip-table__row aip-register__skeleton" aria-hidden="true">
                  {/* eslint-disable-next-line jsx-a11y/control-has-associated-label -- a decorative, aria-hidden placeholder */}
                  <td className="aip-table__cell" colSpan={colSpan}>
                    <span className="aip-register__skeleton-bar" />
                  </td>
                </tr>
              ))
            ) : result.isError ? (
              <tr className="aip-table__row">
                <td className="aip-table__cell" colSpan={colSpan}>
                  <span role="alert">
                    {tr("register.error")}
                    {result.requestId ? (
                      <span className="aip-register__ref"> {tr("register.reference", { id: result.requestId })}</span>
                    ) : null}
                  </span>{" "}
                  <Button variant="secondary" onClick={() => void result.refetch()}>
                    {tr("register.retry")}
                  </Button>
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr className="aip-table__row">
                <td className="aip-table__cell" colSpan={colSpan}>
                  {empty ?? tr("register.empty")}
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr
                  key={row.id}
                  data-row=""
                  tabIndex={index === active ? 0 : -1}
                  className={cn("aip-table__row", "aip-register__row", row.getIsSelected() && "aip-register__row--selected")}
                  {...(selectable ? { "aria-selected": row.getIsSelected() } : {})}
                  onFocus={() => setActive(index)}
                  onKeyDown={(event) => onRowKey(event, index, row.original)}
                >
                  {selectable && (
                    <td className="aip-table__cell aip-register__select">
                      <Checkbox
                        aria-label={tr("register.selectRow", { row: rowId(row.original) })}
                        checked={row.getIsSelected()}
                        onCheckedChange={(value) => row.toggleSelected(value === true)}
                      />
                    </td>
                  )}
                  {row.getVisibleCells().map((cell) => {
                    const column = columns.find((c) => c.id === cell.column.id);
                    return (
                      <td key={cell.id} className={cn("aip-table__cell", column?.mono && "aip-register__mono")}>
                        {column?.cell(row.original)}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {result.isPending && (
        <p className="aip-register__status">
          <Spinner label={tr("register.loading")} />
        </p>
      )}

      <nav className="aip-register__pager" aria-label={tr("register.pagination")}>
        <label className="aip-register__page-size" htmlFor={pageSizeId}>
          {tr("register.pageSize")}{" "}
          <select
            id={pageSizeId}
            value={query.limit}
            onChange={(e) => change({ ...omit(query, "cursor"), limit: Number(e.target.value) })}
          >
            {pageSizes.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <Button variant="secondary" disabled={previous.length === 0 && !query.cursor} onClick={goPrevious}>
          {tr("register.previous")}
        </Button>
        <Button variant="secondary" disabled={!result.data?.nextCursor} onClick={goNext}>
          {tr("register.next")}
        </Button>
      </nav>
    </div>
  );
}
