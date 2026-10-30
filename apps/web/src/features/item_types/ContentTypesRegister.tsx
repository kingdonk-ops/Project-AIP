/**
 * The content-types register `/admin/content-types` (ITEMTYPES-03) on DESIGN-03's `RegisterTable`.
 * The API returns the tenant's whole list (at most 50), so the `useQuery` adapter filters ("In
 * navigation"), searches (name or key) and sorts the fetched array in memory; the query itself
 * lives in the URL like PROJECTS-06. With `item_type.manage` each row can move up or down (`PUT
 * /content-types/order`, plain buttons rather than drag), be shown or hidden in navigation, or be
 * deleted after typing its key; Create opens `ContentTypeDialog`. The server checks every call.
 */
import type { ContentTypeOut } from "@aip/api-client";
import {
  Button,
  confirm,
  decodeRegisterQuery,
  encodeRegisterQuery,
  Icon,
  RegisterTable,
  toast,
  type IconName,
  type RegisterColumn,
  type RegisterFilter,
  type RegisterQuery,
  type RegisterQueryResult,
  type RegisterSpec,
  type Translate,
} from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { t } from "../shell/t";
import { errorCode, useContentTypes, useDeleteContentType, useOrderContentTypes, useUpdateContentType } from "./api";
import { ContentTypeDialog } from "./ContentTypeDialog";

export const DEFAULT_LIMIT = 50;

export const CONTENT_TYPES_SPEC = {
  filters: [{ id: "nav", kind: "select", options: [{ value: "yes" }, { value: "no" }] }],
  sortable: { name: ["asc", "desc"], key: ["asc", "desc"], sortOrder: ["asc", "desc"] },
  columns: ["name", "key", "icon", "sortOrder", "showInNav", "itemTypeCount", "actions"],
  defaultLimit: DEFAULT_LIMIT,
} as const satisfies RegisterSpec;

export function contentTypesQuery(search: Record<string, unknown>): RegisterQuery {
  return decodeRegisterQuery(search, CONTENT_TYPES_SPEC);
}

export function toContentTypesSearch(query: RegisterQuery): Record<string, string> {
  return encodeRegisterQuery(query, DEFAULT_LIMIT);
}

export function validateContentTypesSearch(search: Record<string, unknown>): Record<string, string> {
  return toContentTypesSearch(contentTypesQuery(search));
}

const TERMS: Readonly<Record<string, string>> = {
  "register.search": "item_types.filter.search",
  "register.any": "item_types.filter.any",
  "register.clearAll": "item_types.filter.clear",
  "register.empty": "item_types.empty.filtered",
  "register.loading": "item_types.loading",
  "register.error": "item_types.error.load",
  "register.reference": "item_types.error.request_id",
  "register.retry": "item_types.error.retry",
};
const translate: Translate = (key, params) => t(TERMS[key] ?? key, params);

const filters: readonly RegisterFilter[] = [
  {
    id: "nav",
    kind: "select",
    labelKey: "item_types.filter.nav",
    quick: true,
    options: [
      { value: "yes", labelKey: "item_types.filter.nav.yes" },
      { value: "no", labelKey: "item_types.filter.nav.no" },
    ],
  },
];

/** The tenant's order: sort order, then name. */
export function byOrder(a: ContentTypeOut, b: ContentTypeOut): number {
  return a.sortOrder - b.sortOrder || a.name.localeCompare(b.name);
}

/** Filter, search and sort the whole list as the register query asks. */
export function applyQuery(items: readonly ContentTypeOut[], query: RegisterQuery): ContentTypeOut[] {
  const nav = query.filters.nav;
  const q = query.q?.trim().toLowerCase() ?? "";
  const rows = items.filter(
    (c) =>
      (nav === "yes" ? c.showInNav : nav === "no" ? !c.showInNav : true) &&
      (!q || c.name.toLowerCase().includes(q) || c.key.toLowerCase().includes(q)),
  );
  const sort = query.sort;
  const compare: (a: ContentTypeOut, b: ContentTypeOut) => number =
    sort?.id === "name"
      ? (a, b) => a.name.localeCompare(b.name)
      : sort?.id === "key"
        ? (a, b) => a.key.localeCompare(b.key)
        : byOrder;
  rows.sort(compare);
  if (sort?.dir === "desc") rows.reverse();
  return rows;
}

/** The ids in their new order after moving `id` one place (`-1` up, `1` down); null at an end. */
export function moved(ordered: readonly ContentTypeOut[], id: string, by: -1 | 1): string[] | null {
  const ids = ordered.map((c) => c.id);
  const at = ids.indexOf(id);
  const to = at + by;
  if (at < 0 || to < 0 || to >= ids.length) return null;
  [ids[at], ids[to]] = [ids[to]!, ids[at]!];
  return ids;
}

export interface ContentTypesRegisterProps {
  query: RegisterQuery;
  permissions: readonly string[];
  onQueryChange: (next: RegisterQuery) => void;
  onOpen: (contentType: ContentTypeOut) => void;
}

export function ContentTypesRegister({ query, permissions, onQueryChange, onOpen }: ContentTypesRegisterProps) {
  const canManage = permissions.includes("item_type.manage");
  const [creating, setCreating] = useState(false);
  const list = useContentTypes();
  const order = useOrderContentTypes();
  const update = useUpdateContentType();
  const remove = useDeleteContentType();
  const busy = order.isPending || update.isPending || remove.isPending;

  const all = useMemo(
    () => (list.data?.status === 200 ? [...list.data.data.items].sort(byOrder) : []),
    [list.data],
  );

  async function move(row: ContentTypeOut, by: -1 | 1) {
    const ids = moved(all, row.id, by);
    if (!ids) return;
    const response = await order.mutateAsync({ data: { ids } });
    if (response.status !== 200) toast.error("item_types.error.save");
  }

  async function toggleNav(row: ContentTypeOut) {
    const response = await update.mutateAsync({
      contentTypeId: row.id,
      data: { syncVersion: row.syncVersion, showInNav: !row.showInNav },
    });
    if (response.status === 200) return;
    if (errorCode(response.data) === "VERSION_CONFLICT") {
      await list.refetch();
      toast.error("item_types.error.conflict");
    } else toast.error("item_types.error.save");
  }

  async function del(row: ContentTypeOut) {
    const ok = await confirm({
      titleKey: "item_types.content_type.delete.title",
      bodyKey: "item_types.content_type.delete.body",
      confirmKey: "item_types.content_type.delete.submit",
      params: { name: row.name, key: row.key },
      tone: "danger",
      requireText: row.key,
    });
    if (!ok) return;
    const response = await remove.mutateAsync({ contentTypeId: row.id });
    if (response.status === 204) {
      toast.success("item_types.content_type.deleted", { name: row.name });
      return;
    }
    const data = response.data as Record<string, unknown>;
    const code = errorCode(data);
    if (code === "CONTENT_TYPE_IN_USE") {
      toast.error("item_types.content_type.delete.in_use", { count: Number(data.categories ?? 0) });
    } else if (code === "CONTENT_TYPE_SYSTEM") {
      toast.error("item_types.content_type.delete.system");
    } else toast.error("item_types.error.save");
  }

  const columns = useMemo<RegisterColumn<ContentTypeOut>[]>(() => {
    const base: RegisterColumn<ContentTypeOut>[] = [
      {
        id: "name",
        headerKey: "item_types.content_type.field.name",
        sortable: true,
        cell: (c) => (
          <Link to="/admin/content-types/$contentTypeId" params={{ contentTypeId: c.id }}>
            {c.name}
          </Link>
        ),
      },
      { id: "key", headerKey: "item_types.content_type.field.key", cell: (c) => c.key, mono: true, sortable: true },
      {
        id: "icon",
        headerKey: "item_types.content_type.field.icon",
        cell: (c) => (
          <span className="item-types-icon">
            <Icon name={c.icon as IconName} size={16} />
            <span className="item-types-mono">{c.icon}</span>
          </span>
        ),
      },
      { id: "sortOrder", headerKey: "item_types.content_type.field.sort_order", cell: (c) => c.sortOrder, sortable: true },
      {
        id: "showInNav",
        headerKey: "item_types.content_type.field.show_in_nav",
        cell: (c) => t(c.showInNav ? "item_types.yes" : "item_types.no"),
      },
      { id: "itemTypeCount", headerKey: "item_types.content_type.field.item_types", cell: (c) => c.itemTypeCount },
    ];
    if (!canManage) return base;
    return [
      ...base,
      {
        id: "actions",
        headerKey: "item_types.column.actions",
        csv: () => "",
        cell: (c) => {
          const at = all.findIndex((x) => x.id === c.id);
          return (
            <span className="item-types-actions">
              <Button
                variant="ghost"
                disabled={busy || at <= 0}
                aria-label={t("item_types.content_type.move_up", { name: c.name })}
                onClick={() => void move(c, -1)}
              >
                {t("item_types.action.move_up")}
              </Button>
              <Button
                variant="ghost"
                disabled={busy || at < 0 || at >= all.length - 1}
                aria-label={t("item_types.content_type.move_down", { name: c.name })}
                onClick={() => void move(c, 1)}
              >
                {t("item_types.action.move_down")}
              </Button>
              <Button
                variant="ghost"
                disabled={busy}
                aria-label={t(c.showInNav ? "item_types.content_type.hide_named" : "item_types.content_type.show_named", {
                  name: c.name,
                })}
                onClick={() => void toggleNav(c)}
              >
                {t(c.showInNav ? "item_types.content_type.hide" : "item_types.content_type.show")}
              </Button>
              <Button
                variant="ghost"
                disabled={busy}
                aria-label={t("item_types.content_type.delete_named", { name: c.name })}
                onClick={() => void del(c)}
              >
                {t("item_types.action.delete")}
              </Button>
            </span>
          );
        },
      },
    ];
    // The handlers close over `all` and the mutations, which the deps cover.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, canManage, busy]);

  function rowsFor(q: RegisterQuery): RegisterQueryResult<ContentTypeOut> {
    const response = list.data;
    const failed = response !== undefined && response.status !== 200;
    return {
      data: response?.status === 200 ? { items: applyQuery(response.data.items, q), nextCursor: null } : undefined,
      isPending: list.isPending,
      isError: list.isError || failed,
      refetch: () => void list.refetch(),
      requestId: failed ? response.headers.get("x-request-id") : null,
    };
  }

  const filtered = Object.keys(query.filters).length > 0 || Boolean(query.q);

  return (
    <section className="item-types-page" aria-labelledby="content-types-title">
      <div className="item-types-page__header">
        <h1 id="content-types-title">{t("item_types.register.title")}</h1>
        {canManage ? <Button onClick={() => setCreating(true)}>{t("item_types.content_type.create")}</Button> : null}
      </div>
      <RegisterTable<ContentTypeOut>
        id="content-types"
        captionKey="item_types.register.caption"
        columns={columns}
        filters={filters}
        query={query}
        onQueryChange={onQueryChange}
        useQuery={rowsFor}
        rowId={(c) => c.id}
        onOpenRow={onOpen}
        permissions={permissions}
        translate={translate}
        empty={
          filtered ? undefined : (
            <div className="item-types-page__empty">
              <p>{t("item_types.empty.content_types")}</p>
              {canManage ? <Button onClick={() => setCreating(true)}>{t("item_types.content_type.create")}</Button> : null}
            </div>
          )
        }
      />
      {canManage ? <ContentTypeDialog open={creating} onOpenChange={setCreating} /> : null}
    </section>
  );
}
