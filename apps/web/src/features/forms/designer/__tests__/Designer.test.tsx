import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { api, blocking, renderAt, resolveRelativeFetch, restoreFetch, server } from "../../../projects/__tests__/helpers";
import { REV2_ID, REV3_ID, revision, summary, TEMPLATE_ID, templateDetail, V2 } from "../../__tests__/fixtures";

const VIEW = ["form.view"];
const ALL = ["form.view", "form.manage", "form.publish"];

const DRAFT = {
  schemaVersion: 2,
  sections: [
    {
      key: "prep",
      label: "Preparation",
      fields: [
        { key: "surface_prepared", type: "boolean", label: "Surface prepared" },
        {
          key: "blast_standard",
          type: "dropdown",
          label: "Blast standard",
          options: [{ value: "sa2_5", label: "Sa 2.5" }],
          visibleIf: { "==": [{ var: "answers.surface_prepared" }, true] },
        },
      ],
      rules: [{ key: "prep_ok", expr: { "==": [{ var: "answers.surface_prepared" }, true] }, label: "Prepared" }],
    },
    { key: "final", label: "Final", fields: [{ key: "remarks", type: "text", label: "Remarks" }] },
  ],
};

const R2 = summary(2, "published", REV2_ID);
const R3 = summary(3, "draft", REV3_ID);
const DRAFT_PATH = `/templates/${TEMPLATE_ID}/revisions/3/design`;
const PUBLISHED_PATH = `/templates/${TEMPLATE_ID}/revisions/2/design`;

interface Calls {
  lint: unknown[];
  saves: unknown[];
  publishes: unknown[];
}

function serve(options: { issues?: unknown[]; revisions?: ReturnType<typeof summary>[]; save?: number } = {}): Calls {
  const calls: Calls = { lint: [], saves: [], publishes: [] };
  const revisions = options.revisions ?? [R2, R3];
  server.use(
    http.get(api(`/api/v1/forms/templates/${TEMPLATE_ID}`), () => HttpResponse.json(templateDetail(revisions))),
    http.get(api(`/api/v1/forms/revisions/${REV2_ID}`), () => HttpResponse.json(revision(R2, V2))),
    http.get(api(`/api/v1/forms/revisions/${REV3_ID}`), () => HttpResponse.json(revision(R3, DRAFT))),
    http.post(api("/api/v1/forms/lint"), async ({ request }) => {
      calls.lint.push(await request.json());
      return HttpResponse.json({ issues: options.issues ?? [] });
    }),
    http.put(api(`/api/v1/forms/revisions/${REV3_ID}`), async ({ request }) => {
      const body = (await request.json()) as { schema: Record<string, unknown> };
      calls.saves.push(body);
      if (options.save === 409) return HttpResponse.json({ code: "VERSION_CONFLICT" }, { status: 409 });
      return HttpResponse.json(revision(R3, body.schema));
    }),
    http.post(api(`/api/v1/forms/revisions/${REV3_ID}/publish`), async ({ request }) => {
      calls.publishes.push(await request.json());
      return HttpResponse.json({ template: templateDetail(revisions), revision: revision({ ...R3, status: "published" }, DRAFT) });
    }),
    http.get(api("/api/v1/forms/templates"), () => HttpResponse.json({ items: [] })),
  );
  return calls;
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

async function openDesigner(path = DRAFT_PATH, permissions: readonly string[] = ALL) {
  const rendered = renderAt(path, permissions);
  await screen.findByTestId("designer-canvas");
  return rendered;
}

function canvas() {
  return screen.getByTestId("designer-canvas");
}

function fieldOrder(section: string): string[] {
  const panel = canvas().querySelector(`[data-section="${section}"]`)!;
  return [...panel.querySelectorAll("[data-field]")].map((el) => el.getAttribute("data-field")!);
}

function row(key: string): HTMLElement {
  return canvas().querySelector<HTMLElement>(`[data-select="${key}"]`)!;
}

function properties() {
  return within(screen.getByTestId("designer-properties"));
}

const lintClean = () => screen.findByText("No issues", {}, { timeout: 3000 });

describe("form designer", () => {
  it("adds a field from the palette, follows its label with the key, and moves it with Alt+ArrowDown", async () => {
    serve();
    await openDesigner();
    await userEvent.click(row("surface_prepared"));
    await userEvent.click(within(screen.getByTestId("designer-palette")).getByRole("button", { name: "Measurement" }));

    expect(fieldOrder("prep")).toEqual(["surface_prepared", "measurement", "blast_standard"]);
    expect(row("measurement").getAttribute("aria-current")).toBe("true");
    expect((properties().getByLabelText("Unit") as HTMLSelectElement).value).toBe("mm");

    const label = properties().getByLabelText("Label");
    await userEvent.clear(label);
    await userEvent.type(label, "DFT average");
    expect((properties().getByLabelText("Key") as HTMLInputElement).value).toBe("dft_average");

    row("dft_average").focus();
    await userEvent.keyboard("{Alt>}{ArrowDown}{/Alt}");
    expect(fieldOrder("prep")).toEqual(["surface_prepared", "blast_standard", "dft_average"]);
    expect(document.activeElement).toBe(row("dft_average"));
    expect(screen.getByText("Unsaved changes")).toBeTruthy();
  });

  it("asks before deleting a field that logic reads and names the reading keys", async () => {
    serve();
    await openDesigner();
    row("surface_prepared").focus();
    await userEvent.keyboard("{Delete}");
    const dialog = await screen.findByRole("dialog", { name: "Delete Surface prepared?" });
    expect(dialog.textContent).toContain("blast_standard");
    expect(dialog.textContent).toContain("prep_ok");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fieldOrder("prep")).toContain("surface_prepared");

    // An unreferenced field goes without asking.
    row("remarks").focus();
    await userEvent.keyboard("{Delete}");
    expect(fieldOrder("final")).toEqual([]);
    expect(screen.getByRole("button", { name: "Add a field" })).toBeTruthy();
  });

  it("keeps logic it cannot edit and shows it as Logic set", async () => {
    serve();
    await openDesigner();
    expect(within(row("blast_standard")).getByText("Logic set")).toBeTruthy();
    await userEvent.click(row("blast_standard"));
    expect(properties().getByText("visibleIf")).toBeTruthy();

    // A rename rewrites the logic that reads the key.
    await userEvent.click(row("surface_prepared"));
    const key = properties().getByLabelText("Key");
    await userEvent.clear(key);
    expect(properties().getByText(/Use lower-case letters/)).toBeTruthy();
    await userEvent.type(key, "surface_ready");
    await userEvent.click(screen.getByRole("button", { name: "JSON" }));
    const text = (screen.getByLabelText("Template JSON") as HTMLTextAreaElement).value;
    expect(text).toContain('"answers.surface_ready"');
    expect(text).not.toContain('"answers.surface_prepared"');
  });

  it("previews the unsaved schema, shows a required error after touching, and has a phone width", async () => {
    serve();
    await openDesigner();
    await userEvent.click(row("remarks"));
    await userEvent.click(properties().getByLabelText("Required"));
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    const remarks = await screen.findByRole("textbox", { name: /Remarks/ });
    await userEvent.click(remarks);
    await userEvent.tab();
    expect(await screen.findByText("This field is required.")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Phone" }));
    const frame = screen.getByTestId("designer-preview-frame");
    expect(frame.style.width).toBe("375px");
  });

  it("applies pasted JSON as one undo step and rejects invalid JSON with its position", async () => {
    serve();
    await openDesigner();
    await userEvent.click(screen.getByRole("button", { name: "JSON" }));
    const textarea = screen.getByLabelText("Template JSON");
    const next = { schemaVersion: 2, sections: [{ key: "only", label: "Only", fields: [{ key: "a", type: "text", label: "A" }] }] };
    fireEvent.change(textarea, { target: { value: JSON.stringify(next) } });
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    await userEvent.click(screen.getByRole("button", { name: "Design" }));
    expect(canvas().querySelector('[data-section="only"]')).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(canvas().querySelector('[data-section="prep"]')).toBeTruthy();
    expect(canvas().querySelector('[data-section="only"]')).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "JSON" }));
    fireEvent.change(screen.getByLabelText("Template JSON"), { target: { value: '{\n  "sections": [,]\n}' } });
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByText("The JSON is not valid at line 2, column 16.")).toBeTruthy();
  });

  it("lints once after typing stops, not per keystroke", async () => {
    const calls = serve();
    await openDesigner();
    await lintClean();
    expect(calls.lint).toHaveLength(1);

    await userEvent.click(row("remarks"));
    await userEvent.type(properties().getByLabelText("Label"), "abcde");
    await waitFor(() => expect(calls.lint).toHaveLength(2), { timeout: 3000 });
    await new Promise((resolve) => setTimeout(resolve, 1000));
    expect(calls.lint).toHaveLength(2);
    const sent = calls.lint[1] as { schema: typeof DRAFT };
    expect(sent.schema.sections[1]!.fields[0]!.label).toBe("Remarksabcde");
  });

  it("shows lint issue counts on rows and selects the field when an issue is clicked", async () => {
    serve({ issues: [{ path: ["sections", 0, "fields", 1, "options"], code: "OPTIONS_REQUIRED", message: "dropdown needs options" }] });
    await openDesigner();
    const issue = await waitFor(
      () => {
        const button = screen.getByTestId("designer-lint").querySelector<HTMLButtonElement>(".dsg-lint__button");
        if (!button) throw new Error("no issue yet");
        return button;
      },
      { timeout: 3000 },
    );
    expect(within(row("blast_standard")).getByText("1 issues")).toBeTruthy();
    await userEvent.click(issue);
    expect(row("blast_standard").getAttribute("aria-current")).toBe("true");
    expect(properties().getByText("blast_standard")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Publish v3" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Fix the issues before publishing.")).toBeTruthy();
  });

  it("saves with the template's sync version, then publishes after confirming", async () => {
    const calls = serve();
    const { router } = await openDesigner();
    await lintClean();
    const publish = screen.getByRole("button", { name: "Publish v3" });
    expect(publish.hasAttribute("disabled")).toBe(false);

    await userEvent.click(row("remarks"));
    await userEvent.type(properties().getByLabelText("Label"), " here");
    expect(screen.getByRole("button", { name: "Publish v3" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("Save the draft before publishing.")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(calls.saves).toHaveLength(1));
    const saved = calls.saves[0] as { schema: typeof DRAFT; expectedSyncVersion: number };
    expect(saved.expectedSyncVersion).toBe(4);
    expect(saved.schema.sections[1]!.fields[0]!.label).toBe("Remarks here");
    expect(await screen.findByText("All changes saved")).toBeTruthy();

    await lintClean();
    await waitFor(() => expect(screen.getByRole("button", { name: "Publish v3" }).hasAttribute("disabled")).toBe(false));
    await userEvent.click(screen.getByRole("button", { name: "Publish v3" }));
    const dialog = await screen.findByRole("dialog", { name: "Publish v3 of coating-itr?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Publish" }));
    await waitFor(() => expect(calls.publishes).toEqual([{ expectedSyncVersion: 4 }]));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/templates/${TEMPLATE_ID}`));
  });

  it("shows the conflict toast with Reload when another editor saved first", async () => {
    serve({ save: 409 });
    await openDesigner();
    await userEvent.click(row("remarks"));
    await userEvent.type(properties().getByLabelText("Label"), "!");
    await userEvent.keyboard("{Control>}s{/Control}");
    expect(await screen.findByText("Someone else saved this draft. Your version is kept in the JSON view.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reload" })).toBeTruthy();
    expect((screen.getByLabelText("Template JSON") as HTMLTextAreaElement).value).toContain("Remarks!");
  });

  it("is read-only with form.view only", async () => {
    serve();
    const { container } = await openDesigner(DRAFT_PATH, VIEW);
    expect(screen.queryByTestId("designer-palette")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save draft" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Edit as new draft" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Move / })).toBeNull();
    await userEvent.click(row("remarks"));
    expect((properties().getByLabelText("Label") as HTMLInputElement).disabled).toBe(true);
    expect(await blocking(container)).toEqual([]);
  });

  it("opens a published revision read-only with Edit as new draft for form.manage", async () => {
    serve({ revisions: [R2] });
    await openDesigner(PUBLISHED_PATH, ALL);
    expect(screen.queryByTestId("designer-palette")).toBeNull();
    expect(screen.getByText("v2 is Published and cannot change.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit as new draft" })).toBeTruthy();
  });

  it("shows the not-found state for an unknown revision or another tenant's template", async () => {
    serve();
    renderAt(`/templates/${TEMPLATE_ID}/revisions/9/design`, ALL);
    expect(await screen.findByText("Not found")).toBeTruthy();
  });

  it("has no serious or critical axe violations in Design, Preview and JSON", async () => {
    serve();
    const { container } = await openDesigner();
    await userEvent.click(row("blast_standard"));
    expect(await blocking(container)).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByTestId("designer-preview-frame");
    expect(await blocking(container)).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "JSON" }));
    expect(await blocking(container)).toEqual([]);
  });
});
