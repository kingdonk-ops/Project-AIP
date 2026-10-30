/**
 * Thin hooks over the generated `@aip/api-client` item-types operations (ITEMTYPES-03). Reads are
 * the generated query hooks; every mutation invalidates the list and detail keys it affects, so
 * the pages never refetch by hand. No hand-written fetch: the generated client is the only path.
 *
 * The generated calls resolve 4xx/5xx as data (`{status, data, headers}`), so callers branch on
 * `status`; `errorCode` and `requestId` read the error body and the correlation id.
 */
import {
  getItemTypesCategoriesListQueryKey,
  getItemTypesContentTypesGetQueryKey,
  getItemTypesContentTypesListQueryKey,
  getItemTypesItemTypesGetQueryKey,
  getItemTypesItemTypesListQueryKey,
  getItemTypesVersionsGetQueryKey,
  getItemTypesVersionsListQueryKey,
  useItemTypesCategoriesCreate,
  useItemTypesCategoriesDelete,
  useItemTypesCategoriesList,
  useItemTypesCategoriesUpdate,
  useItemTypesContentTypesCreate,
  useItemTypesContentTypesDelete,
  useItemTypesContentTypesGet,
  useItemTypesContentTypesList,
  useItemTypesContentTypesOrder,
  useItemTypesContentTypesUpdate,
  useItemTypesItemTypesCreate,
  useItemTypesItemTypesGet,
  useItemTypesItemTypesList,
  useItemTypesItemTypesUpdate,
  useItemTypesVersionsCreate,
  useItemTypesVersionsDelete,
  useItemTypesVersionsGet,
  useItemTypesVersionsList,
  useItemTypesVersionsPublish,
  useItemTypesVersionsUpdate,
} from "@aip/api-client";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";

/** The `code` of an API error body (`{code, ...}`), if any. */
export function errorCode(data: unknown): string | undefined {
  if (typeof data !== "object" || data === null) return undefined;
  const code = (data as { code?: unknown }).code;
  return typeof code === "string" ? code : undefined;
}

export function requestId(response: { headers: Headers }): string | null {
  return response.headers.get("x-request-id");
}

// List keys are invalidated by their path prefix, so every parameter variant refreshes.
const CONTENT_TYPES = getItemTypesContentTypesListQueryKey().slice(0, 1);
const CATEGORIES = getItemTypesCategoriesListQueryKey().slice(0, 1);
const ITEM_TYPES = getItemTypesItemTypesListQueryKey().slice(0, 1);

function invalidate(queryClient: QueryClient, ...keys: (readonly unknown[])[]) {
  return Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

// ---- reads ---------------------------------------------------------------------------------

export const useContentTypes = () => useItemTypesContentTypesList();
export const useContentType = (id: string) => useItemTypesContentTypesGet(id, { query: { retry: false } });
export const useCategories = (contentTypeId: string) => useItemTypesCategoriesList({ contentTypeId });
export const useItemTypes = (contentTypeId: string) => useItemTypesItemTypesList({ contentTypeId });
export const useItemType = (id: string) => useItemTypesItemTypesGet(id, { query: { retry: false } });
export const useVersions = (itemTypeId: string) => useItemTypesVersionsList(itemTypeId);
export const useVersion = (itemTypeId: string, versionId: string | null | undefined) =>
  useItemTypesVersionsGet(itemTypeId, versionId ?? "", { query: { enabled: Boolean(versionId) } });

// ---- content types -------------------------------------------------------------------------

export function useCreateContentType() {
  const qc = useQueryClient();
  return useItemTypesContentTypesCreate({ mutation: { onSuccess: () => invalidate(qc, CONTENT_TYPES) } });
}

export function useOrderContentTypes() {
  const qc = useQueryClient();
  return useItemTypesContentTypesOrder({ mutation: { onSuccess: () => invalidate(qc, CONTENT_TYPES) } });
}

export function useUpdateContentType() {
  const qc = useQueryClient();
  return useItemTypesContentTypesUpdate({
    mutation: {
      onSuccess: (_r, v) => invalidate(qc, CONTENT_TYPES, getItemTypesContentTypesGetQueryKey(v.contentTypeId)),
    },
  });
}

export function useDeleteContentType() {
  const qc = useQueryClient();
  return useItemTypesContentTypesDelete({ mutation: { onSuccess: () => invalidate(qc, CONTENT_TYPES) } });
}

// ---- categories ----------------------------------------------------------------------------

export function useCreateCategory() {
  const qc = useQueryClient();
  return useItemTypesCategoriesCreate({ mutation: { onSuccess: () => invalidate(qc, CATEGORIES) } });
}

export function useUpdateCategory() {
  const qc = useQueryClient();
  return useItemTypesCategoriesUpdate({ mutation: { onSuccess: () => invalidate(qc, CATEGORIES) } });
}

export function useDeleteCategory() {
  const qc = useQueryClient();
  return useItemTypesCategoriesDelete({ mutation: { onSuccess: () => invalidate(qc, CATEGORIES) } });
}

// ---- item types ----------------------------------------------------------------------------

export function useCreateItemType() {
  const qc = useQueryClient();
  return useItemTypesItemTypesCreate({ mutation: { onSuccess: () => invalidate(qc, ITEM_TYPES, CONTENT_TYPES) } });
}

export function useUpdateItemType() {
  const qc = useQueryClient();
  return useItemTypesItemTypesUpdate({
    mutation: { onSuccess: (_r, v) => invalidate(qc, ITEM_TYPES, getItemTypesItemTypesGetQueryKey(v.itemTypeId)) },
  });
}

// ---- versions (draft, publish) -------------------------------------------------------------

function versionKeys(itemTypeId: string, versionId?: string) {
  return [
    ITEM_TYPES,
    getItemTypesItemTypesGetQueryKey(itemTypeId),
    getItemTypesVersionsListQueryKey(itemTypeId),
    ...(versionId ? [getItemTypesVersionsGetQueryKey(itemTypeId, versionId)] : []),
  ];
}

export function useCreateDraft() {
  const qc = useQueryClient();
  return useItemTypesVersionsCreate({ mutation: { onSuccess: (_r, v) => invalidate(qc, ...versionKeys(v.itemTypeId)) } });
}

export function useSaveDraft() {
  const qc = useQueryClient();
  return useItemTypesVersionsUpdate({
    mutation: { onSuccess: (_r, v) => invalidate(qc, ...versionKeys(v.itemTypeId, v.versionId)) },
  });
}

export function useDiscardDraft() {
  const qc = useQueryClient();
  return useItemTypesVersionsDelete({
    mutation: { onSuccess: (_r, v) => invalidate(qc, ...versionKeys(v.itemTypeId, v.versionId)) },
  });
}

export function usePublishDraft() {
  const qc = useQueryClient();
  return useItemTypesVersionsPublish({
    mutation: { onSuccess: (_r, v) => invalidate(qc, ...versionKeys(v.itemTypeId, v.versionId)) },
  });
}
