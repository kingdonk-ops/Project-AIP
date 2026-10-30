import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { MediaAdapter, ReferenceAdapter, RendererAdapters } from "../adapters";
import { FormRenderer } from "../FormRenderer";
import type { Answers, FormField, FormSchema } from "../logic/types";
import { tKey } from "../test/translate";
import { numericText, parseNumeric } from "./NumberField";
import { fieldComponent, FIELD_COMPONENTS } from "./registry";

function one(field: FormField): FormSchema {
  return { schemaVersion: 1, sections: [{ key: "s", label: "Section", fields: [field] }] };
}

type Spy = ReturnType<typeof vi.fn<(next: Answers, key: string) => void>>;

function Host({
  field,
  spy,
  initial = {},
  adapters,
  readOnly = false,
}: {
  field: FormField;
  spy: Spy;
  initial?: Answers;
  adapters?: RendererAdapters;
  readOnly?: boolean;
}) {
  const [answers, setAnswers] = useState<Answers>(initial);
  return (
    <FormRenderer
      schema={one(field)}
      answers={answers}
      mode="draft"
      t={tKey}
      readOnly={readOnly}
      {...(adapters ? { adapters } : {})}
      onChange={(next, key) => {
        spy(next, key);
        setAnswers(next);
      }}
    />
  );
}

describe("registry", () => {
  it("maps every FORMS-02 field type and nothing else", () => {
    expect(Object.keys(FIELD_COMPONENTS).sort()).toEqual(
      ["asset_ref", "boolean", "date", "decimal", "dropdown", "measurement", "multi_select", "number", "photo", "signature", "text", "user_ref"].sort(),
    );
    expect(fieldComponent("gps")).toBeNull();
    expect(fieldComponent("toString")).toBeNull();
  });
});

describe("numeric parsing", () => {
  it("keeps an unparsable entry as the raw string", () => {
    expect(parseNumeric("")).toBeNull();
    expect(parseNumeric(" 3 ")).toBe(3);
    expect(parseNumeric("0.18")).toBe(0.18);
    expect(parseNumeric("abc")).toBe("abc");
    expect(parseNumeric("Infinity")).toBe("Infinity");
    expect(numericText(null)).toBe("");
    expect(numericText(2)).toBe("2");
  });
});

describe("text", () => {
  it("edits a string, applies maxLength and removes the answer when cleared", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "note", type: "text", label: "Note", validations: { maxLength: 3 } }} />);
    const input = screen.getByRole("textbox", { name: "Note" });
    expect(input.getAttribute("maxlength")).toBe("3");
    await user.type(input, "abcd");
    expect(spy).toHaveBeenLastCalledWith({ note: "abc" }, "note");
    await user.clear(input);
    expect(spy).toHaveBeenLastCalledWith({}, "note");
  });
});

describe("number and decimal", () => {
  it("number uses inputMode numeric and stores a number", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "coats", type: "number", label: "Coats" }} />);
    const input = screen.getByLabelText("Coats");
    expect(input.getAttribute("inputmode")).toBe("numeric");
    await user.type(input, "12");
    expect(spy).toHaveBeenLastCalledWith({ coats: 12 }, "coats");
  });

  it("decimal keeps the typed text while typing (0. → 0.5)", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "rh", type: "decimal", label: "RH" }} />);
    const input = screen.getByLabelText("RH");
    expect(input.getAttribute("inputmode")).toBe("decimal");
    await user.type(input, "0.5");
    expect((input as HTMLInputElement).value).toBe("0.5");
    expect(spy).toHaveBeenLastCalledWith({ rh: 0.5 }, "rh");
  });

  it("an unparsable number shows WRONG_TYPE after blur", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "coats", type: "number", label: "Coats" }} />);
    await user.type(screen.getByLabelText("Coats"), "two");
    expect(spy).toHaveBeenLastCalledWith({ coats: "two" }, "coats");
    await user.tab();
    expect(screen.getByText("forms.answer.WRONG_TYPE")).toBeTruthy();
  });
});

describe("date", () => {
  it("is a native date input storing YYYY-MM-DD unchanged", async () => {
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "on", type: "date", label: "On" }} initial={{ on: "2026-03-01" }} />);
    const input = screen.getByLabelText("On") as HTMLInputElement;
    expect(input.type).toBe("date");
    expect(input.value).toBe("2026-03-01");
  });

  it("read-only shows the date as given", () => {
    render(<Host spy={vi.fn()} readOnly field={{ key: "on", type: "date", label: "On" }} initial={{ on: "2026-03-01" }} />);
    expect(screen.getByText("2026-03-01")).toBeTruthy();
  });
});

describe("dropdown and multi_select", () => {
  const options = [
    { value: "sa2", label: "Sa 2" },
    { value: "sa3", label: "Sa 3", labelKey: "tenant.sa3" },
  ];

  it("dropdown shows the stored option's label (labelKey wins)", () => {
    render(<Host spy={vi.fn()} field={{ key: "b", type: "dropdown", label: "Blast", options }} initial={{ b: "sa3" }} />);
    expect(screen.getByLabelText("Blast").textContent).toContain("tenant.sa3");
  });

  it("multi_select toggles checkboxes in option order inside a nested fieldset", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "d", type: "multi_select", label: "Defects", options }} />);
    const group = screen.getByRole("group", { name: "Defects" });
    expect(group.tagName).toBe("FIELDSET");
    await user.click(screen.getByRole("checkbox", { name: "tenant.sa3" }));
    await user.click(screen.getByRole("checkbox", { name: "Sa 2" }));
    expect(spy).toHaveBeenLastCalledWith({ d: ["sa2", "sa3"] }, "d");
    await user.click(screen.getByRole("checkbox", { name: "Sa 2" }));
    await user.click(screen.getByRole("checkbox", { name: "tenant.sa3" }));
    expect(spy).toHaveBeenLastCalledWith({}, "d");
  });

  it("multi_select read-only lists the option labels", () => {
    render(<Host spy={vi.fn()} readOnly field={{ key: "d", type: "multi_select", label: "Defects", options }} initial={{ d: ["sa2"] }} />);
    expect(screen.getByRole("listitem").textContent).toBe("Sa 2");
  });
});

describe("measurement", () => {
  it("shows the unit symbol term and stores {value, unit}", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "t", type: "measurement", label: "Temp", unit: "degC" }} />);
    expect(screen.getByText("forms.unit.degC")).toBeTruthy();
    await user.type(screen.getByLabelText("Temp"), "-4.5");
    expect(spy).toHaveBeenLastCalledWith({ t: { value: -4.5, unit: "degC" } }, "t");
  });

  it("read-only shows value and unit", () => {
    render(
      <Host spy={vi.fn()} readOnly field={{ key: "t", type: "measurement", label: "Temp", unit: "bar" }} initial={{ t: { value: 3, unit: "bar" } }} />,
    );
    expect(screen.getByText("3 forms.unit.bar")).toBeTruthy();
  });
});

describe("boolean", () => {
  it("keeps not-answered distinct from no", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} field={{ key: "ok", type: "boolean", label: "OK" }} />);
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((r) => r.checked)).toEqual([false, false]);
    await user.click(screen.getByLabelText("forms.renderer.yes"));
    expect(spy).toHaveBeenLastCalledWith({ ok: true }, "ok");
  });

  it("read-only without an answer says not answered", () => {
    render(<Host spy={vi.fn()} readOnly field={{ key: "ok", type: "boolean", label: "OK" }} />);
    expect(screen.getByText("forms.renderer.not_answered")).toBeTruthy();
  });
});

describe("photo and signature", () => {
  const media: MediaAdapter = {
    pick: vi.fn(async (_key: string, kind: "photo" | "signature") =>
      kind === "photo" ? { fileId: "p1", name: "flange.jpg" } : { fileId: "s1", name: "signature.png" },
    ),
    thumbnailUrl: (fileId) => `https://files.test/${fileId}`,
  };

  it("removes a photo with its remove button", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} adapters={{ media }} field={{ key: "ph", type: "photo", label: "Photos" }} />);
    await user.click(screen.getByRole("button", { name: "forms.renderer.add_photo" }));
    await user.click(await screen.findByRole("button", { name: "forms.renderer.remove_photo{name=flange.jpg}" }));
    expect(spy).toHaveBeenLastCalledWith({}, "ph");
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("signs, shows the file name, and clears", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    render(<Host spy={spy} adapters={{ media }} field={{ key: "sig", type: "signature", label: "Signature" }} />);
    await user.click(screen.getByRole("button", { name: "forms.renderer.sign" }));
    expect(media.pick).toHaveBeenCalledWith("sig", "signature");
    expect(await screen.findByText("signature.png")).toBeTruthy();
    expect(spy).toHaveBeenLastCalledWith({ sig: { fileId: "s1" } }, "sig");
    await user.click(screen.getByRole("button", { name: "forms.renderer.clear_signature" }));
    expect(spy).toHaveBeenLastCalledWith({}, "sig");
    expect(screen.getByRole("button", { name: "forms.renderer.sign" })).toBeTruthy();
  });

  it("signature without a media adapter is read-only", () => {
    render(<Host spy={vi.fn()} field={{ key: "sig", type: "signature", label: "Signature" }} />);
    expect(screen.getByText("forms.renderer.adapter_missing")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("read-only photos are thumbnails", () => {
    render(
      <Host spy={vi.fn()} readOnly adapters={{ media }} field={{ key: "ph", type: "photo", label: "Photos" }} initial={{ ph: [{ fileId: "p9" }] }} />,
    );
    expect(screen.getByRole("img").getAttribute("src")).toBe("https://files.test/p9");
  });
});

describe("asset_ref and user_ref", () => {
  const ASSET = "6f1c2a1e-0000-4000-8000-000000000001";

  function refs(): ReferenceAdapter & { search: ReturnType<typeof vi.fn>; label: ReturnType<typeof vi.fn> } {
    return {
      search: vi.fn(async (_kind: string, query: string) =>
        query ? [{ id: ASSET, label: "PV-101 Pressure vessel" }] : [],
      ),
      label: vi.fn(async (_kind: string, id: string) => (id === ASSET ? "PV-101 Pressure vessel" : null)),
    };
  }

  it("searches through the adapter (debounced) and stores the chosen id", async () => {
    const user = userEvent.setup();
    const spy: Spy = vi.fn();
    const references = refs();
    render(<Host spy={spy} adapters={{ references }} field={{ key: "asset", type: "asset_ref", label: "Asset" }} />);
    const input = screen.getByRole("combobox", { name: "Asset" });
    expect(input.getAttribute("placeholder")).toBe("forms.renderer.search_placeholder");
    await user.type(input, "PV");
    await waitFor(() => expect(references.search).toHaveBeenCalledWith("asset", "PV"));
    expect(references.search).toHaveBeenCalledTimes(1);
    await user.click(await screen.findByRole("option", { name: "PV-101 Pressure vessel" }));
    expect(spy).toHaveBeenLastCalledWith({ asset: ASSET }, "asset");
  });

  it("shows references.label for the stored id, in both modes", async () => {
    const references = refs();
    const { unmount } = render(
      <Host spy={vi.fn()} adapters={{ references }} field={{ key: "asset", type: "asset_ref", label: "Asset" }} initial={{ asset: ASSET }} />,
    );
    await waitFor(() => expect((screen.getByRole("combobox") as HTMLInputElement).value).toBe("PV-101 Pressure vessel"));
    unmount();
    render(
      <Host spy={vi.fn()} readOnly adapters={{ references }} field={{ key: "who", type: "user_ref", label: "Who" }} initial={{ who: ASSET }} />,
    );
    expect(await screen.findByText("PV-101 Pressure vessel")).toBeTruthy();
    expect(references.label).toHaveBeenLastCalledWith("user", ASSET);
  });

  it("a required reference field carries aria-required on its input", async () => {
    render(
      <Host spy={vi.fn()} adapters={{ references: refs() }} field={{ key: "asset", type: "asset_ref", label: "Asset", required: true }} />,
    );
    await waitFor(() => expect(screen.getByRole("combobox").getAttribute("aria-required")).toBe("true"));
  });

  it("without a references adapter the field is read-only", () => {
    render(<Host spy={vi.fn()} field={{ key: "asset", type: "asset_ref", label: "Asset" }} />);
    expect(screen.getByText("forms.renderer.adapter_missing")).toBeTruthy();
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});
