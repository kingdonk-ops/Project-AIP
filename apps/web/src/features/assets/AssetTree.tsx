/**
 * The asset tree panel (ASSETS-03), following the WAI-ARIA tree pattern: `role="tree"` with
 * `treeitem`s that carry `aria-level`, `aria-setsize`, `aria-posinset` and, only when the asset has
 * children, `aria-expanded`. Each level loads lazily through the generated `assets_list` call
 * (`parentId=<id>|root&sort=position`, 200 per page) with a "Show more" item for the next page.
 *
 * Keyboard: Up/Down move, Right expands or enters the first child, Left collapses or goes to the
 * parent, Home/End jump to the first/last visible item, Enter (or Space) selects (or shows more). One roving
 * `tabIndex`: only the focused item (the first one until the user moves) is in the tab order.
 * Expanded ids persist per browser tab in `sessionStorage`.
 */
import { getAssetsListQueryOptions, type AssetOut } from "@aip/api-client";
import { Icon } from "@aip/ui";
import { useQueries } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { t } from "../shell/t";

export const TREE_PAGE_SIZE = 200;
export const EXPANDED_STORAGE_KEY = "aip.assets.tree.expanded";
const ROOT = "root";

function readExpanded(): Set<string> {
  try {
    const raw = window.sessionStorage.getItem(EXPANDED_STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : []);
  } catch {
    return new Set();
  }
}

function writeExpanded(ids: ReadonlySet<string>): void {
  try {
    window.sessionStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify([...ids]));
  } catch {
    // Storage may be unavailable (private mode, blocked): the tree still works for this view.
  }
}

interface TreeState {
  expanded: ReadonlySet<string>;
  toggle: (id: string, open?: boolean) => void;
  /** The item in the tab order (`null`: the first item). */
  focusedId: string | null;
  setFocusedId: (id: string) => void;
  firstId: string | null;
  setFirstId: (id: string | null) => void;
  selectedId: string | undefined;
  select: (asset: Pick<AssetOut, "id" | "name">) => void;
}

const TreeContext = createContext<TreeState | null>(null);

function useTree(): TreeState {
  const state = useContext(TreeContext);
  if (!state) throw new Error("AssetTree items render inside AssetTree");
  return state;
}

export interface AssetTreeProps {
  /** The asset whose subtree the register shows (`under`). */
  selectedId?: string | undefined;
  onSelect: (asset: Pick<AssetOut, "id" | "name">) => void;
}

export function AssetTree({ selectedId, onSelect }: AssetTreeProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(readExpanded);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [firstId, setFirstId] = useState<string | null>(null);
  const treeRef = useRef<HTMLUListElement>(null);

  useEffect(() => writeExpanded(expanded), [expanded]);

  // When the focused item disappears (its parent collapsed, or it moved), the first item takes the
  // tab stop again, so the tree is never left without one.
  useEffect(() => {
    const tree = treeRef.current;
    if (focusedId && tree && !tree.querySelector('[role="treeitem"][tabindex="0"]')) setFocusedId(null);
  }, [focusedId, expanded]);

  const toggle = useCallback((id: string, open?: boolean) => {
    setExpanded((current) => {
      const willOpen = open ?? !current.has(id);
      if (willOpen === current.has(id)) return current;
      const next = new Set(current);
      if (willOpen) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const state = useMemo<TreeState>(
    () => ({ expanded, toggle, focusedId, setFocusedId, firstId, setFirstId, selectedId, select: onSelect }),
    [expanded, toggle, focusedId, firstId, selectedId, onSelect],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    const tree = treeRef.current;
    const current = (event.target as HTMLElement).closest<HTMLElement>('[role="treeitem"]');
    if (!tree || !current) return;
    const items = Array.from(tree.querySelectorAll<HTMLElement>('[role="treeitem"]'));
    const index = items.indexOf(current);
    const level = Number(current.getAttribute("aria-level"));
    const expandedAttr = current.getAttribute("aria-expanded");
    const id = current.dataset.id;
    const focus = (el: HTMLElement | null | undefined) => {
      if (!el) return;
      event.preventDefault();
      el.focus();
    };
    switch (event.key) {
      case "ArrowDown":
        focus(items[index + 1]);
        break;
      case "ArrowUp":
        focus(items[index - 1]);
        break;
      case "Home":
        focus(items[0]);
        break;
      case "End":
        focus(items.at(-1));
        break;
      case "ArrowRight":
        event.preventDefault();
        if (expandedAttr === "false" && id) toggle(id, true);
        else if (expandedAttr === "true") {
          const next = items[index + 1];
          if (next && Number(next.getAttribute("aria-level")) > level) next.focus();
        }
        break;
      case "ArrowLeft":
        event.preventDefault();
        if (expandedAttr === "true" && id) toggle(id, false);
        else if (current.dataset.parent && current.dataset.parent !== ROOT) {
          focus(tree.querySelector<HTMLElement>(`[role="treeitem"][data-id="${current.dataset.parent}"]`));
        }
        break;
      default:
    }
  };

  return (
    <TreeContext.Provider value={state}>
      <RootLevel treeRef={treeRef} onKeyDown={onKeyDown} />
    </TreeContext.Provider>
  );
}

/** Pages of one parent's children: the first page, then one more per "Show more". */
function useLevel(parentId: string) {
  const [cursors, setCursors] = useState<string[]>([]);
  const pages = useQueries({
    queries: [undefined, ...cursors].map((cursor) =>
      getAssetsListQueryOptions({ parentId, sort: "position", limit: TREE_PAGE_SIZE, ...(cursor ? { cursor } : {}) }),
    ),
  });
  const ok = pages.map((p) => (p.data?.status === 200 ? p.data.data : undefined));
  const items = ok.flatMap((page) => page?.items ?? []);
  const last = ok.at(-1);
  const failed = pages.some((p) => p.isError || (p.data !== undefined && p.data.status !== 200));
  return {
    items,
    pending: pages.some((p) => p.isPending),
    failed,
    nextCursor: last?.nextCursor ?? null,
    showMore: () => {
      const next = last?.nextCursor;
      if (next) setCursors((c) => (c.includes(next) ? c : [...c, next]));
    },
  };
}

function RootLevel({
  treeRef,
  onKeyDown,
}: {
  treeRef: RefObject<HTMLUListElement | null>;
  onKeyDown: (event: KeyboardEvent<HTMLUListElement>) => void;
}) {
  const { setFirstId } = useTree();
  const level = useLevel(ROOT);
  const first = level.items[0]?.id ?? null;
  useEffect(() => setFirstId(first), [first, setFirstId]);

  return (
    <div className="assets-tree">
      {level.pending && level.items.length === 0 ? (
        <p className="assets-tree__note" role="status">
          {t("assets.tree.loading")}
        </p>
      ) : null}
      {level.failed ? (
        <p className="assets-tree__note" role="alert">
          {t("assets.tree.error")}
        </p>
      ) : null}
      {!level.pending && !level.failed && level.items.length === 0 ? (
        <p className="assets-tree__note">{t("assets.tree.empty")}</p>
      ) : null}
      {level.items.length > 0 ? (
        <ul ref={treeRef} role="tree" aria-label={t("assets.tree.label")} className="assets-tree__list" onKeyDown={onKeyDown}>
          <LevelItems parentId={ROOT} depth={1} level={level} />
        </ul>
      ) : null}
    </div>
  );
}

function LevelItems({ parentId, depth, level }: { parentId: string; depth: number; level: ReturnType<typeof useLevel> }) {
  const setsize = level.items.length;
  return (
    <>
      {level.items.map((asset, index) => (
        <TreeItem key={asset.id} asset={asset} parentId={parentId} depth={depth} posinset={index + 1} setsize={setsize} />
      ))}
      {level.nextCursor ? <ShowMore parentId={parentId} depth={depth} onShowMore={level.showMore} /> : null}
    </>
  );
}

function ChildGroup({ id, parentId, depth }: { id: string; parentId: string; depth: number }) {
  const level = useLevel(parentId);
  return (
    <ul id={id} role="group" className="assets-tree__group" aria-busy={level.pending || undefined}>
      <LevelItems parentId={parentId} depth={depth} level={level} />
    </ul>
  );
}

// Each node is `li[role=none] > div[role=treeitem]` plus, when open, its `ul[role=group]` owned by
// the treeitem (`aria-owns`). The treeitem's name is then its own row's text, never its children's.
function TreeItem({
  asset,
  parentId,
  depth,
  posinset,
  setsize,
}: {
  asset: AssetOut;
  parentId: string;
  depth: number;
  posinset: number;
  setsize: number;
}) {
  const tree = useTree();
  const groupId = useId();
  const hasChildren = (asset.childCount ?? 0) > 0;
  const isOpen = hasChildren && tree.expanded.has(asset.id);
  const tabStop = (tree.focusedId ?? tree.firstId) === asset.id;
  const select = () => tree.select({ id: asset.id, name: asset.name });
  return (
    <li role="none" className="assets-tree__node">
      <div
        role="treeitem"
        className="assets-tree__item assets-tree__row"
        style={{ paddingInlineStart: `${(depth - 1) * 1.25}rem` }}
        data-id={asset.id}
        data-parent={parentId}
        aria-level={depth}
        aria-setsize={setsize}
        aria-posinset={posinset}
        aria-selected={tree.selectedId === asset.id}
        {...(hasChildren ? { "aria-expanded": isOpen } : {})}
        {...(isOpen ? { "aria-owns": groupId } : {})}
        tabIndex={tabStop ? 0 : -1}
        onFocus={() => tree.setFocusedId(asset.id)}
        onClick={select}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          select();
        }}
      >
        <span
          className="assets-tree__toggle"
          data-open={isOpen || undefined}
          aria-hidden="true"
          onClick={(event) => {
            if (!hasChildren) return;
            event.stopPropagation();
            (event.currentTarget.closest('[role="treeitem"]') as HTMLElement | null)?.focus();
            tree.toggle(asset.id);
          }}
        >
          {hasChildren ? <Icon name="chevron-down" /> : null}
        </span>
        <span className="assets-tree__label">{asset.name}</span>
        {asset.tagNumber ? <span className="assets-tree__tag">{asset.tagNumber}</span> : null}
      </div>
      {isOpen ? <ChildGroup id={groupId} parentId={asset.id} depth={depth + 1} /> : null}
    </li>
  );
}

function ShowMore({ parentId, depth, onShowMore }: { parentId: string; depth: number; onShowMore: () => void }) {
  const tree = useTree();
  const id = `more:${parentId}`;
  return (
    <li role="none" className="assets-tree__node">
      <div
        role="treeitem"
        className="assets-tree__item assets-tree__row assets-tree__more"
        style={{ paddingInlineStart: `${(depth - 1) * 1.25 + 1.5}rem` }}
        data-more=""
        data-parent={parentId}
        aria-level={depth}
        aria-selected={false}
        tabIndex={tree.focusedId === id ? 0 : -1}
        onFocus={() => tree.setFocusedId(id)}
        onClick={onShowMore}
        onKeyDown={(event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          onShowMore();
        }}
      >
        {t("assets.tree.show_more")}
      </div>
    </li>
  );
}
