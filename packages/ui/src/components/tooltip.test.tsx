import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Button } from "./button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./tooltip";

function Fixture({ open }: { open: boolean }) {
  return (
    <TooltipProvider>
      <Tooltip open={open}>
        <TooltipTrigger asChild>
          <Button>{"Sync"}</Button>
        </TooltipTrigger>
        <TooltipContent>{"Last synced 2 minutes ago"}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

describe("Tooltip", () => {
  it("shows its content as a tooltip described by the trigger", () => {
    render(<Fixture open />);
    const tip = screen.getByRole("tooltip");
    expect(tip.textContent).toContain("Last synced 2 minutes ago");
    expect(screen.getByRole("button", { name: "Sync" }).getAttribute("aria-describedby")).toBe(tip.id);
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Fixture open={false} />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
