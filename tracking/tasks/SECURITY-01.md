# SECURITY-01 — Threat model and AGPL provenance log
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | XS |
| Depends on | — |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (AIP not used), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (sandboxed workers), [0005](../../docs/adr/0005-identity-architecture.md) (credentials and sessions), [0006](../../docs/adr/0006-per-tenant-envelope-keys.md) (tenant keys)
4. Only if a step needs it: [`docs/reviews/01-security.md`](../../docs/reviews/01-security.md)

## Spec

Record the threat model and clean-room provenance before schema design. The provenance log also records that no AIP code, schema or data was read (ADR 0001).

- **files**:
  - docs/security/threat-model.md
  - docs/security/provenance-log.md
  - tools/ci/check_security_docs.py (stdlib-only Python; this task has no dependency on the uv workspace)
  - tools/ci/test_check_security_docs.py (stdlib `unittest`)
- **steps**:
  - 1. Write `threat-model.md` with one `## ` section per threat area, using these exact headings: `## Field PIN and magic link`, `## Portal`, `## Inbound email and webhooks`, `## Legal records`, `## AI`, `## File uploads and sandboxed workers`. Each section has `### Assets`, `### Threats (STRIDE)`, `### Controls` and `### Residual risk`. Controls cite the ADR they rely on: opaque `__Host-` cookie sessions, device-bound key + PIN, single-use POST-confirmed magic links and separate portal origin (ADR 0005); RLS with `set_config('app.tenant_id', ..., true)` (ADR 0002); one-shot sandbox containers with no egress, non-root, read-only FS and CPU/memory/time caps (ADR 0003); per-tenant KMS key on every upload (ADR 0006).
  - 2. Write `provenance-log.md` with a table `| Date | Reference area | Viewed by | Statement | Reviewer |`. The statement column says no code or schema was copied.
  - 3. Add one row per OpenConstructionERP feature area used as a reference so far (or one row stating "none viewed yet" dated today).
  - 4. Add a standing row for AIP: "AIP codebase, schema and data — not read, not copied (ADR 0001); behaviour taken only from the blueprint text".
  - 5. Add a note that legal advice on AGPL status is pending, with a placeholder reference `LEGAL-TBD`.
  - 6. Write `tools/ci/check_security_docs.py`: it checks both files exist, that `threat-model.md` has all six required `## ` headings each with the four `### ` subheadings, and that `provenance-log.md` has the table header and an AIP row. It prints one line per missing item and exits 1 if any are missing.
  - 7. If `.github/workflows/ci.yml` exists, add `python3 tools/ci/check_security_docs.py` to its `docs` job; otherwise leave a note in the PR for ARCH-03/STACK-01.
- **acceptance**:
  - Both docs are in the repo.
  - The check fails, naming the area, if any of the six threat areas or any of their four subsections is missing.
  - The provenance log states that AIP was not used.
- **tests**:
  - **unit**:
    - The heading parser on the committed `threat-model.md` returns the 6 required area headings in order.
    - The heading parser on a string with `## AI` but no `### Residual risk` beneath it reports `AI: missing "Residual risk"`.
  - **integration**:
    - Remove the `## AI` heading in a temp copy and run the check. Expected: exit 1 and output `threat-model.md: missing section "AI"`.
    - Remove the AIP row from a temp copy of `provenance-log.md`. Expected: exit 1 and output `provenance-log.md: missing AIP non-use row`.
    - Run on the committed files. Expected: exit 0.
  - **e2e**:
    - CI `docs` job passes on main.
