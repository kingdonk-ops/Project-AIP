# Twenty CRM — metadata engine & record-list UX (external reference)

**Date:** 2026-10-30
**Status:** Reference only. Design inspiration, not a dependency and not a source of code.

## Licence boundary (read first)

[Twenty](https://github.com/twentyhq/twenty) core is **AGPL-3.0** (with ~240 server
files under a separate commercial licence). AIP is a proprietary multi-tenant SaaS, so
Twenty sits in the **same bucket as OpenConstructionERP**: a *feature reference only — copy
no code from it* (see `AGENTS.md` hard rules and `docs/blueprint/modules/item_types/README.md`).
Patterns and ideas may be read and re-expressed in our own Python/TypeScript, proven by our
own tests. Source files, components, schemas and assets may **not** be copied, vendored or forked
into this repo. Twenty's backend is NestJS/TypeScript — the stack ADR 0001 explicitly rejects —
so there is nothing to lift server-side regardless.

## Why this is a reference, not a task

The "tenant-configurable asset types, checklist fields and form attributes" capability Twenty's
metadata engine is admired for **is already designed and largely built in AIP**, and it is a
closer fit to our domain than Twenty's generic CRM objects. Do **not** implement a second
metadata engine.

| Capability | Twenty | AIP — already built | Where |
|---|---|---|---|
| User-defined object kinds | custom objects | **Content types** + item categories + item types | ITEMTYPES-01 (PR #133) |
| User-defined fields, treated like built-in | custom fields | **Shared field-type registry**; JSONB attribute schema | ITEMTYPES-01 |
| Stored in Postgres, per-tenant isolation | Postgres | **JSONB attributes**, every table `tenant_id` + FORCE RLS | ITEMTYPES-01/02, ASSETS-02 |
| Schema evolution | field edits | **Immutable versioned schemas** (draft → publish → pin), migration preview with impact counts | ITEMTYPES-02 (PR #151) |
| Typed values validated | field types | Server-side validation against the **effective schema**, units & tolerances | ITEMTYPES-02, ASSETS-02 (PR #160) |
| No-code builder for forms | — | **Form/template designer**, revisions frozen as JSONB + schema hash | FORMS-01 (PR #143) |
| Shared logic engine | — | **JSONLogic evaluator**, Python + TS on the same golden vectors | FORMS-02 (PR #149) |
| Per-tenant labels | — | **Terminology keys** (every type/field name is tenant-renamable) | TERMS-01/03 |

AIP additionally has capabilities Twenty does not: type inheritance, sandboxed
calculated/conditional attributes with a function allow-list, custom status sets mapped to
neutral lifecycle states, and measurement units/tolerances feeding the rules engine. The
metadata engine is **more capable here, not less**.

## Reference item 1 — metadata-driven custom fields/objects

AIP's model already covers the substance. The only ideas worth *keeping in mind* from Twenty as
the remaining admin/UX tasks land (all re-expressed from scratch, never copied):

- **One field-type registry shared by every consumer.** Twenty treats a field identically
  wherever it appears. AIP already does this (`item_types` and `forms` share one registry) —
  keep that invariant; resist per-feature field-type forks.
- **Schema-driven typed client.** Twenty regenerates a typed client when the schema changes.
  AIP's equivalent is `packages/api-client` + `packages/contracts`; keep attribute/field
  contracts flowing through there so web code stays typed against the published schema.

Nothing here is actionable as new backend work. If a gap is found, it belongs on the board as an
`item_types`/`forms` task with its own spec — not folded into something else.

## Reference item 2 — record-list UX & extensibility model

This is where Twenty is genuinely useful as **design inspiration** for the web app and client
portal, mapped to live/todo tasks:

- **Views, filters and saved views** (Twenty's list/table/kanban + per-view filters) →
  informs **ASSETS-03** (`/assets` register with filters and saved views) and the generated
  per-content-type register pages. Reference the *interaction model* (column choice, filter
  chips, saved view switching), build on our own `RegisterTable` (DESIGN-03).
- **Attribute editing UX** → **ITEMTYPES-03** (`/admin/content-types`). **Caveat:** ADR 0007
  defers a visual attribute **designer** for R1; the task ships a JSON attribute editor beside a
  **read-only** field preview. Twenty's two-pane live-preview *designer* is therefore a
  **post-R1** reference, not an R1 target. Do not pull it forward.
- **Form rendering** → **FORMS-03** (`packages/form-renderer`). Our renderer is contract-driven
  from frozen revisions; Twenty's field-component mapping is only a loose reference.
- **Sandboxed third-party UI** (Twenty's Remote DOM in Web Workers) → relevant **only** if AIP
  ever allows tenant/third-party UI extensions. Not in current scope. Note the pattern exists;
  no action.

## Actionable follow-ups (already on the board — this note creates none)

- `ITEMTYPES-03` (todo) — content/item-type admin pages (JSON editor + read-only preview)
- `ITEMTYPES-04` (todo) — expiry-date flags, scoped reference attributes
- `ASSETS-03` (todo) — asset tree + register with generated forms, filters, saved views
- `FORMS-03/04/06` (todo) — renderer, register/detail, option sets & section library
- `ITEMTYPES-05/06` (blocked) — custom status sets, starter packs (OPEN-QUESTIONS #40/#41)

Work these through the normal loop (`python3 tools/next_task.py`), one task per branch/PR. Use
this note as a UX reference during the web tasks; it changes no architecture and supersedes no ADR.
