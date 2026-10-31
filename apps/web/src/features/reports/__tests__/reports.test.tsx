import type { RenderJobView } from "@aip/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { validateReportsSearch } from "../search";

const VIEW = ["report.view"];

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

let next = 0;

function report(overrides: Partial<RenderJobView> = {}): RenderJobView {
  next += 1;
  const succeeded = (overrides.status ?? "succeeded") === "succeeded";
  return {
    id: `00000000-0000-7000-8000-${String(next).padStart(12, "0")}`,
    status: "succeeded",
    templateId: "00000000-0000-7000-8000-0000000000f1",
    templateKey: "project-summary",
    templateVersion: 1,
    variant: "internal",
    recordType: "project",
    recordId: "00000000-0000-4000-8000-0000000000aa",
    recordLabel: "KF-01 Karratha compressor station",
    projectId: "00000000-0000-4000-8000-0000000000aa",
    snapshotId: "00000000-0000-7000-8000-0000000000e1",
    dataHash: "a".repeat(64),
    opsJobId: null,
    requestedBy: null,
    rerenderOf: null,
    htmlSha256: null,
    fileId: succeeded ? "00000000-0000-7000-8000-0000000000d1" : null,
    pdfSha256: succeeded ? "b".repeat(64) : null,
    pdfSizeBytes: succeeded ? 1234 : null,
    errorCode: null,
    renderedAt: succeeded ? "2026-10-31T02:00:00Z" : null,
    createdAt: "2026-10-31T01:59:00Z",
    updatedAt: "2026-10-31T02:00:00Z",
    templateNameKey: "report.template.project_summary",
    ...overrides,
  };
}

function listReports(items: RenderJobView[], seen?: URL[], nextCursor: string | null = null) {
  return http.get(api("/api/v1/reports/renders"), ({ request }) => {
    seen?.push(new URL(request.url));
    return HttpResponse.json({ items, nextCursor });
  });
}

describe("report register", () => {
  it("shows status chips, template and record, and a download link only on succeeded reports", async () => {
    const ready = report();
    const queued = report({ status: "queued", recordLabel: null });
    const failed = report({ status: "failed", errorCode: "RENDER_UNAVAILABLE", recordLabel: "PL-07 Pilbara" });
    server.use(listReports([ready, queued, failed]));
    const { container } = renderAt("/reports/register", VIEW);

    expect(await screen.findByRole("heading", { level: 1, name: "Report register" })).toBeTruthy();
    await screen.findByText("KF-01 Karratha compressor station");
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);

    expect(within(rows[0]!).getByText("Ready")).toBeTruthy();
    expect(within(rows[0]!).getByText("Project summary")).toBeTruthy();
    expect(within(rows[0]!).getByText(/v1 · Internal/)).toBeTruthy();
    const link = within(rows[0]!).getByRole("link", { name: "Download PDF for KF-01 Karratha compressor station" });
    expect(link.getAttribute("href")).toBe(`/api/v1/reports/renders/${ready.id}/file`);
    expect(link.hasAttribute("download")).toBe(true);

    // No label (a REPORTS-02 job): the record id stands in. Not succeeded: nothing to download.
    expect(within(rows[1]!).getByText("Queued")).toBeTruthy();
    expect(within(rows[1]!).getByText(queued.recordId)).toBeTruthy();
    expect(within(rows[1]!).queryByRole("link")).toBeNull();
    expect(within(rows[2]!).getByText("Failed")).toBeTruthy();
    expect(within(rows[2]!).queryByRole("link")).toBeNull();

    for (const row of rows) {
      const chip = row.querySelector(".aip-status-chip") ?? row.querySelector("svg")!.parentElement!;
      expect(chip.querySelector("svg")).not.toBeNull();
    }
    expect(container.innerHTML).not.toMatch(/X-Amz|presigned|storage_key/i);
    expect(await blocking(container)).toEqual([]);
  });

  it("falls back to the template key when the template's name is unknown", async () => {
    server.use(listReports([report({ templateNameKey: null, templateKey: "custom-sheet" })]));
    renderAt("/reports/register", VIEW);
    expect(await screen.findByText("custom-sheet")).toBeTruthy();
  });

  it("keeps the status filter and the search in the URL and sends them to the API", async () => {
    const seen: URL[] = [];
    server.use(listReports([report()], seen, "cursor-page-2"));
    const { router } = renderAt("/reports/register", VIEW);
    await screen.findByRole("table");

    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Status" }), "succeeded");
    await waitFor(() => expect(router.state.location.search).toEqual({ status: "succeeded" }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.getAll("status")).toEqual(["succeeded"]));

    await userEvent.type(screen.getByRole("searchbox", { name: "Search record or template" }), "karratha");
    await waitFor(() => expect(router.state.location.search).toEqual({ status: "succeeded", q: "karratha" }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.get("q")).toBe("karratha"));

    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(seen.at(-1)?.searchParams.get("cursor")).toBe("cursor-page-2"));
  });

  it("says no report has been generated yet, and that none match a filter", async () => {
    server.use(listReports([]));
    const first = renderAt("/reports/register", VIEW);
    expect(await screen.findByText("No reports have been generated yet.")).toBeTruthy();
    first.unmount();

    renderAt("/reports/register?status=failed", VIEW);
    expect(await screen.findByText("No reports match these filters.")).toBeTruthy();
  });

  it("shows the error with the request id when the list fails", async () => {
    server.use(
      http.get(api("/api/v1/reports/renders"), () =>
        HttpResponse.json({ code: "BOOM" }, { status: 500, headers: { "x-request-id": "req-123" } }),
      ),
    );
    renderAt("/reports/register", VIEW);
    expect(await screen.findByText("The reports could not be loaded.")).toBeTruthy();
    expect(screen.getByText("Reference: req-123")).toBeTruthy();
  });

  it("is in the Insight menu only with report.view", async () => {
    server.use(listReports([]));
    const withView = renderAt("/reports/register", VIEW);
    const nav = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(within(nav).getByRole("link", { name: "Reports" }).getAttribute("href")).toBe("/reports/register");
    withView.unmount();

    const empty = () => HttpResponse.json({ items: [], nextCursor: null });
    server.use(http.get(api("/api/v1/projects"), empty), http.get(api("/api/v1/sites"), empty));
    renderAt("/projects", ["project.view"]);
    const other = await screen.findByRole("navigation", { name: "Main navigation" });
    expect(within(other).queryByRole("link", { name: "Reports" })).toBeNull();
  });
});

describe("validateReportsSearch", () => {
  it("keeps known statuses and search, and drops anything else", () => {
    expect(validateReportsSearch({ status: "succeeded", q: "kf-01", sort: "-generated", other: "x" })).toEqual({
      status: "succeeded",
      q: "kf-01",
    });
    expect(validateReportsSearch({ status: "bogus" })).toEqual({});
  });
});
