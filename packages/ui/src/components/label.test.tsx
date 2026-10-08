import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Input } from "./input";
import { Label } from "./label";

describe("Label", () => {
  it("labels its control", () => {
    render(
      <div>
        <Label htmlFor="email">{"Email"}</Label>
        <Input id="email" />
      </div>,
    );
    expect(screen.getByLabelText("Email").id).toBe("email");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(
      <div>
        <Label htmlFor="email">{"Email"}</Label>
        <Input id="email" />
      </div>,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });
});
