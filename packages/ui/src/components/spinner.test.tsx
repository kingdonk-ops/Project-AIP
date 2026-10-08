import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Spinner } from "./spinner";

describe("Spinner", () => {
  it("announces its label through a status region", () => {
    render(<Spinner label="Loading" />);
    expect(screen.getByRole("status").textContent).toBe("Loading");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Spinner label="Loading" />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
