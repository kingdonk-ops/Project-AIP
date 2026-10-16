import type { JobOut } from "@aip/api-client";
import { Toaster } from "@aip/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { t } from "../../shell/t";
import { MyJobsDrawer } from "../MyJobsDrawer";

// OPS-03: the My jobs drawer against MSW in front of the generated client.

function job(overrides: Partial<JobOut>): JobOut {
  return {
    id: "01a143bb-0000-7000-8000-000000000001",
    jobType: "projects.export",
    status: "queued",
    attempts: 0,
    correlationId: "01a143bb-0000-7000-8000-0000000000c1",
    resultRef: null,
    error: null,
    requestedBy: "00000000-0000-4000-8000-0000000000a1",
    createdAt: "2026-10-16T08:00:00Z",
    updatedAt: "2026-10-16T08:00:00Z",
    ...overrides,
  };
}

const RUNNING = job({ id: "01a143bb-0000-7000-8000-000000000002", status: "running" });
const FAILED = job({ id: "01a143bb-0000-7000-8000-000000000003", status: "failed", error: "timeout" });
const DONE = job({ id: "01a143bb-0000-7000-8000-000000000004", status: "succeeded", resultRef: "/projects" });

let listCalls: URL[] = [];

function serve(items: JobOut[]) {
  server.use(
    http.get(api("/api/v1/jobs/mine"), ({ request }) => {
      const url = new URL(request.url);
      listCalls.push(url);
      const wanted = url.searchParams.getAll("status");
      const shown = wanted.length ? items.filter((j) => wanted.includes(j.status)) : items;
      return HttpResponse.json({ items: shown, nextCursor: null });
    }),
  );
}

function renderDrawer() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MyJobsDrawer open onOpenChange={() => {}} />
      <Toaster translate={t} />
    </QueryClientProvider>,
  );
}

beforeAll(() => {
  server.listen();
  resolveRelativeFetch();
});
afterEach(() => {
  server.resetHandlers();
  listCalls = [];
});
afterAll(() => {
  restoreFetch();
  server.close();
});

describe("MyJobsDrawer", () => {
  it("lists the caller's jobs with status, progress, error and reference", async () => {
    serve([RUNNING, FAILED, DONE]);
    renderDrawer();
    const dialog = await screen.findByRole("dialog", { name: "My jobs" });
    const rows = await within(dialog).findAllByTestId("job-row");
    expect(rows.map((r) => r.dataset.status)).toEqual(["running", "failed", "succeeded"]);
    expect(within(rows[0]!).getByText("Running")).toBeTruthy();
    expect(within(rows[0]!).getByRole("status").textContent).toContain("Working on it");
    expect(within(rows[1]!).getByText("timeout")).toBeTruthy();
    expect(within(rows[1]!).getByText(FAILED.correlationId).tagName).toBe("CODE");
    expect(within(rows[2]!).getByRole("link", { name: "Open result" }).getAttribute("href")).toBe("/projects");
    const results = await axe.run(dialog, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });

  it("filter chips ask the API for those statuses", async () => {
    const user = userEvent.setup();
    serve([RUNNING, FAILED, DONE]);
    renderDrawer();
    await screen.findAllByTestId("job-row");
    await user.click(screen.getByRole("button", { name: "Failed" }));
    await waitFor(() => expect(screen.getAllByTestId("job-row")).toHaveLength(1));
    expect(listCalls.at(-1)?.searchParams.getAll("status")).toEqual(["failed"]);
    expect(screen.getByRole("button", { name: "Failed" }).getAttribute("aria-pressed")).toBe("true");
    await user.click(screen.getByRole("button", { name: "Done" }));
    await waitFor(() => expect(listCalls.at(-1)?.searchParams.getAll("status")).toEqual(["succeeded", "cancelled"]));
  });

  it("cancel posts to the job and refetches the list", async () => {
    const user = userEvent.setup();
    serve([RUNNING]);
    let cancelled: string | undefined;
    server.use(
      http.post(api("/api/v1/jobs/:id/cancel"), ({ params }) => {
        cancelled = String(params.id);
        return HttpResponse.json({ ...RUNNING, status: "cancelled" });
      }),
    );
    renderDrawer();
    await screen.findAllByTestId("job-row");
    const before = listCalls.length;
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(cancelled).toBe(RUNNING.id));
    await waitFor(() => expect(listCalls.length).toBeGreaterThan(before));
    expect(await screen.findByText("Job cancelled")).toBeTruthy();
  });

  it("a 409 says the job had already finished", async () => {
    const user = userEvent.setup();
    serve([RUNNING]);
    server.use(
      http.post(api("/api/v1/jobs/:id/cancel"), () =>
        HttpResponse.json({ code: "JOB_FINISHED", status: "succeeded" }, { status: 409 }),
      ),
    );
    renderDrawer();
    await screen.findAllByTestId("job-row");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(await screen.findByText("That job had already finished")).toBeTruthy();
  });

  it("retry is offered only for failed jobs", async () => {
    const user = userEvent.setup();
    serve([FAILED]);
    let retried = false;
    server.use(
      http.post(api("/api/v1/jobs/:id/retry"), () => {
        retried = true;
        return HttpResponse.json({ ...FAILED, id: "01a143bb-0000-7000-8000-000000000009", status: "queued" }, { status: 201 });
      }),
    );
    renderDrawer();
    await screen.findAllByTestId("job-row");
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(retried).toBe(true));
    expect(await screen.findByText("Job queued again")).toBeTruthy();
  });

  it("shows the empty state when there are no jobs", async () => {
    serve([]);
    renderDrawer();
    expect(await screen.findByText("No jobs here")).toBeTruthy();
  });
});
