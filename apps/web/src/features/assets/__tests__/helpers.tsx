/**
 * Test helpers for the assets page: the shared app harness (real router, providers, fake session,
 * MSW in front of the generated client) from the projects tests, plus asset and item-type rows and
 * MSW handlers that answer the assets list like the server does for `parentId`, `under`, `q` and
 * `tagNumber`.
 */
import type { AssetDetail, AssetListItem, AssetOut, ItemTypeOut, ItemTypeVersionOut } from "@aip/api-client";
import { http, HttpResponse } from "msw";
import { api } from "../../projects/__tests__/helpers";

export { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";

let next = 0;

/** A UUID-shaped id that is stable within a test run. */
export function id(): string {
  next += 1;
  return `00000000-0000-7000-8000-${String(next).padStart(12, "0")}`;
}

export function asset(overrides: Partial<AssetOut> & Pick<AssetOut, "name">): AssetOut {
  const assetId = overrides.id ?? id();
  return {
    id: assetId,
    parentId: null,
    path: assetId.replace(/-/g, ""),
    internalTag: `AT-${assetId.slice(-12, -8)}-${assetId.slice(-8, -4)}-${assetId.slice(-4)}`.toUpperCase(),
    tagNumber: null,
    sortOrder: 0,
    itemTypeId: null,
    itemTypeVersionId: null,
    attributes: {},
    createdBy: null,
    syncVersion: 1,
    createdAt: "2026-10-28T00:00:00Z",
    updatedAt: "2026-10-28T01:00:00Z",
    childCount: 0,
    ...overrides,
  };
}

export function itemType(overrides: Partial<ItemTypeOut> & Pick<ItemTypeOut, "name">): ItemTypeOut {
  return {
    id: id(),
    categoryId: id(),
    contentTypeId: id(),
    key: overrides.name.toLowerCase().replace(/\W+/g, "_"),
    description: null,
    isComponent: false,
    allowsComponents: false,
    publishedVersion: 1,
    publishedVersionId: id(),
    draftVersionId: null,
    syncVersion: 1,
    createdAt: "2026-10-28T00:00:00Z",
    updatedAt: "2026-10-28T00:00:00Z",
    ...overrides,
  };
}

export function version(type: ItemTypeOut, attributes: Record<string, unknown>[]): ItemTypeVersionOut {
  return {
    id: type.publishedVersionId ?? id(),
    itemTypeId: type.id,
    version: 1,
    status: "published",
    attributes,
    changeSummary: null,
    publishedAt: "2026-10-28T00:00:00Z",
    publishedBy: null,
    createdBy: null,
    syncVersion: 1,
    createdAt: "2026-10-28T00:00:00Z",
    updatedAt: "2026-10-28T00:00:00Z",
    compiledSchema: {},
  };
}

/** `GET /assets/{id}`: the asset with its ancestors, looked up in `all`. */
export function detail(all: readonly AssetOut[], target: AssetOut): AssetDetail {
  const byId = new Map(all.map((a) => [a.id, a]));
  const ancestors = [];
  for (let p = target.parentId; p; p = byId.get(p)?.parentId ?? null) {
    const parent = byId.get(p);
    if (!parent) break;
    ancestors.unshift({ id: parent.id, name: parent.name, internalTag: parent.internalTag, tagNumber: parent.tagNumber });
  }
  return { ...target, ancestors };
}

function under(all: readonly AssetOut[], rootId: string): AssetOut[] {
  const out: AssetOut[] = [];
  const walk = (parentId: string) => {
    for (const a of all.filter((x) => x.parentId === parentId)) {
      out.push(a);
      walk(a.id);
    }
  };
  walk(rootId);
  return out;
}

/** A list row: the asset with its ancestors' names, root first (ASSETS-08). */
export function listItem(all: readonly AssetOut[], target: AssetOut): AssetListItem {
  return { ...target, ancestorNames: detail(all, target).ancestors.map((a) => a.name) };
}

/** The assets list over a fixed set; `seen` records each list request. */
export function assetsListApi(all: readonly AssetOut[], seen?: URL[]) {
  return http.get(api("/api/v1/assets"), ({ request }) => {
    const url = new URL(request.url);
    seen?.push(url);
    const params = url.searchParams;
    let items = [...all];
    const parentId = params.get("parentId");
    if (parentId === "root") items = items.filter((a) => a.parentId === null);
    else if (parentId) items = items.filter((a) => a.parentId === parentId);
    const scope = params.get("under");
    if (scope) items = under(all, scope);
    const q = params.get("q")?.toLowerCase();
    if (q) items = items.filter((a) => a.name.toLowerCase().includes(q));
    const tag = params.get("tagNumber")?.toUpperCase();
    if (tag) items = items.filter((a) => a.tagNumber?.toUpperCase() === tag);
    const sort = params.get("sort") ?? "name";
    if (sort.endsWith("name")) items.sort((a, b) => a.name.localeCompare(b.name) * (sort.startsWith("-") ? -1 : 1));
    const limit = Number(params.get("limit") ?? 50);
    return HttpResponse.json({ items: items.slice(0, limit).map((a) => listItem(all, a)), nextCursor: null });
  });
}

/** Handlers for the assets list and get, over a fixed set; `seen` records each list request. */
export function assetsApi(all: readonly AssetOut[], seen?: URL[]) {
  return [
    assetsListApi(all, seen),
    http.get(api("/api/v1/assets/:assetId"), ({ params }) => {
      const target = all.find((a) => a.id === params.assetId);
      return target ? HttpResponse.json(detail(all, target)) : HttpResponse.json({ code: "NOT_FOUND" }, { status: 404 });
    }),
  ];
}

export function itemTypesApi(types: readonly ItemTypeOut[], versions: readonly ItemTypeVersionOut[] = []) {
  return [
    http.get(api("/api/v1/item-types"), () => HttpResponse.json({ items: types })),
    http.get(api("/api/v1/item-types/:itemTypeId/versions/:versionId"), ({ params }) => {
      const found = versions.find((v) => v.id === params.versionId);
      return found ? HttpResponse.json(found) : HttpResponse.json({ code: "NOT_FOUND" }, { status: 404 });
    }),
  ];
}
