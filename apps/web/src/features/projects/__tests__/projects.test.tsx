import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { projectsIndexRoute } from "../../../routes/_app/projects/index";
import { httpSessionPort } from "../../shell/session";
import { validateProjectsSearch } from "../search";
import { api, blocking, project, renderAt, resolveRelativeFetch, restoreFetch, server } from "./helpers";

const VIEW = ["project.view"];
const CREATE = ["project.view", "project.create"];

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

function listProjects(items: ReturnType<typeof project>[], nextCursor: string | null = null, seen?: URL[]) {
  return http.get(api("/api/v1/projects"), ({ request }) => {
    seen?.push(new URL(request.url));
    return HttpResponse.json({ items, nextCursor });
  });
}

const noSites = http.get(api("/api/v1/sites"), () => HttpResponse.json({ items: [], nextCursor: null }));

describe("projects register", () => {
  it("shows one row per project with status chips that have an icon and a label", async () => {
    server.use(listProjects([project({ code: "L592", status: "active" }), project({ code: "KIPS-01", status: "draft" })]), noSites);
    const { container } = renderAt("/projects", VIEW);

    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText("L592")).toBeTruthy();
    for (const [row, label] of [
      [rows[0]!, "Active"],
      [rows[1]!, "Draft"],
    ] as const) {
      const chip = within(row).getByText(label).closest(".aip-status-chip") ?? within(row).getByText(label).parentElement!;
      expect(chip.querySelector("svg")).not.toBeNull();
    }
    expect(await blocking(container)).toEqual([]);
  });

  it("offers Create project in the empty state only with project.create", async () => {
    server.use(listProjects([]), noSites);
    const withPermission = renderAt("/projects", CREATE);
    const empty = await screen.findByText("No projects yet");
    expect(within(empty.parentElement!).getByRole("link", { name: "Create project" })).toBeTruthy();
    withPermission.unmount();

    renderAt("/projects", VIEW);
    await screen.findByText("No projects yet");
    expect(screen.queryByRole("link", { name: "Create project" })).toBeNull();
  });

  it("keeps the status filter in the URL and pages with the API cursor", async () => {
    const seen: URL[] = [];
    server.use(listProjects([project({ code: "L592", status: "active" })], "cursor-page-2", seen), noSites);
    const { router } = renderAt("/projects", VIEW);
    await screen.findByRole("table");

    await userEvent.selectOptions(screen.getByLabelText("Status"), "active");
    await waitFor(() => expect(router.state.location.search).toEqual({ status: "active" }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.get("status")).toBe("active"));

    const previous = screen.getByRole("button", { name: "Previous page" });
    expect((previous as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(router.state.location.search).toEqual({ status: "active", cursor: "cursor-page-2" }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.get("cursor")).toBe("cursor-page-2"));

    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    await waitFor(() => expect(router.state.location.search).toEqual({ status: "active" }));
  });

  it("shows the request reference when the list fails", async () => {
    server.use(
      http.get(api("/api/v1/projects"), () =>
        HttpResponse.json({ code: "INVALID_CURSOR" }, { status: 422, headers: { "x-request-id": "req-1234" } }),
      ),
      noSites,
    );
    renderAt("/projects", VIEW);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Reference: req-1234")).toBeTruthy();
  });

  it("validateSearch keeps valid values and drops the rest", () => {
    const validate = projectsIndexRoute.options.validateSearch as (s: Record<string, unknown>) => unknown;
    expect(validate({ status: "active", limit: "9999" })).toEqual({ status: "active" });
    expect(validateProjectsSearch({ status: "nope", limit: "25", q: "  kips ", cursor: "", created: "L592" })).toEqual({
      limit: 25,
      q: "kips",
      created: "L592",
    });
    expect(validateProjectsSearch({ limit: 50 })).toEqual({});
  });
});

describe("create project form", () => {
  it("rejects an invalid code without sending a request", async () => {
    let posts = 0;
    server.use(
      noSites,
      http.post(api("/api/v1/projects"), () => {
        posts += 1;
        return HttpResponse.json({}, { status: 500 });
      }),
    );
    const { container } = renderAt("/projects/new", CREATE);
    await userEvent.type(await screen.findByLabelText("Project code"), "ab cd");
    await userEvent.type(screen.getByLabelText("Name"), "Ichthys");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("Use 2 to 32 letters, digits or hyphens, starting with a letter or digit.")).toBeTruthy();
    expect(posts).toBe(0);
    expect(await blocking(container)).toEqual([]);
  });

  it("puts a 409 PROJECT_CODE_TAKEN on the code field and keeps the input", async () => {
    server.use(
      noSites,
      http.post(api("/api/v1/projects"), () => HttpResponse.json({ code: "PROJECT_CODE_TAKEN" }, { status: 409 })),
    );
    renderAt("/projects/new", CREATE);
    await userEvent.type(await screen.findByLabelText("Project code"), "L592");
    await userEvent.type(screen.getByLabelText("Name"), "Ichthys");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("This project code is already used in your organisation.")).toBeTruthy();
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Ichthys");
    expect((screen.getByLabelText("Project code") as HTMLInputElement).value).toBe("L592");
  });

  it("maps 422 field errors onto their inputs", async () => {
    server.use(
      noSites,
      http.post(api("/api/v1/projects"), () =>
        HttpResponse.json({ detail: [{ loc: ["body", "currency"], msg: "bad", type: "value_error" }] }, { status: 422 }),
      ),
    );
    renderAt("/projects/new", CREATE);
    await userEvent.type(await screen.findByLabelText("Project code"), "L592");
    await userEvent.type(screen.getByLabelText("Name"), "Ichthys");
    await userEvent.clear(screen.getByLabelText("Currency"));
    await userEvent.type(screen.getByLabelText("Currency"), "ZZZ");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByText("Use a three-letter ISO 4217 currency code.")).toBeTruthy();
  });

  it("creates the project and returns to the register with a confirmation", async () => {
    let body: unknown;
    server.use(
      noSites,
      listProjects([project({ code: "E2E-1", status: "draft" })]),
      http.post(api("/api/v1/projects"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(project({ code: "E2E-1", status: "draft", name: "Walking skeleton" }), { status: 201 });
      }),
    );
    const { router } = renderAt("/projects/new", CREATE);
    await userEvent.type(await screen.findByLabelText("Project code"), "e2e-1");
    await userEvent.type(screen.getByLabelText("Name"), "Walking skeleton");
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects"));
    expect(router.state.location.search).toEqual({ created: "E2E-1" });
    expect(await screen.findByText("Project E2E-1 was created.")).toBeTruthy();
    expect(body).toMatchObject({ code: "e2e-1", name: "Walking skeleton", currency: "AUD", status: "draft" });
    expect(body).not.toHaveProperty("siteId");
  });

  it("shows the permission-denied state without project.create", async () => {
    server.use(noSites);
    renderAt("/projects/new", VIEW);
    expect(await screen.findByText("You do not have permission to create projects.")).toBeTruthy();
    expect(screen.queryByLabelText("Project code")).toBeNull();
  });
});

describe("http session port", () => {
  it("builds the session from /me and the caller's abilities", async () => {
    server.use(
      http.get(api("/api/v1/me"), () =>
        HttpResponse.json({
          user: { id: "u1", displayName: "Alice Anderson", email: "alice@kaefer.test", status: "active", userClass: "staff" },
          tenant: { id: "t1", slug: "kaefer-demo", name: "Kaefer Demo" },
          memberships: [],
          aal: 1,
          amr: ["fed"],
        }),
      ),
      http.get(api("/api/v1/access/me/abilities"), () => HttpResponse.json({ permissions: ["project.view"] })),
    );
    expect(await httpSessionPort.getSession()).toEqual({
      user: { id: "u1", name: "Alice Anderson", email: "alice@kaefer.test" },
      tenant: { slug: "kaefer-demo", name: "Kaefer Demo" },
      permissions: ["project.view"],
    });
  });

  it("treats 401 as signed out", async () => {
    server.use(http.get(api("/api/v1/me"), () => new HttpResponse(null, { status: 401 })));
    expect(await httpSessionPort.getSession()).toBeNull();
  });

  it("denies by default when the abilities cannot be read", async () => {
    server.use(
      http.get(api("/api/v1/me"), () =>
        HttpResponse.json({
          user: { id: "u1", displayName: "Alice", email: "alice@kaefer.test", status: "active", userClass: "staff" },
          tenant: { id: "t1", slug: "kaefer-demo", name: "Kaefer Demo" },
          memberships: [],
          aal: 1,
          amr: ["fed"],
        }),
      ),
      http.get(api("/api/v1/access/me/abilities"), () => new HttpResponse(null, { status: 500 })),
    );
    expect((await httpSessionPort.getSession())?.permissions).toEqual([]);
  });
});
