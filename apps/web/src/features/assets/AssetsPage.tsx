/**
 * The `/assets` page (ASSETS-03): the asset tree beside the register. Selecting a tree node sets
 * `under=<id>` in the URL and the register lists that subtree; a "Within: <name>" chip clears it in
 * one click. Below 768 px the tree is a drawer opened from "Browse tree". The URL alone reproduces
 * the view (tree selection, filters, sort, columns).
 */
import { useAssetsGet, type AssetOut } from "@aip/api-client";
import { Button, Dialog, DialogContent, DialogTitle, Icon, type RegisterQuery } from "@aip/ui";
import { useCallback, useEffect, useState } from "react";
import { t } from "../shell/t";
import { AssetsRegister } from "./AssetsRegister";
import { AssetTree } from "./AssetTree";
import type { AssetRow } from "./columns";
import { MoveAssetDialog } from "./MoveAssetDialog";
import { assetsQuery, toSearch, type AssetsSearch } from "./search";

export const NARROW_QUERY = "(max-width: 767.98px)";

function matchNarrow(): MediaQueryList | null {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(NARROW_QUERY) : null;
}

function useNarrow(): boolean {
  const [query] = useState(matchNarrow);
  const [narrow, setNarrow] = useState(query?.matches ?? false);
  useEffect(() => {
    if (!query) return;
    const onChange = () => setNarrow(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [query]);
  return narrow;
}

export interface AssetsPageProps {
  search: AssetsSearch;
  permissions: readonly string[];
  /** Replace the URL search (the route navigates with `replace: true`). */
  onSearchChange: (next: AssetsSearch) => void;
  /** Enter on a register row (until ASSETS-05: the edit form). */
  onOpenAsset: (asset: Pick<AssetOut, "id">) => void;
}

export function AssetsPage({ search, permissions, onSearchChange, onOpenAsset }: AssetsPageProps) {
  const query = assetsQuery(search);
  const under = search.under;
  const narrow = useNarrow();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [moving, setMoving] = useState<AssetRow | null>(null);
  const [moved, setMoved] = useState<string | null>(null);
  const scope = useAssetsGet(under ?? "", { query: { enabled: Boolean(under), retry: false } });
  const underName = scope.data?.status === 200 ? scope.data.data.name : undefined;

  // Any change drops the "created" confirmation: it belongs to the arrival from the form.
  const onQueryChange = useCallback((next: RegisterQuery) => onSearchChange(toSearch(next, under)), [onSearchChange, under]);
  const selectUnder = useCallback(
    (id: string | undefined) => {
      const first: RegisterQuery = { ...query };
      delete first.cursor; // a new scope starts at the first page
      onSearchChange(toSearch(first, id));
      setDrawerOpen(false);
    },
    [onSearchChange, query],
  );
  const onMove = useCallback((asset: AssetRow) => {
    setMoved(null);
    setMoving(asset);
  }, []);

  const tree = <AssetTree selectedId={under} onSelect={(asset) => selectUnder(asset.id)} />;

  return (
    <div className="assets-page">
      {narrow ? null : (
        <aside className="assets-page__tree" aria-labelledby="assets-tree-title">
          <h2 id="assets-tree-title" className="assets-page__tree-title">
            {t("assets.tree.title")}
          </h2>
          {tree}
        </aside>
      )}
      <div className="assets-page__main">
        <div className="assets-page__scope">
          {narrow ? (
            <Button variant="secondary" onClick={() => setDrawerOpen(true)}>
              {t("assets.tree.browse")}
            </Button>
          ) : null}
          {under ? (
            <span className="assets-page__chip">
              <span>{t("assets.scope.within", { name: underName ?? "" })}</span>
              <button type="button" className="assets-page__chip-clear" aria-label={t("assets.scope.clear")} onClick={() => selectUnder(undefined)}>
                <Icon name="close" />
              </button>
            </span>
          ) : null}
        </div>
        {search.created ? (
          <p role="status" className="assets-page__notice">
            {t("assets.register.created", { tag: search.created })}
          </p>
        ) : null}
        {moved ? (
          <p role="status" className="assets-page__notice">
            {moved}
          </p>
        ) : null}
        <AssetsRegister
          query={query}
          under={under}
          underName={underName}
          permissions={permissions}
          onQueryChange={onQueryChange}
          onOpenAsset={onOpenAsset}
          onMove={onMove}
        />
      </div>
      {narrow ? (
        <Dialog open={drawerOpen} onOpenChange={setDrawerOpen}>
          <DialogContent className="assets-drawer" closeLabel={t("assets.tree.close")} aria-describedby={undefined}>
            <DialogTitle>{t("assets.tree.title")}</DialogTitle>
            {tree}
          </DialogContent>
        </Dialog>
      ) : null}
      {moving ? (
        <MoveAssetDialog
          key={moving.id}
          asset={moving}
          open
          onOpenChange={(open) => {
            if (!open) setMoving(null);
          }}
          onMoved={(asset) => setMoved(t("assets.register.moved", { name: asset.name }))}
        />
      ) : null}
    </div>
  );
}
