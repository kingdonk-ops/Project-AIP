import type { SiteOut } from "@aip/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "./helpers";

const VIEW = ["site.view"];
const MANAGE = ["site.view", "site.manage"];

function site(overrides: Partial<SiteOut> & Pick<SiteOut, "code">): SiteOut {
  return {
    id: crypto.randomUUID(),
    name: `Site ${overrides.code}`,
    lat: null,
    lng: null,
    timezone: "Australia/Perth",
    isSystem: false,
    createdAt: "2026-10-13T00:00:00Z",
    updatedAt: "2026-10-13T01:00:00Z",
    ...overrides,
  };
}

function listSites(items: SiteOut[]) {
  return http.get(api("/api/v1/sites"), () => HttpResponse.json({ items, nextCursor: null }));
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

describe("sites register", () => {
  it("lists sites; Create and row actions need site.manage", async () => {
    server.use(listSites([site({ code: "PERTH-01" })]));
    const { container } = renderAt("/sites", VIEW);
    await screen.findByText("PERTH-01");
    expect(screen.queryByRole("button", { name: "Create site" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    expect(await blocking(container)).toEqual([]);
  });

  it("creates a site through the dialog", async () => {
    const created: unknown[] = [];
    server.use(
      listSites([site({ code: "PERTH-01" })]),
      http.post(api("/api/v1/sites"), async ({ request }) => {
        created.push(await request.json());
        return HttpResponse.json(site({ code: "KWINANA" }), { status: 201 });
      }),
    );
    const { container } = renderAt("/sites", MANAGE);
    await screen.findByText("PERTH-01");
    await userEvent.click(screen.getByRole("button", { name: "Create site" }));

    const dialog = await screen.findByRole("dialog", { name: "Create site" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Site code" }), "KWINANA");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Name" }), "Kwinana yard");
    expect(await blocking(container)).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText("Site KWINANA was created.")).toBeTruthy());
    expect((created[0] as Record<string, unknown>).code).toBe("KWINANA");
  });

  it("edits a site through the dialog", async () => {
    const target = site({ code: "PERTH-01" });
    const patched: unknown[] = [];
    server.use(
      listSites([target]),
      http.patch(api(`/api/v1/sites/${target.id}`), async ({ request }) => {
        patched.push(await request.json());
        return HttpResponse.json({ ...target, name: "Perth depot" });
      }),
    );
    renderAt("/sites", MANAGE);
    const row = (await screen.findByText("PERTH-01")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "Edit" }));

    const dialog = await screen.findByRole("dialog", { name: "Edit site" });
    const name = within(dialog).getByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Perth depot");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText("Site PERTH-01 was saved.")).toBeTruthy());
    expect((patched[0] as Record<string, unknown>).name).toBe("Perth depot");
  });

  it("deletes a site after confirmation", async () => {
    const target = site({ code: "PERTH-01" });
    let deleted = false;
    server.use(
      listSites([target]),
      http.delete(api(`/api/v1/sites/${target.id}`), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt("/sites", MANAGE);
    const row = (await screen.findByText("PERTH-01")).closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "Delete" }));

    const dialog = await screen.findByRole("dialog", { name: "Delete PERTH-01?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.getByText("Site PERTH-01 was deleted.")).toBeTruthy());
    expect(deleted).toBe(true);
  });

  it("does not offer edit or delete for a system site", async () => {
    server.use(listSites([site({ code: "SYS-01", isSystem: true })]));
    renderAt("/sites", MANAGE);
    const row = (await screen.findByText("SYS-01")).closest("tr")!;
    expect(within(row).queryByRole("button", { name: "Edit" })).toBeNull();
    expect(within(row).queryByRole("button", { name: "Delete" })).toBeNull();
  });
});
