/**
 * Shared reads of the assets page (ASSETS-03), all through the generated `@aip/api-client`:
 * breadcrumbs of parent assets (from `GET /assets/{id}`'s ancestors), the tenant's item types and
 * the cache keys a write invalidates. The generated calls resolve 4xx/5xx as data, so callers
 * branch on `status`.
 */
import {
  getAssetsGetQueryKey,
  getAssetsGetQueryOptions,
  getAssetsListQueryKey,
  useItemTypesItemTypesList,
  type ItemTypeOut,
} from "@aip/api-client";
import { useQueries, type QueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

const CRUMB_STALE_MS = 30_000;
export const CRUMB_SEPARATOR = " > ";

/** Breadcrumbs (`Site A > Unit 1`) of the given assets, by id; ids still loading are absent. */
export function useCrumbs(ids: readonly string[]): Readonly<Record<string, string>> {
  const unique = [...new Set(ids)].sort();
  // `combine` output is structurally shared, so the record keeps its identity until a crumb changes.
  return useQueries({
    queries: unique.map((id) => getAssetsGetQueryOptions(id, { query: { retry: false, staleTime: CRUMB_STALE_MS } })),
    combine: (results) => {
      const crumbs: Record<string, string> = {};
      for (const result of results) {
        const response = result.data;
        if (response?.status !== 200) continue;
        const names = [...response.data.ancestors.map((a) => a.name), response.data.name];
        crumbs[response.data.id] = names.join(CRUMB_SEPARATOR);
      }
      return crumbs;
    },
  });
}

export interface ItemTypes {
  items: readonly ItemTypeOut[];
  /** Item types that have a published version (the ones an asset can be typed with). */
  published: readonly ItemTypeOut[];
  names: ReadonlyMap<string, string>;
}

/** The tenant's item types (needs `item_type.view`; without it the list is empty). */
export function useItemTypes(): ItemTypes {
  const list = useItemTypesItemTypesList(undefined, { query: { retry: false } });
  return useMemo(() => {
    const items = list.data?.status === 200 ? list.data.data.items : [];
    return {
      items,
      published: items.filter((i) => Boolean(i.publishedVersionId)),
      names: new Map(items.map((i) => [i.id, i.name])),
    };
  }, [list.data]);
}

/** Refresh every asset list (the register and each tree level) and, when given, one asset. */
export function invalidateAssets(queryClient: QueryClient, assetId?: string): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: getAssetsListQueryKey().slice(0, 1) }),
    ...(assetId ? [queryClient.invalidateQueries({ queryKey: getAssetsGetQueryKey(assetId) })] : []),
  ]);
}
