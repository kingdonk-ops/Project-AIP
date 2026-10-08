# Code provenance log

- **Task:** SECURITY-01 · **Owner:** security programme (`security` module) · **Started:** 2026-10-07
- **Purpose:** show that this codebase is a clean-room build. OpenConstructionERP (AGPL-3.0) is a **feature
  reference only**: no code, schema or text is copied from it. The old AIP codebase is **not used at all**
  (ADR 0001): its code, schema and data are not read or copied, and behaviour comes only from the blueprint text.
- **Enforced:** `tools/ci/check_security_docs.py` (CI `docs` job, `make check-docs`) fails if the table header or
  the AIP row below goes missing.

## How to add an entry

Before anyone (person or agent) looks at OpenConstructionERP or any other copyleft or third-party product for a
feature, add a row first: the date, the feature area, who viewed it, and the statement that no code or schema was
copied. A reviewer other than the viewer initials the row in the PR that adds it. Rows are append-only: correct a
row by adding a new one.

## Log

| Date | Reference area | Viewed by | Statement | Reviewer |
|---|---|---|---|---|
| 2026-10-07 | AIP codebase, schema and data — not read, not copied (ADR 0001); behaviour taken only from the blueprint text | All build agents (standing) | Not read, not copied: no AIP code, schema or data was read, and no code or schema was copied. | KK 2026-10-08 |
| 2026-10-07 | OpenConstructionERP — none viewed yet | — | No OpenConstructionERP source, schema or UI has been viewed by the build; no code or schema was copied. Blueprint module docs only mention it by name as a feature reference. | KK 2026-10-08 |

## Legal advice

Legal advice on the AGPL status of using OpenConstructionERP as a functional reference, including whether
single-tenant on-premise delivery would count as distribution, is **pending**. Reference: `LEGAL-TBD`. Replace this
placeholder with the advice reference and date once received; until then no one views OpenConstructionERP source.
