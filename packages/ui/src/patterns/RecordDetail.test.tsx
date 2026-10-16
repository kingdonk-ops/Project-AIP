import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import { DEFAULT_RECORD_TABS, RecordDetail, type RecordDetailProps } from "./RecordDetail";

const tabs: RecordDetailProps["tabs"] = [
  { id: "details", content: "Details body" },
  { id: "linked", content: "Linked body" },
  { id: "documents", content: "Documents body" },
  { id: "history", content: "History body" },
];

function renderDetail(props: Partial<RecordDetailProps> = {}) {
  return render(
    <RecordDetail
      id="NCR-0042"
      title="Cracked lagging on line 12"
      breadcrumb={<span>{"Plant / Unit 2"}</span>}
      status={{ tone: "warning", icon: "warning", labelKey: "ncr.status.open" }}
      tabs={tabs}
      rightRail={{ comments: "Comments body", approvals: "Approvals body", attachments: "Attachments body" }}
      actions={<button type="button">{"Edit"}</button>}
      translate={tKey}
      {...props}
    />,
  );
}

describe("RecordDetail", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/ncr/42");
    sessionStorage.clear();
  });
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("shows the id in mono, the title, breadcrumb, status and actions", async () => {
    const { container } = renderDetail();
    expect(screen.getByText("NCR-0042").className).toContain("aip-record__id");
    expect(screen.getByRole("heading", { level: 1, name: "Cracked lagging on line 12" })).toBeTruthy();
    expect(screen.getByText("Plant / Unit 2")).toBeTruthy();
    expect(screen.getByText("ncr.status.open")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy();
    expect(await axeBlocking(container)).toEqual([]);
  });

  it("lists the default tab ids in order", () => {
    expect(DEFAULT_RECORD_TABS).toEqual(["details", "linked", "documents", "history"]);
  });

  it("?tab=history renders the History panel selected", () => {
    window.history.replaceState(null, "", "/ncr/42?tab=history");
    renderDetail();
    const tablist = screen.getByRole("tablist", { name: "ui.record.tabs" });
    const history = within(tablist).getByRole("tab", { name: "ui.record.tab.history" });
    expect(history.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel", { name: "ui.record.tab.history" }).textContent).toBe("History body");
    expect(screen.queryByText("Details body")).toBeNull();
  });

  it("selecting a tab writes it to the URL; arrow keys move between tabs", async () => {
    const user = userEvent.setup();
    renderDetail();
    expect(screen.getByRole("tab", { name: "ui.record.tab.details" }).getAttribute("aria-selected")).toBe("true");

    await user.click(screen.getByRole("tab", { name: "ui.record.tab.documents" }));
    expect(new URLSearchParams(window.location.search).get("tab")).toBe("documents");
    expect(screen.getByText("Documents body")).toBeTruthy();

    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "ui.record.tab.history" }));
    expect(new URLSearchParams(window.location.search).get("tab")).toBe("history");
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "ui.record.tab.details" }));
    await user.keyboard("{End}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "ui.record.tab.history" }));
    await user.keyboard("{Home}");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "ui.record.tab.details" }));
  });

  it("is controlled when `tab` and `onTabChange` are given", async () => {
    const onTabChange = vi.fn();
    renderDetail({ tab: "linked", onTabChange });
    expect(screen.getByRole("tab", { name: "ui.record.tab.linked" }).getAttribute("aria-selected")).toBe("true");
    await userEvent.click(screen.getByRole("tab", { name: "ui.record.tab.history" }));
    expect(onTabChange).toHaveBeenCalledWith("history");
    expect(window.location.search).toBe("");
  });

  it("an unknown ?tab falls back to the first tab; custom tabs keep their label key", () => {
    window.history.replaceState(null, "", "/ncr/42?tab=nope");
    renderDetail({ tabs: [{ id: "checks", labelKey: "itp.tab.checks", content: "Checks body" }] });
    expect(screen.getByRole("tab", { name: "itp.tab.checks" }).getAttribute("aria-selected")).toBe("true");
  });

  it("the right rail collapses and the choice is kept for the session", async () => {
    const user = userEvent.setup();
    const first = renderDetail();
    expect(screen.getByRole("complementary", { name: "ui.record.rail" }).textContent).toContain("Comments body");
    const toggle = screen.getByRole("button", { name: "ui.record.rail.hide" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    await user.click(toggle);
    expect(screen.queryByText("Comments body")).toBeNull();
    expect(screen.getByRole("button", { name: "ui.record.rail.show" }).getAttribute("aria-expanded")).toBe("false");

    first.unmount();
    renderDetail();
    expect(screen.queryByText("Comments body")).toBeNull();
  });

  it("superseded records show a Superseded chip and a link to the replacement", () => {
    renderDetail({ superseded: { byId: "NCR-0050", href: "/ncr/50" } });
    expect(screen.getByText("ui.record.superseded")).toBeTruthy();
    expect(screen.getByRole("link", { name: "ui.record.supersededBy{id=NCR-0050}" }).getAttribute("href")).toBe("/ncr/50");
  });

  it("renders the workflow bar when given", () => {
    renderDetail({
      workflow: {
        steps: [
          { id: "open", labelKey: "ncr.step.open" },
          { id: "closed", labelKey: "ncr.step.closed" },
        ],
        current: "open",
        actions: [{ id: "close", labelKey: "ncr.action.close", onSelect: () => {} }],
      },
    });
    expect(screen.getByRole("navigation", { name: "ui.workflow.label" })).toBeTruthy();
  });
});
