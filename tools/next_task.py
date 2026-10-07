#!/usr/bin/env python3
"""Pick the next task from tracking/BOARD.md, or validate the board.

  python3 tools/next_task.py            # print the next ready task and its read-list
  python3 tools/next_task.py --all      # list every ready task (for parallel agents)
  python3 tools/next_task.py --check    # validate the board (CI)

A task is *ready* when its status is `todo` and every dependency is `done`
(or `dropped`). Order follows the board top to bottom.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "tracking" / "BOARD.md"
STATUSES = {"todo", "in-progress", "review", "done", "blocked", "dropped"}
TASK_ID = r"[A-Z][A-Z0-9]*-\d+[a-z]?"
ROW = re.compile(r"^\|\s*\[?(" + TASK_ID + r")\]?(?:\([^)]*\))?\s*\|(.*)\|\s*$")


def parse():
    tasks = []
    for n, line in enumerate(BOARD.read_text().splitlines(), 1):
        m = ROW.match(line)
        if not m:
            continue
        # Columns after ID: Title | Module | Size | Depends on | Status | PR / notes
        title, module, size, deps, status = [c.strip() for c in m.group(2).split("|")][:5]
        tasks.append(dict(id=m.group(1), title=title, module=module.strip("`"), size=size,
                          deps=re.findall(TASK_ID, deps), status=status.strip("`* ").lower(), line=n))
    return tasks


def ready(tasks):
    closed = {t["id"] for t in tasks if t["status"] in ("done", "dropped")}
    return [t for t in tasks if t["status"] == "todo" and all(d in closed for d in t["deps"])]


def check(tasks):
    errs, seen = [], {}
    for t in tasks:
        if t["id"] in seen:
            errs.append(f"duplicate id {t['id']} (lines {seen[t['id']]} and {t['line']})")
        seen[t["id"]] = t["line"]
        if t["status"] not in STATUSES:
            errs.append(f"{t['id']}: unknown status '{t['status']}'")
        if not (ROOT / "tracking" / "tasks" / f"{t['id']}.md").exists():
            errs.append(f"{t['id']}: missing tracking/tasks/{t['id']}.md")
        if not (ROOT / "docs" / "blueprint" / "modules" / t["module"]).is_dir():
            errs.append(f"{t['id']}: unknown module '{t['module']}'")
    for t in tasks:
        errs += [f"{t['id']}: depends on unknown task {d}" for d in t["deps"] if d not in seen]
    for e in errs:
        print("ERROR:", e)
    print(f"{len(tasks)} tasks checked, {len(errs)} errors")
    return 1 if errs else 0


def main():
    if not BOARD.exists():
        print("WARNING: tracking/BOARD.md does not exist yet; nothing to check or pick.")
        return
    tasks = parse()
    if "--check" in sys.argv:
        sys.exit(check(tasks))
    r = ready(tasks)
    if not r:
        busy = [t["id"] for t in tasks if t["status"] in ("in-progress", "review", "blocked")]
        print("No ready tasks. In flight or blocked:", ", ".join(busy) or "none")
        return
    if "--all" in sys.argv:
        for t in r:
            print(f"{t['id']:<14} {t['title']}  [{t['module']}, {t['size']}]")
        return
    t = r[0]
    print(f"{t['id']}  {t['title']}  [{t['module']}, {t['size']}]\n\nRead, in order:")
    print(f"  1. tracking/tasks/{t['id']}.md")
    print("  2. docs/blueprint/07-task-conventions.md")
    print(f"  3. docs/blueprint/modules/{t['module']}/README.md")
    print(f"  4. docs/adr/ entries mentioning {t['id']} or {t['module']}")


if __name__ == "__main__":
    main()
