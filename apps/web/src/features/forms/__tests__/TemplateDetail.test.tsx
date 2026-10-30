import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { REV1_ID, REV2_ID, REV3_ID, revision, summary, TEMPLATE_ID, templateDetail, V1, V2 } from "./fixtures";

const VIEW = ["form.view"];
const ALL = ["form.view", "form.manage", "form.publish"];

const R1 = summary(1, "superseded", REV1_ID);
const R2 = summary(2, "published", REV2_ID);
const R3 = summary(3, "draft", REV3_ID);

function serve(revisions = [R1, R2]) {
  return [
    http.get(api(`/api/v1/forms/templates/${TEMPLATE_ID}`), () => HttpResponse.json(templateDetail(revisions))),
    http.get(api(`/api/v1/forms/revisions/${REV1_ID}`), () => HttpResponse.json(revision(R1, V1))),
    http.get(api(`/api/v1/forms/revisions/${REV2_ID}`), () => HttpResponse.json(revision(R2, V2))),
    http.get(api(`/api/v1/forms/revisions/${REV3_ID}`), () => HttpResponse.json(revision(R3, V2))),
    http.get(api("/api/v1/forms/templates"), () => HttpResponse.json({ items: [] })),
  ];
}

const PATH = `/templates/${TEMPLATE_ID}`;

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

async function confirmDialog(name: string, button: string) {
  const dialog = await screen.findByRole("dialog", { name });
  await userEvent.click(within(dialog).getByRole("button", { name: button }));
}

describe("form template detail page", () => {
  it("shows the header, the history newest first and the current revision's outline", async () => {
    server.use(...serve());
    const { container } = renderAt(PATH, VIEW);
    expect(await screen.findByRole("heading", { level: 1, name: "Coating ITR" })).toBeTruthy();
    expect(screen.getAllByText("coating-itr").length).toBeGreaterThan(0);

    const history = screen.getByRole("table", { name: "Revision history" });
    const rows = within(history).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.getAttribute("data-revision"))).toEqual(["2", "1"]);
    expect(within(rows[0]!).getByText("Published")).toBeTruthy();
    expect(within(rows[1]!).getByText("Superseded")).toBeTruthy();

    expect(await screen.findByRole("heading", { name: "Revision v2" })).toBeTruthy();
    expect(screen.getByText("blast_standard")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Fields in Preparation" })).toBeTruthy();
    expect(screen.getByText("Dropdown")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);
  });

  it("View shows another revision and keeps it in the URL", async () => {
    server.use(...serve());
    const { router } = renderAt(PATH, VIEW);
    await userEvent.click(await screen.findByRole("button", { name: "View v1" }));
    expect(await screen.findByRole("heading", { name: "Revision v1" })).toBeTruthy();
    expect(router.state.location.search).toMatchObject({ rev: 1 });
  });

  it("shows the not-found state for a missing or other tenant's template", async () => {
    server.use(
      http.get(api(`/api/v1/forms/templates/${TEMPLATE_ID}`), () =>
        HttpResponse.json({ code: "TEMPLATE_NOT_FOUND" }, { status: 404 }),
      ),
    );
    const { container } = renderAt(PATH, VIEW);
    expect(await screen.findByText("Not found")).toBeTruthy();
    expect(await blocking(container)).toEqual([]);
  });

  it("is read-only with form.view only", async () => {
    server.use(...serve([R1, R2, R3]));
    renderAt(PATH, VIEW);
    await screen.findByRole("heading", { level: 1, name: "Coating ITR" });
    for (const name of ["New draft", "Replace draft", "Discard draft", "Publish v3"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
  });

  it("offers Publish only with form.publish", async () => {
    server.use(...serve([R1, R2, R3]));
    renderAt(PATH, ["form.view", "form.manage"]);
    expect(await screen.findByRole("button", { name: "Discard draft" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Publish v3" })).toBeNull();
  });

  it("publishes the open draft with the template's sync version after confirming", async () => {
    const published: unknown[] = [];
    server.use(
      ...serve([R1, R2, R3]),
      http.post(api(`/api/v1/forms/revisions/${REV3_ID}/publish`), async ({ request }) => {
        published.push(await request.json());
        const detail = templateDetail([R1, R2, R3]);
        return HttpResponse.json({ template: detail, revision: revision({ ...R3, status: "published" }, V2) });
      }),
    );
    renderAt(PATH, ALL);
    await userEvent.click(await screen.findByRole("button", { name: "Publish v3" }));
    await confirmDialog("Publish v3 of coating-itr?", "Publish");
    await waitFor(() => expect(published).toEqual([{ expectedSyncVersion: 4 }]));
    expect(await screen.findByText("v3 of coating-itr was published.")).toBeTruthy();
  });

  it("lists lint issues when publishing is refused", async () => {
    server.use(
      ...serve([R1, R2, R3]),
      http.post(api(`/api/v1/forms/revisions/${REV3_ID}/publish`), () =>
        HttpResponse.json(
          { code: "TEMPLATE_INVALID", issues: [{ path: ["sections", 0], code: "DUPLICATE_KEY", message: "prep" }] },
          { status: 422 },
        ),
      ),
    );
    renderAt(PATH, ALL);
    await userEvent.click(await screen.findByRole("button", { name: "Publish v3" }));
    await confirmDialog("Publish v3 of coating-itr?", "Publish");
    expect(await screen.findByText("Publishing was refused. Fix these issues in the draft.")).toBeTruthy();
    expect(screen.getByText("This key is used more than once.")).toBeTruthy();
  });

  it("discards the open draft after confirming", async () => {
    let deleted = 0;
    server.use(
      ...serve([R1, R2, R3]),
      http.delete(api(`/api/v1/forms/revisions/${REV3_ID}`), () => {
        deleted += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(PATH, ALL);
    await userEvent.click(await screen.findByRole("button", { name: "Discard draft" }));
    await confirmDialog("Discard draft v3?", "Discard");
    await waitFor(() => expect(deleted).toBe(1));
    expect(await screen.findByText("Draft v3 was discarded.")).toBeTruthy();
  });

  it("New draft with empty JSON copies the published revision", async () => {
    const posted: unknown[] = [];
    server.use(
      ...serve(),
      http.post(api(`/api/v1/forms/templates/${TEMPLATE_ID}/revisions`), async ({ request }) => {
        posted.push(await request.json());
        return HttpResponse.json(revision(R3, V2), { status: 201 });
      }),
    );
    const { container } = renderAt(PATH, ALL);
    await userEvent.click(await screen.findByRole("button", { name: "New draft" }));
    const dialog = await screen.findByRole("dialog", { name: "New draft of coating-itr" });
    expect(await blocking(container.ownerDocument.body)).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(posted).toEqual([{}]));
    expect(await screen.findByText("Draft v3 was created.")).toBeTruthy();
  });

  it("Replace draft starts from the draft's JSON and saves it with PUT", async () => {
    const put: unknown[] = [];
    server.use(
      ...serve([R1, R2, R3]),
      http.put(api(`/api/v1/forms/revisions/${REV3_ID}`), async ({ request }) => {
        put.push(await request.json());
        return HttpResponse.json(revision(R3, V1));
      }),
    );
    renderAt(PATH, ALL);
    const replace = await screen.findByRole("button", { name: "Replace draft" });
    await waitFor(() => expect((replace as HTMLButtonElement).disabled).toBe(false));
    await userEvent.click(replace);
    const dialog = await screen.findByRole("dialog", { name: "Replace draft v3" });
    const text = within(dialog).getByRole("textbox", { name: "Template JSON" }) as HTMLTextAreaElement;
    expect(JSON.parse(text.value)).toEqual(V2);
    await userEvent.clear(text);
    await userEvent.click(text);
    await userEvent.paste(JSON.stringify(V1));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(put).toEqual([{ schema: V1, changeNote: "note 3" }]));
  });

  it("compares two revisions structurally from the URL", async () => {
    server.use(...serve());
    const { container } = renderAt(`${PATH}?tab=compare&from=1&to=2`, VIEW);
    expect(await screen.findByText("1 added, 0 removed, 1 changed, 1 moved")).toBeTruthy();
    const table = screen.getByRole("table", { name: "Changes from v1 to v2" });
    const moved = table.querySelector('tr[data-key="surface_prepared"]');
    expect(moved?.getAttribute("data-change")).toBe("moved");
    expect(within(moved as HTMLElement).getByText("Moved from section prep to final")).toBeTruthy();
    expect(within(table).getByText('unit: "mm" → "um"')).toBeTruthy();
    expect(await blocking(container)).toEqual([]);
  });

  it("changing From updates the URL", async () => {
    server.use(...serve([R1, R2, R3]));
    const { router } = renderAt(`${PATH}?tab=compare`, VIEW);
    const from = await screen.findByRole("combobox", { name: "From" });
    expect((from as HTMLSelectElement).value).toBe("2");
    await userEvent.selectOptions(from, "1");
    await waitFor(() => expect(router.state.location.search).toMatchObject({ tab: "compare", from: 1, to: 3 }));
  });

  it("asks for two revisions before comparing", async () => {
    server.use(...serve([summary(1, "draft", REV1_ID)]));
    renderAt(`${PATH}?tab=compare`, VIEW);
    expect(await screen.findByText("Nothing to compare yet")).toBeTruthy();
  });
});
