/**
 * The assets register (ASSETS-03) on DESIGN-03's `RegisterTable`: item type (multi-select) and free
 * text filters, server-side sort both ways on Name, Tag Number and Updated, cursor paging, a column
 * chooser and CSV export through `GET /assets/export.csv` with the same query. `under` (set by the
 * tree) narrows the rows to that asset's subtree. Everything lives in the URL (see `search.ts`).
 */
import { getAssetsExportUrl, useAssetsList } from "@aip/api-client";
import { Button, RegisterTable, type RegisterFilter, type RegisterQuery, type RegisterQueryResult } from "@aip/ui";
import { Link } from "@tanstack/react-router";
import { createContext, useContext, useMemo } from "react";
import { t } from "../shell/t";
import { assetColumns, type AssetRow } from "./columns";
import { crumb, useItemTypes } from "./data";
import { toExportParams, toListParams } from "./search";
import { assetsTranslate, ITEM_TYPE_OPTION_PREFIX } from "./terms";

interface Scope {
  under: string | undefined;
  itemTypeNames: ReadonlyMap<string, string>;
}

/** What the page adapter needs besides the register query: the tree scope and item type names. */
const ScopeContext = createContext<Scope>({ under: undefined, itemTypeNames: new Map() });

function useAssetsPage(query: RegisterQuery): RegisterQueryResult<AssetRow> {
  const { under, itemTypeNames } = useContext(ScopeContext);
  const list = useAssetsList(toListParams(query, under));
  const response = list.data;
  const page = response?.status === 200 ? response.data : undefined;
  const data = useMemo(
    () =>
      page && {
        nextCursor: page.nextCursor,
        items: page.items.map(
          (a): AssetRow => ({
            ...a,
            parentCrumb: crumb(a.ancestorNames),
            itemTypeName: a.itemTypeId ? (itemTypeNames.get(a.itemTypeId) ?? "") : "",
          }),
        ),
      },
    [page, itemTypeNames],
  );
  const failed = response !== undefined && response.status !== 200;
  return {
    data,
    isPending: list.isPending,
    isError: list.isError || failed,
    refetch: () => void list.refetch(),
    requestId: failed ? response.headers.get("x-request-id") : null,
  };
}

export interface AssetsRegisterProps {
  query: RegisterQuery;
  /** The asset whose subtree is listed, and its name. */
  under?: string | undefined;
  underName?: string | undefined;
  permissions: readonly string[];
  /** Replace the URL search (the route navigates with `replace: true`). */
  onQueryChange: (next: RegisterQuery) => void;
  /** Enter on a row. */
  onOpenAsset: (asset: AssetRow) => void;
  onMove: (asset: AssetRow) => void;
}

export function AssetsRegister({ query, under, underName, permissions, onQueryChange, onOpenAsset, onMove }: AssetsRegisterProps) {
  const canCreate = permissions.includes("asset.create");
  const itemTypes = useItemTypes();
  const columns = useMemo(() => assetColumns({ permissions, onMove }), [permissions, onMove]);
  const translate = useMemo(() => assetsTranslate(itemTypes.names), [itemTypes.names]);
  const filters = useMemo<readonly RegisterFilter[]>(
    () => [
      {
        id: "itemType",
        kind: "multi",
        labelKey: "assets.filter.item_type",
        options: itemTypes.items.map((i) => ({ value: i.id, labelKey: `${ITEM_TYPE_OPTION_PREFIX}${i.id}` })),
      },
    ],
    [itemTypes.items],
  );
  const scope = useMemo<Scope>(() => ({ under, itemTypeNames: itemTypes.names }), [under, itemTypes.names]);
  const filtered = Object.keys(query.filters).length > 0 || Boolean(query.q);
  const createLink = canCreate ? (
    <Button asChild>
      <Link to="/assets/new" search={under ? { parentId: under } : {}}>
        {t("assets.register.create")}
      </Link>
    </Button>
  ) : null;

  return (
    <section className="assets-register" aria-labelledby="assets-register-title">
      <div className="assets-register__header">
        <h1 id="assets-register-title">{t("assets.register.title")}</h1>
        {createLink}
      </div>
      <ScopeContext.Provider value={scope}>
        <RegisterTable<AssetRow>
          id="assets"
          captionKey="assets.register.caption"
          columns={columns}
          filters={filters}
          query={query}
          onQueryChange={onQueryChange}
          useQuery={useAssetsPage}
          rowId={(a) => a.id}
          onOpenRow={onOpenAsset}
          permissions={permissions}
          exportHref={(q) => getAssetsExportUrl(toExportParams(q, under))}
          translate={translate}
          empty={
            filtered ? undefined : (
              <div className="assets-register__empty">
                <p>{under && underName ? t("assets.register.empty_within", { name: underName }) : t("assets.register.empty")}</p>
                {createLink}
              </div>
            )
          }
        />
      </ScopeContext.Provider>
    </section>
  );
}
