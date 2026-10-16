import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import { ConfirmProvider, confirm, useConfirm, type ConfirmOptions } from "./confirm";

const danger: ConfirmOptions = {
  titleKey: "ncr.delete.title",
  bodyKey: "ncr.delete.body",
  confirmKey: "ncr.delete.confirm",
  tone: "danger",
};

function open(options: ConfirmOptions): Promise<boolean> {
  let result!: Promise<boolean>;
  act(() => {
    result = confirm(options);
  });
  return result;
}

describe("confirm", () => {
  it("rejects when no ConfirmProvider is mounted", async () => {
    await expect(confirm(danger)).rejects.toThrow(/ConfirmProvider/);
  });

  it("danger: focus starts on Cancel and Escape resolves false", async () => {
    const user = userEvent.setup();
    render(<ConfirmProvider translate={tKey} />);
    const result = open(danger);

    const dialog = await screen.findByRole("dialog", { name: "ncr.delete.title" });
    expect(dialog.textContent).toContain("ncr.delete.body");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "ui.confirm.cancel" }));

    await user.keyboard("{Escape}");
    await expect(result).resolves.toBe(false);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("clicking Confirm resolves true; Cancel resolves false", async () => {
    const user = userEvent.setup();
    render(<ConfirmProvider translate={tKey} />);

    const yes = open({ ...danger, tone: "default" });
    await user.click(await screen.findByRole("button", { name: "ncr.delete.confirm" }));
    await expect(yes).resolves.toBe(true);

    const no = open(danger);
    await user.click(await screen.findByRole("button", { name: "ui.confirm.cancel" }));
    await expect(no).resolves.toBe(false);
  });

  it("requireText keeps Confirm disabled until the code is typed", async () => {
    const user = userEvent.setup();
    render(<ConfirmProvider translate={tKey} />);
    const result = open({ ...danger, requireText: "L592" });

    const confirmButton = await screen.findByRole("button", { name: "ncr.delete.confirm" });
    expect(confirmButton).toHaveProperty("disabled", true);
    const input = screen.getByRole("textbox", { name: "ui.confirm.requireText{text=L592}" });
    await user.type(input, "L59");
    expect(confirmButton).toHaveProperty("disabled", true);
    await user.type(input, "2");
    expect(confirmButton).toHaveProperty("disabled", false);
    await user.click(confirmButton);
    await expect(result).resolves.toBe(true);
  });

  it("a second request cancels the open one", async () => {
    render(<ConfirmProvider translate={tKey} />);
    const first = open(danger);
    open({ ...danger, titleKey: "second" });
    await expect(first).resolves.toBe(false);
    expect(await screen.findByRole("dialog", { name: "second" })).toBeTruthy();
  });

  it("useConfirm returns the provider's confirm", async () => {
    const user = userEvent.setup();
    let resolved: boolean | undefined;
    function Delete() {
      const ask = useConfirm();
      return (
        <button type="button" onClick={() => void ask(danger).then((v) => (resolved = v))}>
          {"Delete"}
        </button>
      );
    }
    render(
      <ConfirmProvider translate={tKey}>
        <Delete />
      </ConfirmProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(await screen.findByRole("button", { name: "ncr.delete.confirm" }));
    expect(resolved).toBe(true);
  });

  it("has no serious or critical axe violations when open", async () => {
    render(<ConfirmProvider translate={tKey} />);
    void open({ ...danger, requireText: "L592" });
    expect(await axeBlocking(await screen.findByRole("dialog"))).toEqual([]);
  });
});
