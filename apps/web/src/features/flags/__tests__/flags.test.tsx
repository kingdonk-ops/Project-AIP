import { getPlatformListFlagsQueryKey, type FeatureFlag } from "@aip/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";

const MANAGE = ["tenant.flags.manage"];

/** A stateful flags API: GET returns the current values, PUT changes one and records the call. */
function flagsApi(initial: Record<string, boolean>, putStatus = 200) {
  const values = { ...initial };
  const puts: { flag: string; enabled: boolean }[] = [];
  const list = (): FeatureFlag[] => Object.entries(values).map(([flag, enabled]) => ({ flag, enabled }));
  server.use(
    http.get(api("/api/v1/settings/flags"), () => HttpResponse.json({ flags: list() })),
    http.put(api("/api/v1/settings/flags/:flag"), async ({ params, request }) => {
      const flag = String(params.flag);
      const { enabled } = (await request.json()) as { enabled: boolean };
      puts.push({ flag, enabled });
      if (putStatus !== 200) return HttpResponse.json({ detail: "forbidden" }, { status: putStatus });
      values[flag] = enabled;
      return HttpResponse.json({ flag, enabled });
    }),
  );
  return { puts };
}

function nav() {
  return screen.getByRole("navigation", { name: "Main navigation" });
}

/** The rail, once the shell has rendered. */
function shellNav() {
  return screen.findByRole("navigation", { name: "Main navigation" });
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

describe("flag-gated nav items", () => {
  it("does not render a nav item whose flag is off", async () => {
    flagsApi({ ai: false, bim: false });
    const { queryClient } = renderAt("/", []);
    expect(await screen.findByRole("link", { name: "Home" })).toBeTruthy();
    // The flags have loaded, so the absence is the flag's doing and not a pending request.
    await waitFor(() => expect(queryClient.getQueryState(getPlatformListFlagsQueryKey())?.status).toBe("success"));
    expect(within(nav()).queryByRole("link", { name: "BIM models (preview)" })).toBeNull();
  });

  it("renders it when the tenant's flag is on", async () => {
    flagsApi({ ai: false, bim: true });
    renderAt("/", []);
    expect(await within(await shellNav()).findByRole("link", { name: "BIM models (preview)" })).toBeTruthy();
  });
});

describe("release flags page", () => {
  it("is in the Settings menu only with tenant.flags.manage", async () => {
    flagsApi({ ai: false, bim: false });
    renderAt("/", MANAGE);
    expect(await within(await shellNav()).findByRole("link", { name: "Release flags" })).toBeTruthy();
  });

  it("shows a user without the permission the 403 state, no menu entry and no switches", async () => {
    flagsApi({ ai: false, bim: false });
    const { container } = renderAt("/settings/flags", ["project.view"]);
    expect(await screen.findByRole("heading", { name: "Release flags", level: 1 })).toBeTruthy();
    expect(screen.getByText("You don’t have access")).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(within(nav()).queryByRole("link", { name: "Release flags" })).toBeNull();
    expect(await blocking(container)).toEqual([]);
  });

  it("lets an admin switch bim on, and the gated nav item appears without a reload", async () => {
    const { puts } = flagsApi({ ai: false, bim: false });
    const { container } = renderAt("/settings/flags", MANAGE);
    const bim = await screen.findByRole("checkbox", { name: "BIM models" });
    expect(bim.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByRole("checkbox", { name: "AI assistant" })).toBeTruthy();
    expect(await blocking(container)).toEqual([]);

    await userEvent.click(bim);
    await waitFor(() => expect(bim.getAttribute("aria-checked")).toBe("true"));
    expect(puts).toEqual([{ flag: "bim", enabled: true }]);
    expect(await within(nav()).findByRole("link", { name: "BIM models (preview)" })).toBeTruthy();
    expect(await screen.findByText("BIM models is now on.")).toBeTruthy();
  });

  it("keeps the switch as it was and says so when the API refuses the change", async () => {
    flagsApi({ ai: false, bim: false }, 403);
    renderAt("/settings/flags", MANAGE);
    const bim = await screen.findByRole("checkbox", { name: "BIM models" });
    await userEvent.click(bim);
    expect(await screen.findByText("The flag could not be changed. Try again.")).toBeTruthy();
    expect(bim.getAttribute("aria-checked")).toBe("false");
    expect(within(nav()).queryByRole("link", { name: "BIM models (preview)" })).toBeNull();
  });
});
