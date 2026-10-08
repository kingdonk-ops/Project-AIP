import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { statusTones } from "../tokens/tokens";
import { axeBlocking } from "../test/axe";
import { StatusChip } from "./status-chip";

describe("StatusChip", () => {
  it("renders a hidden icon plus visible text, never colour alone", () => {
    const { container } = render(<StatusChip tone="danger" icon="alert" label="Rejected" />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByText("Rejected")).toBeTruthy();
    expect(container.firstElementChild?.getAttribute("data-tone")).toBe("danger");
  });

  it("has no serious or critical axe violations for every tone", async () => {
    const { container } = render(
      <div>
        {statusTones.map((tone) => (
          <StatusChip key={tone} tone={tone} icon="info" label={tone} />
        ))}
      </div>,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });
});
