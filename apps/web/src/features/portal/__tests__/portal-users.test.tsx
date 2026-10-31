import type { GrantOut, PortalUserOut, ProjectOut } from "@aip/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { PENDING_KEY } from "../../identity/step-up";
import { api, blocking, project, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { INVITE_STEP_UP_KEY } from "../InviteForm";
import { DETAIL_STEP_UP_KEY } from "../PortalUserDetail";
import { toListParams, validatePortalUsersSearch, portalUsersQuery } from "../search";

const VIEW = ["portal.user.view"];
const ADMIN = ["portal.user.view", "portal.user.invite", "portal.user.suspend", "portal.grant.manage"];
const DAY = 24 * 60 * 60 * 1000;
const USERS = "/api/v1/admin/portal/users";

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
beforeEach(() => window.sessionStorage.clear());
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

const P1 = project({ code: "KF-01", status: "active", name: "Karratha compressor station" });
const P2 = project({ code: "PL-07", status: "active", name: "Pilbara gas plant" });
const CLOSED = project({ code: "OLD-1", status: "archived", name: "Closed job" });

let next = 0;
const id = () => `00000000-0000-7000-8000-${String((next += 1)).padStart(12, "0")}`;
const inDays = (days: number) => new Date(Date.now() + days * DAY).toISOString();

function grant(overrides: Partial<GrantOut> = {}): GrantOut {
  return {
    id: id(),
    projectId: P1.id,
    assetId: null,
    actions: ["view", "sign_off"],
    accessDays: 180,
    expiresAt: inDays(120),
    state: "live",
    renewedAt: null,
    renewedBy: null,
    revokedAt: null,
    revokedReason: null,
    createdBy: "00000000-0000-4000-8000-0000000000a1",
    createdAt: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

function portalUser(overrides: Partial<PortalUserOut> = {}): PortalUserOut {
  return {
    id: id(),
    userId: id(),
    email: "client.a@rio.example",
    companyName: "Rio Example Pty Ltd",
    organisationId: null,
    status: "active",
    effectiveStatus: "active",
    invitedBy: "00000000-0000-4000-8000-0000000000a1",
    firstSignedInAt: "2026-10-02T00:00:00Z",
    suspendedAt: null,
    suspendedReason: null,
    expiresAt: null,
    grants: [grant()],
    syncVersion: 1,
    createdAt: "2026-10-01T00:00:00Z",
    updatedAt: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

function lookups(projects: ProjectOut[] = [P1, P2, CLOSED]) {
  return [
    http.get(api("/api/v1/projects"), () => HttpResponse.json({ items: projects, nextCursor: null })),
    http.get(api("/api/v1/assets"), () => HttpResponse.json({ items: [], nextCursor: null })),
  ];
}

function listUsers(items: PortalUserOut[], seen?: URL[]) {
  return http.get(api(USERS), ({ request }) => {
    seen?.push(new URL(request.url));
    return HttpResponse.json({ items, nextCursor: null });
  });
}

function getUser(user: PortalUserOut) {
  return http.get(api(`${USERS}/${user.id}`), () => HttpResponse.json(user));
}

describe("external users register", () => {
  it("lists users with status, project count and the next expiry, flagging one that ends soon", async () => {
    const soon = portalUser({ grants: [grant({ expiresAt: inDays(5) }), grant({ projectId: P2.id, expiresAt: inDays(100) })] });
    const invited = portalUser({ email: "new@bhp.example", companyName: "BHP Example", status: "invited", effectiveStatus: "invited", firstSignedInAt: null });
    const expired = portalUser({ email: "old@fmg.example", effectiveStatus: "expired", grants: [grant({ state: "expired", expiresAt: inDays(-1) })] });
    server.use(...lookups(), listUsers([soon, invited, expired]));
    const { container } = renderAt("/admin/portal/users", ADMIN);

    expect(await screen.findByRole("heading", { level: 1, name: "External users" })).toBeTruthy();
    await screen.findByText("Rio Example Pty Ltd");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);

    expect(within(rows[0]!).getByRole("link", { name: "client.a@rio.example" }).getAttribute("href")).toBe(`/admin/portal/users/${soon.id}`);
    expect(within(rows[0]!).getByText("Active")).toBeTruthy();
    expect(within(rows[0]!).getByText("2")).toBeTruthy();
    expect(within(rows[0]!).getByText("Expiring soon")).toBeTruthy();
    expect(within(rows[1]!).getByText("Invited")).toBeTruthy();
    expect(within(rows[1]!).queryByText("Expiring soon")).toBeNull();
    expect(within(rows[2]!).getByText("Access expired")).toBeTruthy();
    expect(within(rows[2]!).getByText("No current access")).toBeTruthy();

    expect(screen.getByRole("link", { name: "Invite external user" }).getAttribute("href")).toBe("/admin/portal/users/new");
    expect(await blocking(container)).toEqual([]);
  });

  it("keeps the expiring and status filters and the search in the URL and sends them to the API", async () => {
    const seen: URL[] = [];
    server.use(...lookups(), listUsers([portalUser()], seen));
    const { router } = renderAt("/admin/portal/users", VIEW);
    await screen.findByRole("table");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Expiring within" }), "30");
    await waitFor(() => expect(router.state.location.search).toEqual({ expiring: "30" }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.get("expiringWithinDays")).toBe("30"));

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Status" }), "active");
    await waitFor(() => expect(seen.at(-1)?.searchParams.get("status")).toBe("active"));

    await userEvent.type(screen.getByRole("searchbox", { name: "Search email or company" }), "rio");
    await waitFor(() => expect(seen.at(-1)?.searchParams.get("q")).toBe("rio"));
    expect(router.state.location.search).toEqual({ expiring: "30", status: "active", q: "rio" });
  });

  it("hides the invite link without portal.user.invite, and the nav item without portal.user.view", async () => {
    server.use(...lookups(), listUsers([]));
    const viewer = renderAt("/admin/portal/users", VIEW);
    expect(await screen.findByText("No external users have been invited yet.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Invite external user" })).toBeNull();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByRole("link", { name: "External users" }).getAttribute("href")).toBe("/admin/portal/users");
    viewer.unmount();

    const empty = () => HttpResponse.json({ items: [], nextCursor: null });
    server.use(http.get(api("/api/v1/sites"), empty));
    renderAt("/projects", ["project.view"]);
    const other = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(within(other).queryByRole("link", { name: "External users" })).toBeNull();
  });

  it("shows the error with the request id when the API refuses the list", async () => {
    server.use(
      ...lookups(),
      http.get(api(USERS), () => HttpResponse.json({ code: "FORBIDDEN" }, { status: 403, headers: { "x-request-id": "req-9" } })),
    );
    renderAt("/admin/portal/users", []);
    expect(await screen.findByText("The external users could not be loaded.")).toBeTruthy();
    expect(screen.getByText("Reference: req-9")).toBeTruthy();
  });
});

describe("invite form", () => {
  async function fillIdentity() {
    await userEvent.type(screen.getByLabelText("Email"), "client.b@rio.example");
    await userEvent.type(screen.getByLabelText("First name"), "Client");
    await userEvent.type(screen.getByLabelText("Last name"), "B");
    await userEvent.type(screen.getByLabelText("Company"), "Rio Example Pty Ltd");
  }

  it("sends the grants built, with view always on and no expiry, then opens the new user", async () => {
    const bodies: unknown[] = [];
    const created = portalUser({ status: "invited", effectiveStatus: "invited" });
    server.use(
      ...lookups(),
      getUser(created),
      http.post(api(USERS), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    const { router, container } = renderAt("/admin/portal/users/new", ADMIN);
    await screen.findByRole("heading", { level: 1, name: "Invite external user" });
    await fillIdentity();

    const first = screen.getByRole("group", { name: "Access 1" });
    const select = within(first).getByRole("combobox", { name: "Project" });
    await waitFor(() => expect(within(select).getAllByRole("option")).toHaveLength(3)); // closed project not offered
    await userEvent.selectOptions(select, P1.id);
    expect((within(first).getByRole("checkbox", { name: "View records" }) as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(within(first).getByRole("checkbox", { name: "Sign off" }));

    await userEvent.click(screen.getByRole("button", { name: "Add project access" }));
    const second = screen.getByRole("group", { name: "Access 2" });
    await userEvent.selectOptions(within(second).getByRole("combobox", { name: "Project" }), P2.id);
    await userEvent.click(within(second).getByRole("checkbox", { name: "Download reports" }));
    expect(await blocking(container)).toEqual([]);

    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/admin/portal/users/${created.id}`));
    expect(bodies).toEqual([
      {
        email: "client.b@rio.example",
        firstName: "Client",
        lastName: "B",
        companyName: "Rio Example Pty Ltd",
        grants: [
          { projectId: P1.id, actions: ["view", "sign_off"] },
          { projectId: P2.id, actions: ["view", "download"] },
        ],
      },
    ]);
  });

  it("checks the form before sending: a missing project stays on its row", async () => {
    let calls = 0;
    server.use(...lookups(), http.post(api(USERS), () => HttpResponse.json({}, { status: 201, headers: { x: String((calls += 1)) } })));
    renderAt("/admin/portal/users/new", ADMIN);
    await screen.findByRole("heading", { level: 1, name: "Invite external user" });
    await fillIdentity();
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await within(screen.getByRole("group", { name: "Access 1" })).findByText("Choose an open project.")).toBeTruthy();
    expect(calls).toBe(0);
  });

  it("puts PROJECT_CLOSED on the grant row it names, and USER_EXISTS on email", async () => {
    let answer: { status: number; body: object } = { status: 422, body: { code: "PROJECT_CLOSED", projectId: P2.id } };
    server.use(...lookups(), http.post(api(USERS), () => HttpResponse.json(answer.body, { status: answer.status })));
    renderAt("/admin/portal/users/new", ADMIN);
    await screen.findByRole("heading", { level: 1, name: "Invite external user" });
    await fillIdentity();
    const first = screen.getByRole("group", { name: "Access 1" });
    await waitFor(() => expect(within(within(first).getByRole("combobox", { name: "Project" })).getAllByRole("option")).toHaveLength(3));
    await userEvent.selectOptions(within(first).getByRole("combobox", { name: "Project" }), P1.id);
    await userEvent.click(screen.getByRole("button", { name: "Add project access" }));
    await userEvent.selectOptions(within(screen.getByRole("group", { name: "Access 2" })).getByRole("combobox", { name: "Project" }), P2.id);

    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    const closed = "This project is closed, so client access cannot be given or renewed.";
    expect(await within(screen.getByRole("group", { name: "Access 2" })).findByText(closed)).toBeTruthy();
    expect(within(first).queryByText(closed)).toBeNull();

    answer = { status: 409, body: { code: "USER_EXISTS" } };
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("This person already has an account.")).toBeTruthy();
    expect(screen.getByLabelText("Email").getAttribute("aria-invalid")).toBe("true");
  });

  it("keeps the form across a step-up and offers to send it again on return", async () => {
    server.use(
      ...lookups(),
      http.post(api(USERS), () =>
        HttpResponse.json({ detail: { code: "STEP_UP_REQUIRED", stepUpUrl: "/api/v1/auth/step-up/start" } }, { status: 401 }),
      ),
    );
    const first = renderAt("/admin/portal/users/new", ADMIN);
    await screen.findByRole("heading", { level: 1, name: "Invite external user" });
    await fillIdentity();
    const row = screen.getByRole("group", { name: "Access 1" });
    await waitFor(() => expect(within(within(row).getByRole("combobox", { name: "Project" })).getAllByRole("option")).toHaveLength(3));
    await userEvent.selectOptions(within(row).getByRole("combobox", { name: "Project" }), P1.id);
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));

    await waitFor(() => expect(window.sessionStorage.getItem(PENDING_KEY)).not.toBeNull());
    const saved = JSON.parse(window.sessionStorage.getItem(PENDING_KEY)!) as { key: string; state: { email: string } };
    expect(saved.key).toBe(INVITE_STEP_UP_KEY);
    expect(saved.state.email).toBe("client.b@rio.example");
    first.unmount();

    renderAt("/admin/portal/users/new", ADMIN);
    expect(await screen.findByText("You have confirmed it is you. Try the action again?")).toBeTruthy();
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("client.b@rio.example");
    expect((screen.getByLabelText("Company") as HTMLInputElement).value).toBe("Rio Example Pty Ltd");
  });

  it("shows the denied panel without portal.user.invite", async () => {
    server.use(...lookups());
    renderAt("/admin/portal/users/new", VIEW);
    expect(await screen.findByRole("heading", { name: "You cannot invite external users" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Send invitation" })).toBeNull();
  });
});

describe("external user detail", () => {
  it("shows the grants with state and expiry, and renews an expired one", async () => {
    const expired = grant({ state: "expired", expiresAt: inDays(-2) });
    const user = portalUser({ effectiveStatus: "expired", grants: [expired] });
    const renewed = { ...expired, state: "live" as const, expiresAt: inDays(180), renewedAt: new Date().toISOString() };
    let current = user;
    const renews: string[] = [];
    server.use(
      ...lookups(),
      http.get(api(`${USERS}/${user.id}`), () => HttpResponse.json(current)),
      http.post(api(`${USERS}/${user.id}/grants/${expired.id}/renew`), ({ request }) => {
        renews.push(new URL(request.url).pathname);
        current = { ...user, effectiveStatus: "active", grants: [renewed] };
        return HttpResponse.json(renewed);
      }),
    );
    const { container } = renderAt(`/admin/portal/users/${user.id}?tab=access`, ADMIN);
    await screen.findByRole("heading", { name: "client.a@rio.example" });
    await userEvent.click(screen.getByRole("tab", { name: "Access" }));
    const table = await screen.findByRole("table", { name: "Project access" });
    expect(within(table).getByText("KF-01 Karratha compressor station")).toBeTruthy();
    expect(within(table).getByText("Expired")).toBeTruthy();
    expect(within(table).getByText("Whole project")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);

    await userEvent.click(within(table).getByRole("button", { name: "Renew access to KF-01 Karratha compressor station" }));
    await waitFor(() => expect(within(screen.getByRole("table", { name: "Project access" })).getByText("Current")).toBeTruthy());
    expect(renews).toEqual([`${USERS}/${user.id}/grants/${expired.id}/renew`]);
  });

  it("revokes a grant after confirming", async () => {
    const live = grant();
    const user = portalUser({ grants: [live] });
    let current = user;
    const deletes: string[] = [];
    server.use(
      ...lookups(),
      http.get(api(`${USERS}/${user.id}`), () => HttpResponse.json(current)),
      http.delete(api(`${USERS}/${user.id}/grants/${live.id}`), ({ request }) => {
        deletes.push(new URL(request.url).pathname);
        current = { ...user, grants: [] };
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(`/admin/portal/users/${user.id}`, ADMIN);
    await screen.findByRole("heading", { name: "client.a@rio.example" });
    await userEvent.click(screen.getByRole("tab", { name: "Access" }));
    await userEvent.click(await screen.findByRole("button", { name: "Remove access to KF-01 Karratha compressor station" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove access" }));
    expect(await screen.findByText("This person has no current project access.")).toBeTruthy();
    expect(deletes).toHaveLength(1);
  });

  it("suspends with a reason, which is required", async () => {
    const user = portalUser();
    const bodies: unknown[] = [];
    let current = user;
    server.use(
      ...lookups(),
      http.get(api(`${USERS}/${user.id}`), () => HttpResponse.json(current)),
      http.post(api(`${USERS}/${user.id}/suspend`), async ({ request }) => {
        bodies.push(await request.json());
        current = { ...user, status: "suspended", effectiveStatus: "suspended", suspendedAt: new Date().toISOString(), suspendedReason: "Contract ended" };
        return HttpResponse.json(current);
      }),
    );
    renderAt(`/admin/portal/users/${user.id}`, ADMIN);
    await screen.findByRole("heading", { name: "client.a@rio.example" });
    await userEvent.click(screen.getByRole("button", { name: "Suspend" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend" }));
    expect(await within(dialog).findByText("Enter a reason of up to 500 characters.")).toBeTruthy();
    expect(bodies).toHaveLength(0);

    await userEvent.type(within(dialog).getByLabelText("Reason"), "Contract ended");
    await userEvent.click(within(dialog).getByRole("button", { name: "Suspend" }));
    await waitFor(() => expect(bodies).toEqual([{ reason: "Contract ended" }]));
    expect(await screen.findByRole("button", { name: "Reinstate" })).toBeTruthy();
  });

  it("keeps a renew across a step-up and offers it again on return", async () => {
    const live = grant();
    const user = portalUser({ grants: [live] });
    server.use(
      ...lookups(),
      getUser(user),
      http.post(api(`${USERS}/${user.id}/grants/${live.id}/renew`), () =>
        HttpResponse.json({ detail: { code: "STEP_UP_REQUIRED", stepUpUrl: "/api/v1/auth/step-up/start" } }, { status: 401 }),
      ),
    );
    const first = renderAt(`/admin/portal/users/${user.id}`, ADMIN);
    await screen.findByRole("heading", { name: "client.a@rio.example" });
    await userEvent.click(screen.getByRole("tab", { name: "Access" }));
    await userEvent.click(await screen.findByRole("button", { name: "Renew access to KF-01 Karratha compressor station" }));
    await waitFor(() => expect(window.sessionStorage.getItem(PENDING_KEY)).not.toBeNull());
    const saved = JSON.parse(window.sessionStorage.getItem(PENDING_KEY)!) as { key: string; state: unknown };
    expect(saved).toMatchObject({ key: DETAIL_STEP_UP_KEY, state: { kind: "renew", grantId: live.id } });
    first.unmount();

    renderAt(`/admin/portal/users/${user.id}`, ADMIN);
    expect(await screen.findByText("You have confirmed it is you. Try the action again?")).toBeTruthy();
  });

  it("hides every action without the manage and suspend permissions", async () => {
    const user = portalUser();
    server.use(...lookups(), getUser(user));
    renderAt(`/admin/portal/users/${user.id}`, VIEW);
    await screen.findByRole("heading", { name: "client.a@rio.example" });
    expect(screen.queryByRole("button", { name: "Suspend" })).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "Access" }));
    await screen.findByRole("table", { name: "Project access" });
    expect(screen.queryByRole("button", { name: /Renew access/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add project access" })).toBeNull();
  });

  it("shows not found for a missing or another tenant's user", async () => {
    const missing = "00000000-0000-7000-8000-00000000dead";
    server.use(...lookups(), http.get(api(`${USERS}/${missing}`), () => HttpResponse.json({ code: "NOT_FOUND" }, { status: 404 })));
    const { container } = renderAt(`/admin/portal/users/${missing}`, ADMIN);
    expect(await screen.findByRole("link", { name: "Back to external users" })).toBeTruthy();
    expect(container.textContent).not.toContain("client.a@rio.example");
  });
});

describe("register search", () => {
  it("keeps known filters and drops anything else", () => {
    const projectId = "00000000-0000-4000-8000-0000000000a1";
    expect(validatePortalUsersSearch({ status: "active", expiring: "30", project: projectId, q: "rio", sort: "x" })).toEqual({
      status: "active",
      expiring: "30",
      project: projectId,
      q: "rio",
    });
    expect(validatePortalUsersSearch({ status: "expired", expiring: "45", project: "not-a-uuid" })).toEqual({});
  });

  it("maps a query to the list parameters", () => {
    const projectId = "00000000-0000-4000-8000-0000000000a1";
    const query = portalUsersQuery({ status: "invited", expiring: "7", project: projectId, q: "bhp" });
    expect(toListParams(query)).toEqual({ status: "invited", expiringWithinDays: 7, projectId, q: "bhp", limit: 50 });
  });
});
