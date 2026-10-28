import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axeBlocking } from "../test/axe";
import { AipMark, BadgeLockup, EndorsedLockup } from "./brand";

describe("AipMark", () => {
  it("draws a decorative green tile with the letters as paths, never as text", () => {
    const { container } = render(<AipMark size={64} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
    expect(svg?.getAttribute("height")).toBe("64");
    expect(svg?.getAttribute("width")).toBe("64");
    expect(svg?.querySelector("rect")?.getAttribute("fill")).toBe("var(--brand-green)");
    expect(svg?.querySelector("text")).toBeNull();
    expect(svg?.textContent).toBe("");
  });

  it("has a wide tag, a single-letter favicon mark and a tile-less plain tone", () => {
    const { container } = render(
      <>
        <AipMark shape="tag" size={52} />
        <AipMark shape="letter" />
        <AipMark shape="tag" tone="plain" />
      </>,
    );
    const [tag, letter, plain] = container.querySelectorAll("svg");
    expect(tag?.getAttribute("width")).toBe("80");
    expect(letter?.getAttribute("class")).toContain("aip-mark--letter");
    expect(plain?.querySelector("rect")).toBeNull();
    expect(plain?.querySelector("path")?.getAttribute("fill")).toBe("var(--brand-green)");
  });
});

describe("BadgeLockup", () => {
  it("reads as '<Company> AIP' with the company in the tenant brand class", () => {
    render(<BadgeLockup company="Kaefer" product="AIP" companyClassName="x-company" data-testid="lockup" />);
    const lockup = screen.getByTestId("lockup");
    expect(lockup.textContent).toBe("KaeferAIP");
    expect(lockup.querySelector(".aip-lockup__company.x-company")?.textContent).toBe("Kaefer");
    expect(lockup.querySelector(".aip-lockup__product .aip-mark--tag")).not.toBeNull();
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<BadgeLockup company="Kaefer" product="AIP" />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});

describe("EndorsedLockup", () => {
  it("leads with the company and signs off 'Powered by projectAIP'", () => {
    render(
      <EndorsedLockup company="Kaefer" poweredBy="Powered by" platformPrefix="project" product="AIP" data-testid="c" />,
    );
    const lockup = screen.getByTestId("c");
    expect(lockup.firstElementChild?.textContent).toBe("Kaefer");
    expect(lockup.querySelector(".aip-lockup__powered-by")?.textContent).toBe("Powered by");
    expect(lockup.querySelector(".aip-lockup__wordmark .aip-visually-hidden")?.textContent).toBe("projectAIP");
    expect(lockup.querySelectorAll("svg")).toHaveLength(2);
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(
      <EndorsedLockup company="Kaefer" poweredBy="Powered by" platformPrefix="project" product="AIP" />,
    );
    expect(await axeBlocking(container)).toEqual([]);
  });
});
