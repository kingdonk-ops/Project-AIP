import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { axeBlocking } from "../test/axe";
import { tKey } from "../test/translate";
import { QUEUE_MAX_ACTIONS, WorkQueue, dueTag, type WorkQueueItem } from "./WorkQueue";

const NOW = new Date("2026-11-04T09:00:00Z");
const hoursFromNow = (h: number) => new Date(NOW.getTime() + h * 3_600_000).toISOString();

const approve = vi.fn();
const items: WorkQueueItem[] = [
  {
    id: "ITP-0042",
    title: "Coating hold point",
    snippet: "DFT below spec on 2 readings",
    assetPath: "Karratha › Train 2 › P-101",
    due: hoursFromNow(-3),
    status: { tone: "warning", icon: "clock", labelKey: "inspection.state.supervisor_review" },
    actions: [
      { id: "approve", labelKey: "queue.approve", onSelect: approve },
      { id: "reject", labelKey: "queue.reject", onSelect: () => {} },
      { id: "assign", labelKey: "queue.assign", onSelect: () => {} },
      { id: "extra", labelKey: "queue.extra", onSelect: () => {} },
    ],
  },
  { id: "INS-0101", title: "Insulation check", due: hoursFromNow(5), status: { tone: "info", icon: "loader", labelKey: "s.in_progress" } },
  { id: "INS-0102", title: "Lagging repair", due: hoursFromNow(72), status: { tone: "neutral", icon: "clock", labelKey: "s.assigned" } },
  { id: "INS-0103", title: "Cladding survey", due: hoursFromNow(-60), status: { tone: "danger", icon: "alert", labelKey: "s.rework" } },
  { id: "RFI-0007", title: "Clarify paint system", status: { tone: "neutral", icon: "info", labelKey: "s.draft" } },
  { id: "INS-0104", title: "Valve box", assetPath: "Karratha › Train 1", status: { tone: "success", icon: "check", labelKey: "s.performed" } },
  { id: "ITP-0043", title: "Surface prep witness", due: hoursFromNow(1), status: { tone: "info", icon: "shield", labelKey: "s.review" } },
  { id: "INS-0105", title: "Heat tracing", due: hoursFromNow(30), status: { tone: "neutral", icon: "clock", labelKey: "s.assignable" } },
];

function Queue({ onOpen = vi.fn() }: { onOpen?: (id: string) => void }) {
  const [tab, setTab] = useState("mine");
  return (
    <WorkQueue
      items={items}
      onOpen={onOpen}
      labelKey="home.queue"
      translate={tKey}
      now={NOW}
      tabs={[
        { id: "mine", labelKey: "home.queue.mine", count: 8 },
        { id: "team", labelKey: "home.queue.team" },
      ]}
      activeTab={tab}
      onTabChange={setTab}
    />
  );
}

describe("dueTag", () => {
  it("uses hours under 48 and days after, and flags overdue", () => {
    expect(dueTag(hoursFromNow(-3), NOW)).toEqual({ overdue: true, key: "ui.queue.overdue", params: { hours: 3 } });
    expect(dueTag(hoursFromNow(5), NOW)).toEqual({ overdue: false, key: "ui.queue.dueIn", params: { hours: 5 } });
    expect(dueTag(hoursFromNow(72), NOW)).toEqual({ overdue: false, key: "ui.queue.dueInDays", params: { days: 3 } });
    expect(dueTag(hoursFromNow(-60), NOW).key).toBe("ui.queue.overdueDays");
  });
});

describe("WorkQueue", () => {
  it("renders 8 rows; an item due 3h ago says overdue by 3h with the danger icon", () => {
    render(<Queue />);
    const list = screen.getByRole("list", { name: "home.queue" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(8);
    const due = screen.getByText("ui.queue.overdue{hours=3}");
    expect(due.tagName).toBe("TIME");
    const tag = due.closest(".aip-queue__due");
    expect(tag?.className).toContain("aip-queue__due--overdue");
    expect(tag?.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("names each row by its id and title, and opens it with Enter or a click", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<Queue onOpen={onOpen} />);
    const row = screen.getByRole("button", { name: /^ITP-0042 Coating hold point/ });
    row.focus();
    await user.keyboard("{Enter}");
    expect(onOpen).toHaveBeenCalledWith("ITP-0042");
    await user.click(screen.getByRole("button", { name: /^RFI-0007/ }));
    expect(onOpen).toHaveBeenLastCalledWith("RFI-0007");
  });

  it("shows up to three quick actions named for their item", async () => {
    render(<Queue />);
    const row = screen.getByRole("button", { name: /^ITP-0042/ }).closest("li") as HTMLElement;
    const actions = within(row).getAllByRole("button").filter((b) => !b.className.includes("aip-queue__open"));
    expect(actions).toHaveLength(QUEUE_MAX_ACTIONS);
    await userEvent.click(within(row).getByRole("button", { name: "ui.queue.action{action=queue.approve,item=ITP-0042}" }));
    expect(approve).toHaveBeenCalled();
  });

  it("switches filter tabs with the arrow keys", async () => {
    const user = userEvent.setup();
    render(<Queue />);
    const mine = screen.getByRole("tab", { name: /home\.queue\.mine/ });
    expect(mine.getAttribute("aria-selected")).toBe("true");
    mine.focus();
    await user.keyboard("{ArrowRight}");
    const team = screen.getByRole("tab", { name: "home.queue.team" });
    expect(team.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(team);
    expect(screen.getByRole("tabpanel", { name: "home.queue.team" })).toBeTruthy();
  });

  it("shows the empty term with no items", () => {
    render(<WorkQueue items={[]} onOpen={() => {}} labelKey="home.queue" translate={tKey} />);
    expect(screen.getByText("ui.queue.empty")).toBeTruthy();
  });

  it("has no serious or critical axe violations", async () => {
    const { container } = render(<Queue />);
    expect(await axeBlocking(container)).toEqual([]);
  });
});
