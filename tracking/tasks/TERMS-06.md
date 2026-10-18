# TERMS-06 — Term aliases for import column matching (re-scoped into data_io)

<!-- hand-edited: re-scoped by PLAN-R1 (2026-10-18): moved from P0 into R1 for data_io imports (ADR 0007 §3), rewritten for the Python backend (ADR 0001), narrowed to import aliases (ADR 0036 §6) -->
<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | R1 |
| Size | S |
| Depends on | DATAIO-01, TERMS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. ADRs: [0028](../../docs/adr/0028-platform-tenant-rows.md) (platform rows readable by every tenant), [0036](../../docs/adr/0036-r1-module-decisions.md) §6 (why this is narrowed)
4. [`DATAIO-01.md`](DATAIO-01.md): the column-mapping step this feeds
5. The code: `apps/api/aip/modules/terms/tables.py` (`term_alias`), `repository.py`, `api.py`, and the TERMS-01 migration `apps/api/migrations/versions/202610141200_terms_tables.py`

## Spec

Let an import map a spreadsheet header such as "Deficiency" or " PUNCH ITEM " to a neutral field code through the
tenant's and the platform's term aliases, so data_io's column mapping can suggest matches and report the columns it
could not match (tag: extend).

Glossary tooltips and search-query expansion are out of scope: they wait for a search module (ADR 0036 §6). The
`term_alias` and `glossary_entry` tables already exist (TERMS-01), so this task has no migration.

- **files**:
  - apps/api/aip/modules/terms/aliases.py
  - apps/api/aip/modules/terms/repository.py
  - apps/api/aip/modules/terms/schemas.py
  - apps/api/aip/modules/terms/routes.py
  - apps/api/aip/modules/terms/api.py
  - apps/api/aip/modules/terms/manifest.toml
  - config/terms/en-AU/aliases.json
  - apps/api/aip/modules/terms/tests/test_aliases.py
  - apps/api/aip/modules/terms/tests/test_aliases_db.py
- **steps**:
  - 1. `aliases.py`: `normalise(text)` folds case (`casefold`), applies NFKC, trims and collapses inner whitespace.
    `map_headers(columns, aliases, targets)` is pure: for each column it returns `{column, target_code | None,
    via: "exact" | "alias" | None}`, matching a column against the target codes first and then the aliases, both
    normalised. Unmatched columns are returned with `target_code: None`, never dropped. Two columns mapping to
    the same target both keep it and are flagged `duplicate: true`.
  - 2. `repository.py`: `aliases_for(conn, target_type, locale)` reads `term_alias` rows for the bound tenant plus
    the platform tenant (ADR 0028); a tenant row with the same normalised alias wins over the platform row.
  - 3. `api.py` exports `resolve_alias(conn, text, *, namespace, locale="en-AU") -> str | None` and
    `map_headers(conn, columns, *, namespace, targets, locale="en-AU") -> list[HeaderMatch]`, where `namespace` is
    the `target_type` (e.g. `asset.field`). data_io calls these through `aip.modules.terms.api` only.
  - 4. Tenant alias admin: `GET /api/v1/terms/aliases?namespace=` (`terms.alias.view`), `POST /api/v1/terms/aliases`
    `{alias, namespace, targetCode, locale}` and `DELETE /api/v1/terms/aliases/{id}` (`terms.alias.manage`, soft
    delete). A duplicate normalised alias in the same namespace and locale gives 409 `ALIAS_EXISTS`. Declare both
    permissions in `manifest.toml`. Strict request bodies (unknown keys → 422, as ADR 0035 §6).
  - 5. Seed platform aliases from `config/terms/en-AU/aliases.json` through the TERMS-01 loader path (platform rows
    are written only by `aip_owner`): `Deficiency`, `Punch`, `Punch item` → `issue.title` in namespace
    `issue.field`; `Tag`, `Tag No`, `Tag Number` → `tag_number` in namespace `asset.field`.
- **acceptance**:
  - `map_headers` for `[" DEFICIENCY ", "Due", "Colour"]` in namespace `issue.field` with targets
    `["issue.title", "due"]` returns `issue.title` (alias), `due` (exact) and an unmatched `Colour`.
  - A `kaefer-demo` alias never applies to `tenant-b`; platform aliases apply to both.
  - Only holders of `terms.alias.manage` can add or delete aliases; deletes are soft.
- **tests**:
  - **unit** (`test_aliases.py`):
    - `normalise("  Tag   No ")` → `"tag no"`.
    - `map_headers(["Tag Number"], aliases={"tag number": "tag_number"}, targets=["tag_number", "name"])` →
      `[{column: "Tag Number", target_code: "tag_number", via: "alias"}]`.
    - `map_headers(["name", "NAME"], aliases={}, targets=["name"])` → both `target_code: "name"`, both `duplicate: true`.
    - `map_headers(["Colour"], aliases={}, targets=["name"])` → `target_code: None`, `via: None`.
  - **integration** (`test_aliases_db.py`, Testcontainers Postgres, TESTING-01 fixtures):
    - With the seed loaded, `resolve_alias(conn, "punch item", namespace="issue.field")` as `kaefer-demo` →
      `"issue.title"`.
    - `kaefer-demo` POSTs alias `Defect ref` → `issue.title`; as `tenant-b`, `resolve_alias(conn, "Defect ref",
      namespace="issue.field")` → `None`, and `SELECT count(*) FROM term_alias WHERE alias = 'Defect ref'` as
      `tenant-b` → 0.
    - A tenant alias `Punch` → `issue.description` overrides the platform `Punch` → `issue.title` for that tenant
      only.
    - POST the same alias twice → second call 409 `ALIAS_EXISTS`; a viewer without `terms.alias.manage` → 403 and
      no new `term_alias` row.
  - **e2e**:
    - Covered by DATAIO-03's import wizard journey once it uses `map_headers` for its suggested mapping; this task
      ships no page.
