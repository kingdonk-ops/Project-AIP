import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { MediaAdapter, RendererAdapters } from "./adapters";
import coating from "./fixtures/coating-itr.json";
import { FormRenderer, type FormRendererProps } from "./FormRenderer";
import { evaluateAnswers } from "./logic/evaluate";
import type { Answers, FormSchema } from "./logic/types";
import { axeBlocking } from "./test/axe";
import { tKey } from "./test/translate";

const schema = coating as FormSchema;

type Spy = ReturnType<typeof vi.fn<(next: Answers, changedKey: string) => void>>;

/** Holds answers in state like a host page, reporting every change to `spy`. */
function Harness({
  initial = {},
  spy,
  ...rest
}: { initial?: Answers; spy: Spy } & Partial<Omit<FormRendererProps, "answers" | "onChange">>) {
  const [answers, setAnswers] = useState<Answers>(initial);
  return (
    <FormRenderer
      schema={schema}
      mode="draft"
      t={tKey}
      {...rest}
      answers={answers}
      onChange={(next, key) => {
        spy(next, key);
        setAnswers(next);
      }}
    />
  );
}

const ASSET = "6f1c2a1e-0000-4000-8000-000000000001";
const USER = "6f1c2a1e-0000-4000-8000-000000000002";
const PHOTO = "6f1c2a1e-0000-4000-8000-000000000003";
const SIGNATURE = "6f1c2a1e-0000-4000-8000-000000000004";

const fullAnswers: Answers = {
  inspection_date: "2026-10-30",
  surface_prepared: false,
  remarks: "Mill scale on the north flange",
  blast_standard: "sa2_5",
  defects: ["rust", "oil"],
  coats: 2,
  humidity: 65.5,
  steel_temp: { value: 21.5, unit: "degC" },
  dft_avg: { value: 0.18, unit: "mm" },
  photos: [{ fileId: PHOTO }],
  asset: ASSET,
  inspector: USER,
  signature: { fileId: SIGNATURE },
};

describe("FormRenderer: visibility follows the evaluator", () => {
  it("shows remarks only after surface_prepared is answered no", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(<FormRenderer schema={schema} answers={{}} onChange={onChange} mode="draft" t={tKey} />);

    const group = screen.getByRole("radiogroup", { name: "Surface prepared" });
    expect(within(group).getAllByRole("radio")).toHaveLength(2);
    expect(screen.queryByLabelText("Remarks")).toBeNull();

    await user.click(within(group).getByLabelText("forms.renderer.no"));
    expect(onChange).toHaveBeenCalledWith({ surface_prepared: false }, "surface_prepared");

    rerender(<FormRenderer schema={schema} answers={{ surface_prepared: false }} onChange={onChange} mode="draft" t={tKey} />);
    expect(screen.getByRole("textbox", { name: "Remarks" })).toBeTruthy();
  });

  it("hides remarks again and leaves the stale answer untouched", () => {
    const onChange = vi.fn();
    render(
      <FormRenderer
        schema={schema}
        answers={{ surface_prepared: true, remarks: "old" }}
        onChange={onChange}
        mode="draft"
        t={tKey}
      />,
    );
    expect(screen.queryByLabelText("Remarks")).toBeNull();
    expect(screen.queryByText("old")).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not render a section whose fields are all hidden", () => {
    const hidden: FormSchema = {
      schemaVersion: 1,
      sections: [
        { key: "a", label: "Shown", fields: [{ key: "x", type: "boolean", label: "X" }] },
        {
          key: "b",
          label: "Hidden section",
          visibleIf: { "==": [{ var: "answers.x" }, true] },
          fields: [{ key: "y", type: "text", label: "Y" }],
        },
      ],
    };
    render(<FormRenderer schema={hidden} answers={{}} onChange={vi.fn()} mode="draft" t={tKey} />);
    expect(screen.queryByText("Hidden section")).toBeNull();
    expect(screen.getByRole("group", { name: "Shown" })).toBeTruthy();
  });
});

describe("FormRenderer: errors", () => {
  it("lists REQUIRED for blast_standard in the summary; the link focuses the select", async () => {
    const user = userEvent.setup();
    render(<FormRenderer schema={schema} answers={{}} onChange={vi.fn()} mode="submit" showErrors="all" t={tKey} />);

    const summary = screen.getByRole("alert", { name: "forms.renderer.error_summary_title" });
    const link = within(summary).getByRole("link", {
      name: "forms.renderer.error_summary_item{field=Blast standard,message=forms.answer.REQUIRED}",
    });
    await user.click(link);
    expect(document.activeElement).toBe(screen.getByLabelText("Blast standard"));
  });

  it("shows a touched field's error only after blur", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Harness spy={spy} />);
    const dft = screen.getByLabelText("Average dry film thickness");

    await user.type(dft, "0.18");
    expect(spy).toHaveBeenLastCalledWith({ dft_avg: { value: 0.18, unit: "mm" } }, "dft_avg");
    expect(screen.getByText("forms.answer.failed")).toBeTruthy();

    await user.clear(dft);
    await user.type(dft, "abc");
    expect(spy).toHaveBeenLastCalledWith({ dft_avg: { value: "abc", unit: "mm" } }, "dft_avg");
    expect(screen.queryByText("forms.answer.WRONG_TYPE")).toBeNull();

    await user.tab();
    expect(screen.getByText("forms.answer.WRONG_TYPE")).toBeTruthy();
    expect(dft.getAttribute("aria-invalid")).toBe("true");
  });

  it("shows server errors under the field without a blur", () => {
    render(
      <FormRenderer
        schema={schema}
        answers={{ blast_standard: "sa2_5" }}
        onChange={vi.fn()}
        mode="draft"
        t={tKey}
        serverErrors={[{ fieldKey: "blast_standard", code: "NOT_AN_OPTION", messageKey: "forms.answer.NOT_AN_OPTION", params: {} }]}
      />,
    );
    const message = screen.getByText("forms.answer.NOT_AN_OPTION");
    const select = screen.getByLabelText("Blast standard");
    expect(select.getAttribute("aria-describedby")).toContain(message.id);
  });

  it("shows the fail chip and the field's failMessageKey", () => {
    const withMessage: FormSchema = {
      schemaVersion: 1,
      sections: [
        {
          key: "s",
          label: "S",
          fields: [
            {
              key: "dft",
              type: "measurement",
              label: "DFT",
              unit: "mm",
              failWhen: { "<": [{ var: "answers.dft.value" }, 0.25] },
              failMessageKey: "tenant.dft_low",
            },
          ],
        },
      ],
    };
    render(<FormRenderer schema={withMessage} answers={{ dft: { value: 0.1, unit: "mm" } }} onChange={vi.fn()} mode="draft" t={tKey} />);
    expect(screen.getByText("forms.answer.failed")).toBeTruthy();
    expect(screen.getByText("tenant.dft_low")).toBeTruthy();
  });
});

describe("FormRenderer: field types and adapters", () => {
  it("renders an unknown field type as a read-only row without throwing", () => {
    const gps = {
      schemaVersion: 1,
      sections: [{ key: "s", label: "S", fields: [{ key: "where", type: "gps", label: "Where" }] }],
    } as unknown as FormSchema;
    render(<FormRenderer schema={gps} answers={{}} onChange={vi.fn()} mode="draft" t={tKey} />);
    expect(screen.getByText("forms.renderer.unsupported_field{type=gps}")).toBeTruthy();
  });

  it("photo without a media adapter is read-only; with one it adds a thumbnail", async () => {
    const user = userEvent.setup();
    const photoOnly: FormSchema = {
      schemaVersion: 1,
      sections: [{ key: "s", label: "S", fields: [{ key: "photos", type: "photo", label: "Photos" }] }],
    };
    const { unmount } = render(<FormRenderer schema={photoOnly} answers={{}} onChange={vi.fn()} mode="draft" t={tKey} />);
    expect(screen.getByText("forms.renderer.adapter_missing")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    unmount();

    const media: MediaAdapter = {
      pick: vi.fn(async () => ({ fileId: "f1", name: "blast.jpg" })),
      thumbnailUrl: (fileId) => `https://files.test/${fileId}.jpg`,
    };
    const spy: Spy = vi.fn();
    render(<Harness spy={spy} schema={photoOnly} adapters={{ media }} />);
    await user.click(screen.getByRole("button", { name: "forms.renderer.add_photo" }));
    expect(media.pick).toHaveBeenCalledWith("photos", "photo");
    expect(await screen.findByAltText("blast.jpg")).toBeTruthy();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(spy).toHaveBeenLastCalledWith({ photos: [{ fileId: "f1" }] }, "photos");
  });
});

describe("FormRenderer: read-only", () => {
  it("shows every value as text with no controls", () => {
    const { container } = render(
      <FormRenderer schema={schema} answers={fullAnswers} onChange={vi.fn()} mode="submit" readOnly t={tKey} />,
    );
    expect(container.querySelectorAll("input, select, button, textarea")).toHaveLength(0);
    expect(screen.getByText("Sa 2½")).toBeTruthy();
    expect(screen.getByText("2026-10-30")).toBeTruthy();
    expect(screen.getByText("forms.renderer.no")).toBeTruthy();
    expect(screen.getByText("Rust")).toBeTruthy();
    expect(screen.getByText("Oil")).toBeTruthy();
    expect(screen.getByText("forms.answer.failed")).toBeTruthy();
  });
});

describe("FormRenderer: accessibility", () => {
  it("gives every required visible field aria-required and a label", () => {
    const answers: Answers = { surface_prepared: false };
    render(<FormRenderer schema={schema} answers={answers} onChange={vi.fn()} mode="submit" t={tKey} />);
    const evaluation = evaluateAnswers(schema, answers, { mode: "submit" });
    const required = schema.sections
      .flatMap((s) => s.fields)
      .filter((f) => evaluation.required[f.key] === true);
    expect(required.map((f) => f.key)).toEqual(["inspection_date", "surface_prepared", "blast_standard", "dft_avg"]);
    for (const field of required) {
      expect(screen.getByLabelText(field.label).getAttribute("aria-required"), field.key).toBe("true");
    }
    expect(screen.getAllByText("forms.renderer.required")).toHaveLength(required.length);
  });

  const media: MediaAdapter = { pick: async () => null, thumbnailUrl: () => null };
  const references = {
    search: async () => [],
    label: async (_kind: string, id: string) => (id === ASSET ? "PV-101" : "Alice"),
  };
  const adapters: RendererAdapters = { media, references };

  it("editable: 0 serious/critical axe violations", async () => {
    const { container } = render(
      <FormRenderer schema={schema} answers={{ surface_prepared: false }} onChange={vi.fn()} mode="draft" adapters={adapters} t={tKey} />,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("read-only: 0 serious/critical axe violations", async () => {
    const { container } = render(
      <FormRenderer schema={schema} answers={fullAnswers} onChange={vi.fn()} mode="submit" readOnly adapters={adapters} t={tKey} />,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("all errors: 0 serious/critical axe violations", async () => {
    const { container } = render(
      <FormRenderer
        schema={schema}
        answers={{ surface_prepared: false, coats: 9, dft_avg: { value: "abc", unit: "mm" } }}
        onChange={vi.fn()}
        mode="submit"
        showErrors="all"
        adapters={adapters}
        t={tKey}
      />,
    );
    expect(screen.getByText("forms.answer.ABOVE_MAX{max=5}")).toBeTruthy();
    expect(await axeBlocking(container)).toEqual([]);
  });
});
