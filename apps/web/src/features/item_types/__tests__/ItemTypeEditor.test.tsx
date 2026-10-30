import type { ItemTypeOut, ItemTypeVersionOut } from "@aip/api-client";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { t } from "../../shell/t";

const CT = "00000000-0000-7000-8000-0000000000c1";
const CAT = "00000000-0000-7000-8000-0000000000a1";
const IT = "00000000-0000-7000-8000-0000000000b1";
const DRAFT = "00000000-0000-7000-8000-0000000000d1";

const VIEW = ["item_type.view"];
const EDIT = ["item_type.view", "item_type.edit"];
const ALL = ["item_type.view", "item_type.edit", "item_type.manage", "item_type.publish"];

const ATTRS = [{ key: "wall_thickness", label: "Wall thickness", fieldType: "measurement", config: { unit: "in" } }];

function itemType(overrides: Partial<ItemTypeOut> = {}): ItemTypeOut {
  return {
    id: IT,
    contentTypeId: CT,
    categoryId: CAT,
    key: "pipe_spool",
    name: "Pipe spool",
    description: null,
    isComponent: false,
    allowsComponents: false,
    draftVersionId: DRAFT,
    publishedVersion: null,
    publishedVersionId: null,
    syncVersion: 1,
    createdAt: "2026-10-30T00:00:00Z",
    updatedAt: "2026-10-30T00:00:00Z",
    ...overrides,
  };
}

function version(overrides: Partial<ItemTypeVersionOut> = {}): ItemTypeVersionOut {
  return {
    id: DRAFT,
    itemTypeId: IT,
    version: 1,
    status: "draft",
    attributes: ATTRS,
    compiledSchema: null,
    changeSummary: null,
    createdAt: "2026-10-30T00:00:00Z",
    createdBy: null,
    publishedAt: null,
    publishedBy: null,
    syncVersion: 1,
    updatedAt: "2026-10-30T00:00:00Z",
    ...overrides,
  };
}

function base(item: ItemTypeOut = itemType()) {
  return [
    http.get(api(`/api/v1/item-types/${IT}`), () => HttpResponse.json(item)),
    http.get(api(`/api/v1/content-types/${CT}`), () =>
      HttpResponse.json({
        id: CT,
        key: "piping",
        name: "Piping",
        icon: "folder",
        isSystem: false,
        itemTypeCount: 1,
        showInNav: true,
        sortOrder: 0,
        syncVersion: 1,
        createdAt: "2026-10-30T00:00:00Z",
        updatedAt: "2026-10-30T00:00:00Z",
      }),
    ),
    http.get(api("/api/v1/item-categories"), () => HttpResponse.json({ items: [] })),
    http.get(api(`/api/v1/item-types/${IT}/versions/${DRAFT}`), () => HttpResponse.json(version())),
    http.get(api(`/api/v1/item-types/${IT}/versions`), () => HttpResponse.json({ items: [] })),
  ];
}

const SCHEMA = `/admin/content-types/${CT}/item-types/${IT}?tab=schema`;

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

async function editor() {
  return (await screen.findByRole("textbox", { name: t("item_types.editor.label") })) as HTMLTextAreaElement;
}

describe("item type editor", () => {
  it("lists the server's ATTRIBUTES_INVALID issues under the editor and keeps the text", async () => {
    const sent: unknown[] = [];
    server.use(
      ...base(),
      http.patch(api(`/api/v1/item-types/${IT}/versions/${DRAFT}`), async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(
          { code: "ATTRIBUTES_INVALID", issues: [{ path: "attributes[0].config", code: "ATTRIBUTE_CONFIG_INVALID" }] },
          { status: 422 },
        );
      }),
    );
    const { container } = renderAt(SCHEMA, ALL);
    const area = await editor();
    await waitFor(() => expect(area.value).toContain('"unit": "in"'));
    // Edit the text so it differs from the server's copy.
    fireEvent.change(area, { target: { value: area.value.replace('"in"', '"inch"') } });
    await userEvent.click(screen.getByRole("button", { name: t("item_types.editor.save_draft") }));

    const issues = await screen.findByRole("alert", { name: t("item_types.editor.issues") });
    expect(within(issues).getByText(t("item_types.issue.attribute_config_invalid"))).toBeTruthy();
    expect(within(issues).getByText("attributes[0].config")).toBeTruthy();
    expect(area.value).toContain('"unit": "inch"');
    expect((sent[0] as { syncVersion: number }).syncVersion).toBe(1);

    // Selecting the issue puts the caret on the attribute.
    await userEvent.click(within(issues).getByRole("button"));
    expect(document.activeElement).toBe(area);
    expect(area.value.slice(area.selectionStart, area.selectionStart + 1)).toBe("{");

    expect(await blocking(container)).toEqual([]);
  });

  it("previews the current text, and the last valid text with the parse error when it breaks", async () => {
    server.use(...base());
    renderAt(SCHEMA, ALL);
    const area = await editor();
    await waitFor(() => expect(screen.getByText("Wall thickness")).toBeTruthy());
    fireEvent.change(area, { target: { value: '[{"key":"material","label":"Material","fieldType":"text"}]' } });
    expect(await screen.findByText("Material")).toBeTruthy();
    fireEvent.change(area, { target: { value: '[{"key":"material",' } });
    expect(await screen.findByText(/line 1, column/)).toBeTruthy();
    expect(screen.getByText("Material")).toBeTruthy();
  });

  it("shows no Save draft, Create draft or Publish with item_type.view only", async () => {
    server.use(...base());
    renderAt(SCHEMA, VIEW);
    const area = await editor();
    expect(area.readOnly).toBe(true);
    for (const key of ["item_types.editor.save_draft", "item_types.editor.create_draft", "item_types.editor.publish"]) {
      expect(screen.queryByRole("button", { name: t(key) })).toBeNull();
    }
  });

  it("shows Save draft but no Publish with item_type.edit and no item_type.publish", async () => {
    server.use(...base());
    renderAt(SCHEMA, EDIT);
    await editor();
    expect(await screen.findByRole("button", { name: t("item_types.editor.save_draft") })).toBeTruthy();
    expect(screen.queryByRole("button", { name: t("item_types.editor.publish") })).toBeNull();
  });

  it("offers Create draft without a draft, showing the published attributes read-only", async () => {
    const PUB = "00000000-0000-7000-8000-0000000000e1";
    const created: string[] = [];
    server.use(
      ...base(itemType({ draftVersionId: null, publishedVersion: 1, publishedVersionId: PUB })),
      http.get(api(`/api/v1/item-types/${IT}/versions/${PUB}`), () =>
        HttpResponse.json(version({ id: PUB, status: "published", attributes: [{ key: "a", label: "Published A", fieldType: "text" }] })),
      ),
      http.post(api(`/api/v1/item-types/${IT}/versions`), () => {
        created.push("draft");
        return HttpResponse.json(version({ version: 2 }), { status: 201 });
      }),
    );
    const { container } = renderAt(SCHEMA, ALL);
    const area = await editor();
    await waitFor(() => expect(area.value).toContain("Published A"));
    expect(area.readOnly).toBe(true);
    expect(screen.getByText("Published v1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: t("item_types.editor.save_draft") })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: t("item_types.editor.create_draft") }));
    await waitFor(() => expect(created).toEqual(["draft"]));
    expect(await blocking(container)).toEqual([]);
  });

  it("publishes the draft with a change summary", async () => {
    const published: unknown[] = [];
    server.use(
      ...base(),
      http.post(api(`/api/v1/item-types/${IT}/versions/${DRAFT}/publish`), async ({ request }) => {
        published.push(await request.json());
        return HttpResponse.json(version({ status: "published" }));
      }),
    );
    renderAt(SCHEMA, ALL);
    await editor();
    await userEvent.click(await screen.findByRole("button", { name: t("item_types.editor.publish") }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText(t("item_types.editor.publish.summary")), "first");
    await userEvent.click(within(dialog).getByRole("button", { name: t("item_types.editor.publish.submit") }));
    await waitFor(() => expect(published).toEqual([{ syncVersion: 1, changeSummary: "first" }]));
  });

  it("asks before leaving the Schema tab with unsaved text", async () => {
    server.use(...base());
    const { router } = renderAt(SCHEMA, ALL);
    const area = await editor();
    await waitFor(() => expect(area.value).toContain("wall_thickness"));
    fireEvent.change(area, { target: { value: "[]" } });
    await userEvent.click(screen.getByRole("tab", { name: t("item_types.tab.versions") }));
    const dialog = await screen.findByRole("dialog", { name: t("item_types.editor.leave.title") });
    await userEvent.click(within(dialog).getByRole("button", { name: t("item_types.editor.leave.submit") }));
    await waitFor(() => expect(router.state.location.search).toEqual({ tab: "versions" }));
  });

  it("shows the not-found state for another tenant's or a missing item type", async () => {
    server.use(
      http.get(api(`/api/v1/item-types/${IT}`), () => HttpResponse.json({ code: "NOT_FOUND" }, { status: 404 })),
      http.get(api(`/api/v1/content-types/${CT}`), () => HttpResponse.json({ code: "NOT_FOUND" }, { status: 404 })),
    );
    renderAt(SCHEMA, ALL);
    expect(await screen.findByText("Not found")).toBeTruthy();
  });

  it("lists versions with their local publish time and previews the chosen one", async () => {
    // MSW tries handlers in order: the versions list goes before base()'s empty one.
    server.use(
      http.get(api(`/api/v1/item-types/${IT}/versions`), () =>
        HttpResponse.json({
          items: [
            {
              ...version({ status: "published", publishedAt: "2026-10-30T02:00:00Z", publishedBy: "u1", changeSummary: "first" }),
              attributes: [{ key: "a", label: "Version one A", fieldType: "text" }],
            },
          ],
        }),
      ),
      ...base(itemType({ draftVersionId: null, publishedVersion: 1, publishedVersionId: DRAFT })),
    );
    const { container } = renderAt(`/admin/content-types/${CT}/item-types/${IT}?tab=versions`, VIEW);
    expect(await screen.findByText("first")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "v1" }));
    expect(await screen.findByText("Version one A")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);
  });
});
