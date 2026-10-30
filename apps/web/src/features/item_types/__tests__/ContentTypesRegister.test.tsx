import type { CategoryOut, ContentTypeOut, ItemTypeOut } from "@aip/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { t } from "../../shell/t";
import { validateContentTypesSearch } from "../ContentTypesRegister";

const VIEW = ["item_type.view"];
const MANAGE = ["item_type.view", "item_type.edit", "item_type.manage"];

const A = "00000000-0000-7000-8000-00000000000a";
const B = "00000000-0000-7000-8000-00000000000b";
const C = "00000000-0000-7000-8000-00000000000c";

function contentType(id: string, key: string, sortOrder: number, showInNav: boolean): ContentTypeOut {
  return {
    id,
    key,
    name: `Type ${key}`,
    icon: "folder",
    isSystem: false,
    itemTypeCount: 0,
    showInNav,
    sortOrder,
    syncVersion: 1,
    createdAt: "2026-10-30T00:00:00Z",
    updatedAt: "2026-10-30T00:00:00Z",
  };
}

const THREE = [contentType(A, "a", 0, true), contentType(B, "b", 1, true), contentType(C, "c", 2, false)];
const list = (items = THREE) => http.get(api("/api/v1/content-types"), () => HttpResponse.json({ items }));

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

function bodyRows() {
  const table = screen.getByRole("table");
  return within(table)
    .getAllByRole("row")
    .filter((row) => within(row).queryAllByRole("columnheader").length === 0);
}

describe("content types register", () => {
  it("filters In navigation in memory and keeps the filter in the URL", async () => {
    server.use(list());
    const { router, container } = renderAt("/admin/content-types", MANAGE);
    await screen.findByText("Type c");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: t("item_types.filter.nav") }), "yes");
    await waitFor(() => expect(router.state.location.search).toEqual({ nav: "yes" }));
    await waitFor(() => expect(bodyRows()).toHaveLength(2));
    expect(screen.queryByText("Type c")).toBeNull();
    expect(await blocking(container)).toEqual([]);
  });

  it("moves a row down with PUT /content-types/order", async () => {
    const orders: unknown[] = [];
    server.use(
      list(),
      http.put(api("/api/v1/content-types/order"), async ({ request }) => {
        orders.push(await request.json());
        return HttpResponse.json({ items: THREE });
      }),
    );
    renderAt("/admin/content-types?nav=yes", MANAGE);
    await waitFor(() => expect(bodyRows()).toHaveLength(2));
    await userEvent.click(screen.getByRole("button", { name: t("item_types.content_type.move_down", { name: "Type a" }) }));
    await waitFor(() => expect(orders).toEqual([{ ids: [B, A, C] }]));
  });

  it("searches name or key", async () => {
    server.use(list());
    renderAt("/admin/content-types?q=type%20b", MANAGE);
    await waitFor(() => expect(bodyRows()).toHaveLength(1));
    expect(screen.getByText("Type b")).toBeTruthy();
  });

  it("shows no Create, Move or Delete controls with item_type.view only", async () => {
    server.use(list());
    renderAt("/admin/content-types", VIEW);
    await screen.findByText("Type a");
    expect(screen.queryByRole("button", { name: t("item_types.content_type.create") })).toBeNull();
    expect(screen.queryByRole("button", { name: t("item_types.content_type.move_down", { name: "Type a" }) })).toBeNull();
    expect(screen.queryByRole("button", { name: t("item_types.content_type.delete_named", { name: "Type a" }) })).toBeNull();
  });

  it("creates a content type and shows a taken key on the key field", async () => {
    const sent: unknown[] = [];
    server.use(
      list(),
      http.post(api("/api/v1/content-types"), async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json({ code: "CONTENT_TYPE_KEY_TAKEN" }, { status: 409 });
      }),
    );
    renderAt("/admin/content-types", MANAGE);
    await screen.findByText("Type a");
    await userEvent.click(screen.getAllByRole("button", { name: t("item_types.content_type.create") })[0]!);
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(t("item_types.content_type.field.key")), "a");
    await userEvent.type(within(dialog).getByLabelText(t("item_types.content_type.field.name")), "Again");
    await userEvent.click(within(dialog).getByRole("button", { name: t("item_types.content_type.create.submit") }));
    expect(await within(dialog).findByText(t("item_types.error.key_taken"))).toBeTruthy();
    expect(sent).toEqual([{ key: "a", name: "Again", icon: "folder", showInNav: true }]);
  });

  it("deletes after typing the key and reports a content type in use", async () => {
    server.use(
      list(),
      http.delete(api(`/api/v1/content-types/${A}`), () =>
        HttpResponse.json({ code: "CONTENT_TYPE_IN_USE", categories: 2 }, { status: 409 }),
      ),
    );
    renderAt("/admin/content-types", MANAGE);
    await userEvent.click(await screen.findByRole("button", { name: t("item_types.content_type.delete_named", { name: "Type a" }) }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox"), "a");
    await userEvent.click(within(dialog).getByRole("button", { name: t("item_types.content_type.delete.submit") }));
    expect(await screen.findByText(t("item_types.content_type.delete.in_use", { count: 2 }))).toBeTruthy();
  });

  it("validateSearch keeps the nav filter and drops unknown values", () => {
    expect(validateContentTypesSearch({ nav: "yes", junk: "1" })).toEqual({ nav: "yes" });
    expect(validateContentTypesSearch({ nav: "maybe" })).toEqual({});
  });
});

describe("content type detail", () => {
  const category: CategoryOut = {
    id: "00000000-0000-7000-8000-0000000000a1",
    contentTypeId: A,
    key: "piping",
    name: "Piping",
    applicableFor: "item",
    sortOrder: 0,
    syncVersion: 1,
    createdAt: "2026-10-30T00:00:00Z",
    updatedAt: "2026-10-30T00:00:00Z",
  };
  const item: ItemTypeOut = {
    id: "00000000-0000-7000-8000-0000000000b1",
    contentTypeId: A,
    categoryId: category.id,
    key: "pipe_spool",
    name: "Pipe spool",
    description: null,
    isComponent: false,
    allowsComponents: false,
    draftVersionId: null,
    publishedVersion: 2,
    publishedVersionId: null,
    syncVersion: 1,
    createdAt: "2026-10-30T00:00:00Z",
    updatedAt: "2026-10-30T00:00:00Z",
  };
  const detail = () => [
    http.get(api(`/api/v1/content-types/${A}`), () => HttpResponse.json(THREE[0])),
    http.get(api("/api/v1/item-categories"), () => HttpResponse.json({ items: [category] })),
    http.get(api("/api/v1/item-types"), () => HttpResponse.json({ items: [item] })),
  ];

  it("has no axe violations on each tab, with the tab in the URL", async () => {
    server.use(...detail());
    const { container, router } = renderAt(`/admin/content-types/${A}`, MANAGE);
    expect(await screen.findByRole("heading", { level: 1, name: "Type a" })).toBeTruthy();
    expect(await blocking(container)).toEqual([]);

    await userEvent.click(screen.getByRole("tab", { name: t("item_types.tab.categories") }));
    await waitFor(() => expect(router.state.location.search).toEqual({ tab: "categories" }));
    expect(await screen.findByText("Piping")).toBeTruthy();
    expect(screen.getByText(t("item_types.applicable_for.item"))).toBeTruthy();
    expect(await blocking(container)).toEqual([]);

    await userEvent.click(screen.getByRole("tab", { name: t("item_types.tab.item_types") }));
    expect(await screen.findByRole("link", { name: "Pipe spool" })).toBeTruthy();
    expect(screen.getByText("Published v2")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);
  });

  it("shows the definition read-only without item_type.manage", async () => {
    server.use(...detail());
    renderAt(`/admin/content-types/${A}?tab=details`, VIEW);
    await screen.findByRole("heading", { level: 1, name: "Type a" });
    expect(screen.queryByRole("button", { name: t("item_types.action.save") })).toBeNull();
  });

  it("shows the changed-by-someone-else state on a version conflict", async () => {
    server.use(
      ...detail(),
      http.patch(api(`/api/v1/content-types/${A}`), () => HttpResponse.json({ code: "VERSION_CONFLICT" }, { status: 409 })),
    );
    renderAt(`/admin/content-types/${A}`, MANAGE);
    await screen.findByRole("heading", { level: 1, name: "Type a" });
    await userEvent.click(screen.getByRole("button", { name: t("item_types.action.save") }));
    expect(await screen.findByText(t("ui.error.conflict"))).toBeTruthy();
  });

  it("shows the not-found state for another tenant's content type", async () => {
    server.use(http.get(api(`/api/v1/content-types/${A}`), () => HttpResponse.json({ code: "NOT_FOUND" }, { status: 404 })));
    renderAt(`/admin/content-types/${A}`, MANAGE);
    expect(await screen.findByText("Not found")).toBeTruthy();
  });
});
