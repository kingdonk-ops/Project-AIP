#!/usr/bin/env python3
"""Split the monolithic product blueprint into small, agent-sized files.

Usage: python3 tools/split_blueprint.py <path-to-product-blueprint.md>

Re-running overwrites generated files under docs/blueprint/ and
tracking/tasks/<ID>.md for blueprint tasks. tracking/BOARD.md is
hand-maintained and never touched by this script.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BP = ROOT / "docs" / "blueprint"
TASKS = ROOT / "tracking" / "tasks"

REMOVED = {"cost_items", "cases"}  # owner removed these modules

SUBFILES = {
    "Architecture & code structure": "architecture.md",
    "Data model & schema": "data-model.md",
    "Page & layout designer": "ui-layout.md",
    "Feature scout": "features-market.md",
    "Feature filler": "features-access.md",
    "Security advisor": "advice-security.md",
    "Tech stack advisor": "advice-stack.md",
}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def split_on(lines, pattern):
    """Return [(heading_line_or_None, body_lines)] split at lines matching pattern."""
    chunks, head, cur = [], None, []
    for ln in lines:
        if re.match(pattern, ln):
            if head is not None or cur:
                chunks.append((head, cur))
            head, cur = ln, []
        else:
            cur.append(ln)
    chunks.append((head, cur))
    return chunks


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def parse_phases(build):
    phases, mods, in_mods = [], [], False
    for ln in build:
        if re.match(r"\s+- \*\*modules\*\*:", ln):
            in_mods, mods = True, []
            continue
        if in_mods:
            mm = re.match(r"\s{6}- (\w+)$", ln)
            if mm:
                mods.append(mm.group(1))
                continue
            in_mods = False
        m = re.match(r"\s+- \*\*name\*\*: (P\d) (.*)", ln)
        if m:
            phases.append({"id": m.group(1), "name": m.group(2), "modules": mods})
    return phases


def main(src):
    lines = Path(src).read_text().splitlines()
    shutil.rmtree(BP, ignore_errors=True)  # fully generated; safe to rebuild
    sections = {(h[3:].strip() if h else "_pre"): b for h, b in split_on(lines, r"^## ")}

    def sec(prefix):
        return next(v for k, v in sections.items() if k.startswith(prefix))

    build = sec("Build order")
    phases = parse_phases(build)
    module_phase = {m: p["id"] for p in phases for m in p["modules"]}

    # Top-level reference files
    write(BP / "00-brief.md", "# Brief\n\n" + "\n".join(sec("Brief")))
    write(BP / "01-decisions.md",
          "# Owner decisions\n\n"
          "> Owner decisions override advisor text anywhere else in the blueprint.\n"
          "> Conflicts *between* decisions are resolved in `docs/adr/` — check there first.\n\n"
          + "\n".join(sec("Decisions")))
    write(BP / "02-advisor-summaries.md", "# Advisor summaries\n\n"
          "> Background only. Where advisors disagree with `01-decisions.md`, the decision wins.\n\n"
          + "\n".join(sec("Advisor summaries")))
    write(BP / "03-site-hierarchy.md", "# Site hierarchy (navigation)\n\n" + "\n".join(sec("Site hierarchy")))
    write(BP / "04-code-layout.md",
          "# Folders, files and shared code\n\n"
          "> WARNING: this section was written for the Python/FastAPI AIP codebase. The owner chose a\n"
          "> TypeScript rebuild (NestJS + Next.js). Map Python files to the TypeScript module template\n"
          "> from task ARCH-01 (`apps/api/src/modules/<name>/`). See `docs/adr/0001-*.md`.\n\n"
          + "\n".join(sec("Folders, files")))
    write(BP / "05-access-matrix.md", "# Accounts, profiles and access matrix\n\n" + "\n".join(sec("Accounts, profiles")))
    bo = "\n".join(build)
    ci = bo.find("- **task conventions**")
    write(BP / "06-build-order.md", "# Build order and phases\n\n" + bo[:ci])
    write(BP / "07-task-conventions.md",
          "# Task conventions (definition of done)\n\n"
          "Every agent follows these on every task. Where a line conflicts with an ADR in `docs/adr/`, "
          "the ADR wins (e.g. migrations are TypeScript, not Alembic — ADR 0002).\n\n" + bo[ci:])

    # Modules
    mod_index, name_to_id = [], {}
    for ghead, gbody in split_on(sec("Modules"), r"^### "):
        if not ghead:
            continue
        group = ghead[4:].strip()
        for mhead, mbody in split_on(gbody, r"^#### "):
            if not mhead:
                continue
            title, mid = re.match(r"#### (.*) \(`(\w+)`\)", mhead).groups()
            name_to_id[title] = mid
            phase = "removed" if mid in REMOVED else module_phase.get(mid, "unphased")
            mod_index.append((group, mid, title, phase))
            d = BP / "modules" / mid
            overview, produced = [], []
            for phead, pbody in split_on(mbody, r"^\*\*[^*]+\*\*$"):
                if phead is None:
                    overview = pbody
                    continue
                key = phead.strip("*")
                fn = SUBFILES.get(key, slug(key) + ".md")
                write(d / fn, f"# {title} — {key}\n\n" + "\n".join(pbody))
                produced.append((fn, key))
            produced.append(("routes.md", "Page specs: routes, sections, actions, access"))
            head = (f"# {title} (`{mid}`)\n\n- **Group:** {group}\n- **Phase:** {phase}\n"
                    + ("\n> **REMOVED by owner. Do not build. Strip any hooks that reference it.**\n"
                       if mid in REMOVED else "") + "\n")
            files = "\n\n## Other files in this folder (read only if your task needs them)\n\n" + "\n".join(
                f"- [`{fn}`]({fn}) — {k}" for fn, k in produced)
            write(d / "README.md", head + "\n".join(overview).strip() + files)

    # Pages grouped by owning module
    pages = {}
    for phead, pbody in split_on(sec("Pages"), r"^### "):
        if not phead:
            continue
        m = re.match(r"### .*? `[^`]*` \((.*)\)$", phead)
        owner = m.group(1) if m else "global"
        mid = "_global" if owner == "global" else name_to_id.get(owner, slug(owner))
        pages.setdefault(mid, []).append("#" + phead + "\n" + "\n".join(pbody).rstrip())
    for mid, pg in pages.items():
        if mid == "_global":
            write(BP / "pages-global.md", "# Global pages (auth, shell, profile, errors)\n\n" + "\n\n".join(pg))
        else:
            write(BP / "modules" / mid / "routes.md", f"# Page specs for `{mid}`\n\n" + "\n\n".join(pg))

    # Tasks
    tasks = []
    for thead, tbody in split_on(sec("Tasks"), r"^### "):
        if not thead:
            continue
        tid, ttitle, mname, size = re.match(
            r"### ([A-Z]+-\d+) (.*) \((.*), (XS|S|M|L|XL)\)", thead).groups()
        mid = name_to_id.get(mname, slug(mname))
        body = "\n".join(tbody).strip()
        deps = re.findall(r"^  - ([A-Z_]+-\d+)$", body.split("- **files**")[0], re.M)
        phase = module_phase.get(mid, "?")
        tasks.append(dict(id=tid, title=ttitle, module=mid, size=size, deps=deps, phase=phase))
        out = TASKS / f"{tid}.md"
        if out.exists() and "hand-" in out.read_text()[:400]:
            continue  # marked hand-written / hand-edited: keep the curated version
        write(out,
              f"# {tid} — {ttitle}\n\n"
              "| Field | Value |\n|---|---|\n"
              f"| Module | [`{mid}`](../../docs/blueprint/modules/{mid}/README.md) |\n"
              f"| Phase | {phase} |\n| Size | {size} |\n"
              f"| Depends on | {', '.join(deps) or '—'} |\n"
              "| Status | tracked in [BOARD.md](../BOARD.md) |\n\n"
              "## Read before starting (and nothing else unless blocked)\n\n"
              "1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)\n"
              f"2. [`docs/blueprint/modules/{mid}/README.md`](../../docs/blueprint/modules/{mid}/README.md)\n"
              "3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module\n"
              "4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder\n\n"
              "## Spec\n\n" + body + "\n")

    # Index
    order = {p["id"]: i for i, p in enumerate(phases)}
    idx = ["# Blueprint index", "",
           "The original 2.5 MB blueprint, split so an agent only reads what its current task needs.", "",
           "## Reference files (read on demand)", "", "| File | Read when |", "|---|---|",
           "| [00-brief.md](00-brief.md) | Product context: audience, compliance, scale |",
           "| [01-decisions.md](01-decisions.md) | Choosing a library or approach (owner decisions win) |",
           "| [02-advisor-summaries.md](02-advisor-summaries.md) | Background rationale only |",
           "| [03-site-hierarchy.md](03-site-hierarchy.md) | Building navigation or the app shell |",
           "| [04-code-layout.md](04-code-layout.md) | Creating a module folder (Python-era, see warning) |",
           "| [05-access-matrix.md](05-access-matrix.md) | Adding roles or permissions |",
           "| [06-build-order.md](06-build-order.md) | Phase goals and exit criteria |",
           "| [07-task-conventions.md](07-task-conventions.md) | **Every task**: definition of done |",
           "| [pages-global.md](pages-global.md) | Auth, shell, profile and error pages |", "",
           "## Modules (by phase)", "", "| Phase | Module | Group | Folder |", "|---|---|---|---|"]
    for g, mid, title, ph in sorted(mod_index, key=lambda x: (order.get(x[3], 99), x[0], x[1])):
        idx.append(f"| {ph} | {title} | {g} | [`modules/{mid}/`](modules/{mid}/README.md) |")
    write(BP / "INDEX.md", "\n".join(idx))
    return phases, mod_index, tasks


if __name__ == "__main__":
    phases, mods, tasks = main(sys.argv[1])
    (ROOT / "tracking" / ".generated.json").write_text(
        json.dumps({"phases": phases, "modules": mods, "tasks": tasks}, indent=1) + "\n")
    print(f"{len(phases)} phases, {len(mods)} modules, {len(tasks)} tasks")
