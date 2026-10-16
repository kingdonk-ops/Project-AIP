import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import { WorkflowBar } from "./WorkflowBar";

const steps = [
  { id: "draft", labelKey: "ncr.step.draft" },
  { id: "review", labelKey: "ncr.step.review" },
  { id: "closed", labelKey: "ncr.step.closed" },
];

describe("WorkflowBar", () => {
  it("marks the current step and shows the passed-in actions", async () => {
    const approve = vi.fn();
    const reject = vi.fn();
    const { container } = render(
      <WorkflowBar
        steps={steps}
        current="review"
        actions={[
          { id: "approve", labelKey: "ncr.action.approve", onSelect: approve },
          { id: "reject", labelKey: "ncr.action.reject", onSelect: reject, tone: "danger" },
        ]}
        translate={tKey}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.dataset.state)).toEqual(["done", "current", "todo"]);
    expect(items[1]?.getAttribute("aria-current")).toBe("step");
    await userEvent.click(screen.getByRole("button", { name: "ncr.action.reject" }));
    expect(reject).toHaveBeenCalledOnce();
    expect(approve).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "ncr.action.reject" }).className).toContain("aip-button--danger");
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("shows no actions when none are allowed", () => {
    render(<WorkflowBar steps={steps} current="closed" actions={[]} translate={tKey} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
