import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import { KPI_MAX_TILES, KpiStrip, type KpiTile } from "./KpiStrip";

function Strip({ onFilter }: { onFilter?: (on: boolean) => void }) {
  const [overdueOnly, setOverdueOnly] = useState(false);
  const tiles: KpiTile[] = [
    { id: "mine", labelKey: "home.kpi.mine", value: 12, icon: "user" },
    {
      id: "overdue",
      labelKey: "home.kpi.overdue",
      value: 3,
      tone: "danger",
      icon: "alert",
      hintKey: "home.kpi.overdue.hint",
      pressed: overdueOnly,
      onSelect: () => {
        setOverdueOnly((v) => !v);
        onFilter?.(!overdueOnly);
      },
    },
    { id: "holds", labelKey: "home.kpi.holds", value: 2, tone: "warning", icon: "shield" },
    { id: "spend", labelKey: "home.kpi.spend", icon: "folder", restricted: true, onSelect: () => {} },
    { id: "extra", labelKey: "home.kpi.extra", value: 1, icon: "info" },
  ];
  return <KpiStrip tiles={tiles} labelKey="home.kpi.label" translate={tKey} />;
}

describe("KpiStrip", () => {
  it("renders at most four tiles in a named list", () => {
    render(<Strip />);
    const list = screen.getByRole("list", { name: "home.kpi.label" });
    expect(list.querySelectorAll("li")).toHaveLength(KPI_MAX_TILES);
    expect(screen.queryByText("home.kpi.extra")).toBeNull();
    expect(screen.getByText("12")).toBeTruthy();
  });

  it("toggles a filter tile and exposes its pressed state", async () => {
    const onFilter = vi.fn();
    render(<Strip onFilter={onFilter} />);
    const tile = screen.getByRole("button", { name: /home\.kpi\.overdue/ });
    expect(tile.getAttribute("aria-pressed")).toBe("false");
    await userEvent.click(tile);
    expect(tile.getAttribute("aria-pressed")).toBe("true");
    expect(onFilter).toHaveBeenCalledWith(true);
  });

  it("shows the restricted term and no number for a tile the user may not see, and is not a toggle", () => {
    render(<Strip />);
    const tile = screen.getByText("home.kpi.spend").closest(".aip-kpi__tile");
    expect(tile?.getAttribute("data-restricted")).toBe("true");
    expect(tile?.textContent).toContain("ui.kpi.restricted");
    expect(tile?.querySelector(".aip-kpi__number")).toBeNull();
    expect(tile?.tagName).toBe("DIV");
  });

  it("colours the danger number and icon, not the tile", () => {
    render(<Strip />);
    const value = screen.getByText("3").closest(".aip-kpi__value");
    expect(value?.className).toContain("aip-kpi__value--danger");
    expect(value?.closest(".aip-kpi__tile")?.className).not.toContain("danger");
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Strip />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
