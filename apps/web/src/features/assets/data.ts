/**
 * Shared reads of the assets page (ASSETS-03), all through the generated `@aip/api-client`: the
 * tenant's item types and the cache keys a write invalidates. Breadcrumbs come with each list row
 * (`ancestorNames`, ASSETS-08), so no parent is fetched on its own. The generated calls resolve 4xx/5xx as data, so callers
 * branch on `status`.
 */
import {
  getAssetsGetQueryKey,
  getAssetsListQueryKey,
  useItemTypesItemTypesList,
  type ItemTypeOut,
} from "@aip/api-client";
import type { QueryClient } from "@tanstack/react-query";
import { useMemo } from "react";

export const CRUMB_SEPARATOR = " > ";

/** A breadcrumb (`Site A > Unit 1`) from names, root first. */
export function crumb(names: readonly string[]): string {
  return names.join(CRUMB_SEPARATOR);
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
