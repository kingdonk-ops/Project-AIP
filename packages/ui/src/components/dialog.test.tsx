import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Button } from "./button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "./dialog";

function Fixture() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button>{"Delete record"}</Button>
      </DialogTrigger>
      <DialogContent closeLabel="Close">
        <DialogTitle>{"Delete NCR-12?"}</DialogTitle>
        <DialogDescription>{"This cannot be undone."}</DialogDescription>
        <DialogClose asChild>
          <Button variant="secondary">{"Cancel"}</Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}

describe("Dialog", () => {
  it("opens, moves focus inside, closes on Escape and returns focus to the trigger", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    const trigger = screen.getByRole("button", { name: "Delete record" });
    await user.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "Delete NCR-12?" });
    expect(dialog.contains(document.activeElement)).toBe(true);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("names the corner close button from a prop", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    await user.click(screen.getByRole("button", { name: "Delete record" }));
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("has no serious or critical axe violations when open", async () => {
    const user = userEvent.setup();
    render(<Fixture />);
    await user.click(screen.getByRole("button", { name: "Delete record" }));
    expect(await axeBlocking(screen.getByRole("dialog"))).toEqual([]);
  });
});
