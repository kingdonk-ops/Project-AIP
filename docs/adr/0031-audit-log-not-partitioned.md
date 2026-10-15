# ADR 0031: audit_log is not range-partitioned; monthly segments are logical

- **Status:** accepted
- **Date:** 2026-10-15
- **Affects:** audit (AUDIT-01, AUDIT-03, AUDIT-05); database (DATABASE-05)

## Context

DATABASE-05 lists `audit_log` among the append-only evidence tables and suggests each uses
`db/templates/append_only_table.sql.tpl`, which range-partitions a table by month and keys it on
`(id, <partition_column>)`.

AUDIT-01 also requires, for the tamper-evident hash chain, a table-wide `UNIQUE (tenant_id, stream,
seq)` (gap-free per-tenant sequence) and a partial `UNIQUE (tenant_id, source_event_id)` (so
redelivery from the outbox is idempotent via `ON CONFLICT`). PostgreSQL requires every unique
index on a partitioned table to include all partition-key columns. Neither of these uniques
includes a month/time column, so they cannot exist on a table partitioned by `occurred_at` (or any
time column). The two requirements are mutually exclusive.

ADR 0021 asks that the chain be "sealed in monthly segments" so old segments can be removed under
retention without breaking verification, and that deletion be done by a retention job (AUDIT-05),
not an S3 expiry rule or a partition drop.

## Decision

`audit_log` is a **plain (non-partitioned)** append-only table with a surrogate `id uuid` primary
key, carrying the two unique constraints above. It is modelled on the append-only template's
*controls* — fail-closed `NULLIF` RLS policy, `FORCE ROW LEVEL SECURITY`, `REVOKE
UPDATE/DELETE/TRUNCATE` from `PUBLIC` and every role, and a `BEFORE UPDATE OR DELETE` trigger — but
written as raw SQL in the revision rather than rendered from the template, and it is not registered
in `partition_settings`.

The "monthly segments" of ADR 0021 are **logical**: they are recorded in `audit_chain_checkpoints`
`(tenant_id, stream, segment, last_seq, last_hash)`, one row per `YYYY-MM`. Verification can start
from any checkpoint, so the AUDIT-05 retention job removes an old segment by deleting that month's
rows (keeping its checkpoint), and the remainder still verifies. Removal is a privileged operation
that lifts the append-only trigger for the delete; it is never available to a runtime role.

`audit_chain_heads` and `audit_chain_checkpoints` are writer-maintained bookkeeping keyed on
natural columns, an intentional exception to the uuid-PK convention. All three tables keep
`tenant_id` and `FORCE ROW LEVEL SECURITY`.

## Consequences

- The hash chain's integrity and idempotency guarantees are enforceable in the database, not only
  in the application.
- `audit_log` does not get automatic monthly partition pruning; the AUDIT-05 retention job deletes
  by segment instead, which it must do anyway to honour legal holds (ADR 0021 point 5).
- DATABASE-05's "use the append-only template" guidance does not apply to `audit_log`; the other
  evidence tables it lists (for example `inspection_responses`, `activity`) still use the template,
  as they have no table-wide uniqueness requirement.
- The soft-delete convention does not apply to `audit_log` (no `deleted_at`): a correction is a new
  superseding row, recorded in `tables.py` and the revision.
