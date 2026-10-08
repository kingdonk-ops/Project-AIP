import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Icon, iconNames } from "./icon";

describe("Icon", () => {
  it("is decorative (aria-hidden) without a label", () => {
    const { container } = render(<Icon name="alert" />);
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("is a named image with a label", () => {
    render(<Icon name="warning" label="Warning" />);
    expect(screen.getByRole("img", { name: "Warning" })).toBeTruthy();
  });

  it("renders every registered icon with no serious or critical axe violations", async () => {
    const { container } = render(
      <div>
        {iconNames.map((name) => (
          <Icon key={name} name={name} label={name} />
        ))}
      </div>,
    );
    expect(container.querySelectorAll("svg")).toHaveLength(iconNames.length);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
