import { describe, expect, it } from "vitest";
import { canRedo, canUndo, createHistory, HISTORY_LIMIT, push, redo, undo } from "../history";

describe("history", () => {
  it("undoes twice and redoes once to the second state", () => {
    let h = createHistory("s0");
    h = push(h, "s1", { now: 0 });
    h = push(h, "s2", { now: 2000 });
    h = push(h, "s3", { now: 4000 });
    h = undo(undo(h));
    expect(h.present).toBe("s1");
    h = redo(h);
    expect(h.present).toBe("s2");
    expect(canUndo(h)).toBe(true);
    expect(canRedo(h)).toBe(true);
  });

  it("groups typing in one input within a second into one step", () => {
    let h = createHistory("");
    for (const [i, text] of ["a", "ab", "abc", "abcd", "abcde"].entries()) {
      h = push(h, text, { group: "field_1:label", now: i * 200 });
    }
    expect(h.present).toBe("abcde");
    expect(h.past).toEqual([""]);
    expect(undo(h).present).toBe("");
  });

  it("starts a new step after a pause or in another input", () => {
    let h = createHistory("");
    h = push(h, "a", { group: "x", now: 0 });
    h = push(h, "ab", { group: "x", now: 1500 });
    h = push(h, "abc", { group: "y", now: 1600 });
    expect(h.past).toEqual(["", "a", "ab"]);
  });

  it("a new edit clears redo and the stack is capped", () => {
    let h = createHistory(0);
    for (let i = 1; i <= HISTORY_LIMIT + 10; i++) h = push(h, i, { now: i * 5000 });
    expect(h.past.length).toBe(HISTORY_LIMIT);
    h = push(undo(h), 999, { now: 1e9 });
    expect(canRedo(h)).toBe(false);
  });
});
