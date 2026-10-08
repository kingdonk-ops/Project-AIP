import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { Button } from "./button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./dropdown-menu";

function Fixture({ onSelect }: { onSelect: () => void }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button>{"Actions"}</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>{"Record"}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={onSelect}>{"Approve"}</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem>{"Archive"}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

describe("DropdownMenu", () => {
  it("opens from the keyboard and runs the selected item", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Fixture onSelect={onSelect} />);
    screen.getByRole("button", { name: "Actions" }).focus();
    await user.keyboard("{Enter}");
    const menu = screen.getByRole("menu");
    expect(menu.className).toContain("aip-menu__content");
    await user.click(screen.getByRole("menuitem", { name: "Approve" }));
    expect(onSelect).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("has no serious or critical axe violations when open", async () => {
    const user = userEvent.setup();
    render(<Fixture onSelect={() => {}} />);
    screen.getByRole("button", { name: "Actions" }).focus();
    await user.keyboard("{Enter}");
    expect(await axeBlocking(screen.getByRole("menu"))).toEqual([]);
  });
});
