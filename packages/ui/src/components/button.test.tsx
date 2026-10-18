import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { Button, buttonVariants } from "./button";
import { Icon } from "./icon";

describe("Button", () => {
  it("renders a type=button with variant classes", () => {
    render(<Button variant="secondary">{"Save"}</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button.getAttribute("type")).toBe("button");
    expect(button.className).toContain("aip-button--secondary");
    expect(buttonVariants({ variant: "danger", size: "icon" })).toContain("aip-button--icon");
  });

  it("renders the child element when asChild is set", () => {
    render(
      <Button asChild>
        <a href="/x">{"Open"}</a>
      </Button>,
    );
    expect(screen.getByRole("link", { name: "Open" }).className).toContain("aip-button");
  });

  // DESIGN-08: vitest runs with `css: false`, so load the real stylesheet for this computed-style check.
  it("renders an asChild anchor with no underline and keeps the button classes", () => {
    const style = document.createElement("style");
    style.textContent = readFileSync(fileURLToPath(new URL("./components.css", import.meta.url)), "utf8");
    document.head.append(style);
    try {
      render(
        <Button asChild>
          <a href="/projects/new">{"Create project"}</a>
        </Button>,
      );
      const link = screen.getByRole("link", { name: "Create project" });
      expect(link.className).toContain("aip-button aip-button--primary aip-button--default");
      expect(getComputedStyle(link).textDecoration).toBe("none");
    } finally {
      style.remove();
    }
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(
      <div>
        <Button>{"Save"}</Button>
        <Button size="icon" aria-label="Search">
          <Icon name="search" />
        </Button>
      </div>,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("fails the axe gate when it has no accessible name (proves the gate works)", async () => {
    const { container } = render(
      <Button size="icon">
        <Icon name="search" />
      </Button>,
    );
    const violations = await axeBlocking(container);
    expect(violations.some((v) => v.startsWith("button-name"))).toBe(true);
  });
});
