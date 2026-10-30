import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, asset, assetsApi, blocking, itemType, itemTypesApi, renderAt, resolveRelativeFetch, restoreFetch, server, version } from "./helpers";

const CREATE = ["asset.view", "asset.create", "item_type.view"];
const UPDATE = ["asset.view", "asset.update", "item_type.view"];

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

const pump = itemType({ name: "Pump" });
const pumpV1 = version(pump, [
  { key: "diameter_mm", label: "Diameter", fieldType: "number", required: true },
  {
    key: "service",
    label: "Service",
    fieldType: "dropdown",
    config: {
      options: [
        { value: "water", label: "Water" },
        { value: "steam", label: "Steam" },
      ],
    },
  },
  { key: "photo", label: "Nameplate photo", fieldType: "photo" },
]);
const site = asset({ name: "Site A", childCount: 1 });
const existing = asset({ name: "P-101", tagNumber: "P-101", parentId: site.id });
const ALL = [site, existing];

async function chooseItemType(name: string) {
  await userEvent.click(screen.getByRole("combobox", { name: "Item type" }));
  await userEvent.click(await screen.findByRole("option", { name }));
}

describe("asset form", () => {
  it("generates the attribute inputs from the item type's published version", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump], [pumpV1]));
    const { container } = renderAt("/assets/new", CREATE);
    await screen.findByRole("heading", { name: "Create asset" });
    await chooseItemType("Pump");

    const diameter = await screen.findByLabelText("Diameter (required)");
    expect(diameter.getAttribute("type")).toBe("number");
    const service = screen.getByLabelText("Service");
    expect(service.tagName).toBe("SELECT");
    expect(within(service).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose…", "Water", "Steam"]);
    expect(screen.getByText("Edit this on the asset page.")).toBeTruthy(); // photo: read-only note
    expect(await blocking(container)).toEqual([]);
  });

  it("puts a 422 attribute error under its field", async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      ...assetsApi(ALL),
      ...itemTypesApi([pump], [pumpV1]),
      http.post(api("/api/v1/assets"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { code: "ATTRIBUTES_INVALID", field: "attributes", errors: [{ path: "attributes.diameter_mm", code: "required" }] },
          { status: 422 },
        );
      }),
    );
    renderAt("/assets/new", CREATE);
    await screen.findByRole("heading", { name: "Create asset" });
    await userEvent.type(screen.getByLabelText("Name (required)"), "New pump");
    await chooseItemType("Pump");
    await userEvent.selectOptions(await screen.findByLabelText("Service"), "steam");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    const diameter = await screen.findByLabelText("Diameter (required)");
    await waitFor(() => expect(diameter.getAttribute("aria-invalid")).toBe("true"));
    const errorId = diameter.getAttribute("aria-describedby")?.split(" ").find((d) => d.endsWith("-error"));
    expect(document.getElementById(errorId!)?.textContent).toBe("This field is required.");
    expect(body).toEqual({ name: "New pump", tagNumber: null, parentId: null, itemTypeId: pump.id, attributes: { service: "steam" } });
  });

  it("checks the Tag Number as the user types", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump], [pumpV1]));
    renderAt(`/assets/new?parentId=${site.id}`, CREATE);
    await screen.findByRole("heading", { name: "Create asset" });
    await waitFor(() => expect((screen.getByRole("combobox", { name: "Parent" }) as HTMLInputElement).value).toBe("Site A"));
    await userEvent.type(screen.getByLabelText("Tag Number"), "p-101");
    expect(await screen.findByText(`Already used by P-101 (${existing.internalTag})`)).toBeTruthy();
  });

  it("does not flag the asset's own Tag Number when editing, and shows a reload on a conflict", async () => {
    server.use(
      ...assetsApi(ALL),
      ...itemTypesApi([pump], [pumpV1]),
      http.patch(api("/api/v1/assets/:assetId"), () => HttpResponse.json({ code: "VERSION_CONFLICT", current: existing }, { status: 409 })),
    );
    renderAt(`/assets/${existing.id}/edit`, UPDATE);
    await screen.findByRole("heading", { name: "Edit P-101" });
    expect((screen.getByLabelText("Tag Number") as HTMLInputElement).value).toBe("P-101");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("button", { name: "Reload" })).toBeTruthy();
    expect(screen.queryByText(/Already used by/)).toBeNull();
  });

  it("shows the not-found state for an asset the API does not return", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump], [pumpV1]));
    renderAt("/assets/00000000-0000-7000-8000-ffffffffffff/edit", UPDATE);
    expect(await screen.findByText("Not found")).toBeTruthy();
  });

  it("without asset.create the create form is replaced by the permission notice", async () => {
    server.use(...assetsApi(ALL), ...itemTypesApi([pump], [pumpV1]));
    renderAt("/assets/new", ["asset.view"]);
    expect(await screen.findByRole("heading", { name: "You do not have permission to create assets." })).toBeTruthy();
  });
});
