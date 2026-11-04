import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { Button } from "../components/button";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import { BLADE_PARAM, Blade, readBladeParam, useBladeParam, writeBladeParam } from "./Blade";

/** A queue row that opens the blade through the URL, as a page would wire it. */
function Harness() {
  const [openId, setOpenId] = useBladeParam();
  const row = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={row} type="button" onClick={() => setOpenId("ITP-0042")}>
        ITP-0042 Coating hold point
      </button>
      <Blade
        open={openId !== null}
        onOpenChange={(open) => !open && setOpenId(null)}
        recordId={openId ?? ""}
        title="Coating hold point"
        breadcrumb={<span>Karratha › Train 2 › P-101</span>}
        status={{ tone: "warning", icon: "clock", labelKey: "inspection.state.supervisor_review" }}
        permalink={`/inspections/${openId}`}
        banner={{ tone: "danger", icon: "alert", text: "Overdue by 3h" }}
        actions={<Button>Approve</Button>}
        translate={tKey}
      >
        <p>Answers</p>
        <Button variant="secondary">Raise issue</Button>
      </Blade>
    </>
  );
}

afterEach(() => window.history.replaceState(null, "", "/"));

describe("Blade URL helpers", () => {
  it("reads and writes ?open= keeping other parameters", () => {
    expect(BLADE_PARAM).toBe("open");
    expect(readBladeParam("?state=draft&open=ITP-0042")).toBe("ITP-0042");
    expect(readBladeParam("?state=draft")).toBeNull();
    expect(writeBladeParam("?state=draft", "ITP-0042")).toBe("?state=draft&open=ITP-0042");
    expect(writeBladeParam("?open=ITP-0042", null)).toBe("");
  });
});

describe("Blade", () => {
  it("opens from ?open=ITP-0042 with its header, banner, body and action bar", () => {
    window.history.replaceState(null, "", "/inspections?open=ITP-0042");
    render(<Harness />);
    const blade = screen.getByRole("dialog", { name: "Coating hold point" });
    expect(blade.getAttribute("data-record")).toBe("ITP-0042");
    expect(screen.getByText("ITP-0042", { selector: ".aip-blade__id" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Overdue by 3h");
    expect(screen.getByRole("link", { name: "ui.blade.permalink" }).getAttribute("href")).toBe("/inspections/ITP-0042");
    expect(screen.getByText("inspection.state.supervisor_review")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("traps focus, closes on Escape, restores focus to the row and drops ?open=", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/inspections?state=draft");
    render(<Harness />);
    const row = screen.getByRole("button", { name: "ITP-0042 Coating hold point" });
    row.focus();
    await user.keyboard("{Enter}");
    const blade = screen.getByRole("dialog", { name: "Coating hold point" });
    expect(window.location.search).toBe("?state=draft&open=ITP-0042");
    expect(blade.contains(document.activeElement)).toBe(true);
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(blade.contains(document.activeElement)).toBe(true);
    }
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    // The hook went Back over the entry it pushed; jsdom applies the traversal asynchronously.
    await waitFor(() => expect(window.location.search).toBe("?state=draft"));
    expect(document.activeElement).toBe(row);
  });

  it("closes with its close button and replaces the URL when it was opened by link", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/inspections?open=ITP-0042");
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "ui.close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(window.location.search).toBe("");
  });

  it("has no serious or critical axe violations when open", async () => {
    window.history.replaceState(null, "", "/inspections?open=ITP-0042");
    render(<Harness />);
    expect(await axeBlocking(document.body)).toEqual([]);
  });
});
