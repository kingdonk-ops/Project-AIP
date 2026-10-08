import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Badge, badgeVariants } from "./badge";

describe("Badge", () => {
  it("renders its children with the tone class", () => {
    render(<Badge tone="accent">{"3"}</Badge>);
    expect(screen.getByText("3").className).toContain("aip-badge--accent");
    expect(badgeVariants()).toContain("aip-badge--neutral");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Badge tone="outline">{"Draft"}</Badge>);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
