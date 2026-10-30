import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../projects/__tests__/helpers";
import { listItem, revision, summary, templateDetail, REV1_ID, TEMPLATE_ID, V1 } from "./fixtures";

const VIEW = ["form.view"];
const MANAGE = ["form.view", "form.manage"];

const TEMPLATES = [
  listItem({ code: "coating-itr", name: "Coating ITR", kind: "inspection", currentRevisionNo: 1 }),
  listItem({ code: "weld-itp", name: "Weld ITP", kind: "itp", status: "draft", currentRevisionNo: null }),
];

function listTemplates(seen: URL[] = []) {
  return http.get(api("/api/v1/forms/templates"), ({ request }) => {
    seen.push(new URL(request.url));
    return HttpResponse.json({ items: TEMPLATES });
  });
}

const getCreated = http.get(api(`/api/v1/forms/templates/${TEMPLATE_ID}`), () =>
  HttpResponse.json(templateDetail([summary(1, "draft", REV1_ID)])),
);
const getRev1 = http.get(api(`/api/v1/forms/revisions/${REV1_ID}`), () =>
  HttpResponse.json(revision(summary(1, "draft", REV1_ID), V1)),
);

beforeAll(() => {
  server.listen({ onUnhandledFrame: "error" });
  resolveRelativeFetch();
});
afterEach(() => server.resetHandlers());
afterAll(() => {
  restoreFetch();
  server.close();
});

async function openUpload() {
  await userEvent.click(await screen.findByRole("button", { name: "Upload template" }));
  return screen.findByRole("dialog", { name: "Upload template" });
}

async function fillUpload(dialog: HTMLElement, json: string) {
  await userEvent.type(within(dialog).getByRole("textbox", { name: "Code" }), "coating-itr");
  await userEvent.type(within(dialog).getByRole("textbox", { name: "Name" }), "Coating ITR");
  await userEvent.click(within(dialog).getByRole("textbox", { name: "Template JSON" }));
  await userEvent.paste(json);
}

describe("form template register", () => {
  it("lists the templates with kind and current revision", async () => {
    server.use(listTemplates());
    const { container } = renderAt("/templates", VIEW);
    expect(await screen.findByRole("heading", { level: 1, name: "Form templates" })).toBeTruthy();
    expect(await screen.findByRole("link", { name: "coating-itr" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "weld-itp" })).toBeTruthy();
    expect(screen.getAllByText("v1").length).toBeGreaterThan(0);
    expect(screen.getByText("Not published")).toBeTruthy();
    expect(screen.getAllByText("ITP").length).toBeGreaterThan(0);
    expect(await blocking(container)).toEqual([]);
  });

  it("sends the kind filter and search from the URL to the API", async () => {
    const seen: URL[] = [];
    server.use(listTemplates(seen));
    renderAt("/templates?kind=itp&q=weld", VIEW);
    await screen.findByRole("link", { name: "coating-itr" });
    const last = seen[seen.length - 1]!;
    expect(last.searchParams.get("kind")).toBe("itp");
    expect(last.searchParams.get("q")).toBe("weld");
    expect(last.searchParams.get("limit")).toBe("200");
  });

  it("hides Upload template without form.manage", async () => {
    server.use(listTemplates());
    renderAt("/templates", VIEW);
    await screen.findByRole("link", { name: "coating-itr" });
    expect(screen.queryByRole("button", { name: "Upload template" })).toBeNull();
  });

  it("uploads a pasted body and opens the new template", async () => {
    const posted: unknown[] = [];
    server.use(
      listTemplates(),
      getCreated,
      getRev1,
      http.post(api("/api/v1/forms/templates"), async ({ request }) => {
        posted.push(await request.json());
        const detail = templateDetail([summary(1, "draft", REV1_ID)]);
        return HttpResponse.json(
          { template: { ...detail, revisions: undefined }, revision: revision(summary(1, "draft", REV1_ID), V1) },
          { status: 201 },
        );
      }),
    );
    const { router } = renderAt("/templates", MANAGE);
    const dialog = await openUpload();
    await fillUpload(dialog, JSON.stringify(V1));
    await userEvent.selectOptions(within(dialog).getByRole("combobox", { name: "Kind" }), "itp");
    await userEvent.click(within(dialog).getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(router.state.location.pathname).toBe(`/templates/${TEMPLATE_ID}`));
    expect(posted).toEqual([{ code: "coating-itr", name: "Coating ITR", kind: "itp", schema: V1 }]);
    expect(await screen.findByText("Template coating-itr was uploaded.")).toBeTruthy();
  });

  it("pre-fills empty fields from an upload body", async () => {
    const posted: unknown[] = [];
    server.use(
      listTemplates(),
      getCreated,
      getRev1,
      http.post(api("/api/v1/forms/templates"), async ({ request }) => {
        posted.push(await request.json());
        return HttpResponse.json({ code: "CODE_TAKEN" }, { status: 409 });
      }),
    );
    renderAt("/templates", MANAGE);
    const dialog = await openUpload();
    await userEvent.click(within(dialog).getByRole("textbox", { name: "Template JSON" }));
    await userEvent.paste(JSON.stringify({ code: "from-file", name: "From file", kind: "rfi", schema: V1 }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({ code: "from-file", name: "From file", kind: "rfi", schema: V1 });
  });

  it("lists the server's lint issues and keeps the text", async () => {
    server.use(
      listTemplates(),
      http.post(api("/api/v1/forms/templates"), () =>
        HttpResponse.json(
          {
            code: "TEMPLATE_INVALID",
            issues: [{ path: ["sections", 0, "fields", 0, "type"], code: "UNKNOWN_FIELD_TYPE", message: "barcode" }],
          },
          { status: 422 },
        ),
      ),
    );
    const { container } = renderAt("/templates", MANAGE);
    const dialog = await openUpload();
    const json = JSON.stringify(V1);
    await fillUpload(dialog, json);
    await userEvent.click(within(dialog).getByRole("button", { name: "Upload" }));

    expect(await within(dialog).findByText("This field type is not in the registry.")).toBeTruthy();
    expect(within(dialog).getByText("sections[0].fields[0].type")).toBeTruthy();
    expect((within(dialog).getByRole("textbox", { name: "Template JSON" }) as HTMLTextAreaElement).value).toBe(json);
    expect(await blocking(container.ownerDocument.body)).toEqual([]);
  });

  it("puts CODE_TAKEN on the code field", async () => {
    server.use(
      listTemplates(),
      http.post(api("/api/v1/forms/templates"), () => HttpResponse.json({ code: "CODE_TAKEN" }, { status: 409 })),
    );
    renderAt("/templates", MANAGE);
    const dialog = await openUpload();
    await fillUpload(dialog, JSON.stringify(V1));
    await userEvent.click(within(dialog).getByRole("button", { name: "Upload" }));
    expect(await within(dialog).findByText("Another template already uses this code.")).toBeTruthy();
  });

  it("shows a parse error with its line and column without calling the API", async () => {
    server.use(listTemplates());
    renderAt("/templates", MANAGE);
    const dialog = await openUpload();
    await fillUpload(dialog, '{"sections": [}');
    await userEvent.click(within(dialog).getByRole("button", { name: "Upload" }));
    expect(await within(dialog).findByText(/The JSON is not valid at line 1, column \d+\./)).toBeTruthy();
  });

  it("Check lists the lint issues without saving", async () => {
    const linted: unknown[] = [];
    server.use(
      listTemplates(),
      http.post(api("/api/v1/forms/lint"), async ({ request }) => {
        linted.push(await request.json());
        return HttpResponse.json({
          issues: [{ path: ["sections", 0, "fields", 1, "unit"], code: "UNKNOWN_UNIT", message: "furlong" }],
        });
      }),
    );
    renderAt("/templates", MANAGE);
    const dialog = await openUpload();
    await fillUpload(dialog, JSON.stringify(V1));
    await userEvent.click(within(dialog).getByRole("button", { name: "Check" }));
    expect(await within(dialog).findByText("This unit is not known.")).toBeTruthy();
    expect(within(dialog).getByText("sections[0].fields[1].unit")).toBeTruthy();
    expect(linted).toEqual([{ schema: V1 }]);
  });
});
