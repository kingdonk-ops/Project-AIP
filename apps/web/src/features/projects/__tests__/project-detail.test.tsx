import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, project, renderAt, resolveRelativeFetch, restoreFetch, server } from "./helpers";

const VIEW = ["project.view"];
const EDIT = ["project.view", "project.update"];
const ARCHIVE = ["project.view", "project.update", "project.archive"];

const ID = "00000000-0000-7000-8000-0000000000d1";
const noSites = http.get(api("/api/v1/sites"), () => HttpResponse.json({ items: [], nextCursor: null }));

function getProject(overrides: Partial<ReturnType<typeof project>> = {}) {
  return http.get(api(`/api/v1/projects/${ID}`), () =>
    HttpResponse.json(project({ id: ID, code: "L592", status: "active", ...overrides })),
  );
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

describe("project detail page", () => {
  it("shows the loading state, then the project header", async () => {
    server.use(
      http.get(api(`/api/v1/projects/${ID}`), async () => {
        await delay(20);
        return HttpResponse.json(project({ id: ID, code: "L592", status: "active" }));
      }),
      noSites,
    );
    const { container } = renderAt(`/projects/${ID}`, VIEW);

    // The spinner's accessible label is the shared ui.loading term.
    expect(await screen.findByText("Loading…")).toBeTruthy();
    expect(await screen.findByRole("heading", { level: 1, name: "Project L592" })).toBeTruthy();
    expect(screen.getAllByText("L592").length).toBeGreaterThan(0);
    expect(await blocking(container)).toEqual([]);
  });

  it("shows the error state with the request reference when the load fails", async () => {
    server.use(
      http.get(api(`/api/v1/projects/${ID}`), () =>
        HttpResponse.json({ code: "BOOM" }, { status: 500, headers: { "x-request-id": "req-det-1" } }),
      ),
      noSites,
    );
    renderAt(`/projects/${ID}`, VIEW);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("req-det-1")).toBeTruthy();
  });

  it("shows the not-found state when the project is missing or in another tenant", async () => {
    server.use(
      http.get(api(`/api/v1/projects/${ID}`), () => HttpResponse.json({ code: "PROJECT_NOT_FOUND" }, { status: 404 })),
      noSites,
    );
    renderAt(`/projects/${ID}`, VIEW);
    expect(await screen.findByText("Not found")).toBeTruthy();
  });

  it("without project.update the fields are read-only, not an editable form", async () => {
    server.use(getProject(), noSites);
    renderAt(`/projects/${ID}`, VIEW);
    await screen.findByRole("heading", { level: 1, name: "Project L592" });
    expect(screen.getByRole("heading", { name: "Project details" })).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Name" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });

  it("edits the name and saves it, sending the sync version", async () => {
    const seen: unknown[] = [];
    server.use(
      getProject(),
      http.patch(api(`/api/v1/projects/${ID}`), async ({ request }) => {
        seen.push(await request.json());
        return HttpResponse.json(project({ id: ID, code: "L592", name: "Line 592 refurbishment", status: "active", syncVersion: 2 }));
      }),
      noSites,
    );
    renderAt(`/projects/${ID}`, EDIT);
    const name = await screen.findByRole("textbox", { name: "Name" });
    await userEvent.clear(name);
    await userEvent.type(name, "Line 592 refurbishment");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.getByText("Project L592 was saved.")).toBeTruthy());
    expect(seen).toHaveLength(1);
    expect((seen[0] as Record<string, unknown>).syncVersion).toBe(1);
    expect((seen[0] as Record<string, unknown>).name).toBe("Line 592 refurbishment");
  });

  it("offers Archive project only with project.archive", async () => {
    server.use(getProject(), noSites);
    const withoutArchive = renderAt(`/projects/${ID}`, EDIT);
    await screen.findByRole("heading", { level: 1, name: "Project L592" });
    expect(screen.queryByRole("button", { name: "Archive project" })).toBeNull();
    withoutArchive.unmount();

    renderAt(`/projects/${ID}`, ARCHIVE);
    await screen.findByRole("heading", { level: 1, name: "Project L592" });
    expect(screen.getByRole("button", { name: "Archive project" })).toBeTruthy();
  });

  it("archives the project after confirmation", async () => {
    const patched: unknown[] = [];
    server.use(
      getProject(),
      http.patch(api(`/api/v1/projects/${ID}`), async ({ request }) => {
        patched.push(await request.json());
        return HttpResponse.json(project({ id: ID, code: "L592", status: "archived", syncVersion: 2 }));
      }),
      noSites,
    );
    renderAt(`/projects/${ID}`, ARCHIVE);
    await screen.findByRole("heading", { level: 1, name: "Project L592" });
    await userEvent.click(screen.getByRole("button", { name: "Archive project" }));

    const dialog = await screen.findByRole("dialog", { name: "Archive L592?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(screen.getByText("Project L592 was archived.")).toBeTruthy());
    expect((patched[0] as Record<string, unknown>).status).toBe("archived");
  });

  it("handles a server 403 on archive without crashing", async () => {
    server.use(
      getProject(),
      http.patch(api(`/api/v1/projects/${ID}`), () => HttpResponse.json({ code: "FORBIDDEN" }, { status: 403 })),
      noSites,
    );
    renderAt(`/projects/${ID}`, ARCHIVE);
    await screen.findByRole("heading", { level: 1, name: "Project L592" });
    await userEvent.click(screen.getByRole("button", { name: "Archive project" }));
    const dialog = await screen.findByRole("dialog", { name: "Archive L592?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(screen.getByText("You do not have permission to change this project.")).toBeTruthy());
    // The page is still there.
    expect(screen.getByRole("heading", { level: 1, name: "Project L592" })).toBeTruthy();
  });
});
