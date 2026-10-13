# OPS-16 — RDS bootstrap runbook and the web hosting decision

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`ops`](../../docs/blueprint/modules/ops/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | DATABASE-02 (board is authoritative) |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/ops/README.md`](../../docs/blueprint/modules/ops/README.md)
3. ADRs: 0002, 0012 (roles in the cluster bootstrap), 0004 (SPAs on S3 + CloudFront)
4. `db/bootstrap/00_cluster.sql`

## Spec

Write the "RDS bootstrap runbook" that `db/bootstrap/00_cluster.sql` refers to, and settle with the
owner where the web app is served in AWS, before OPS-07 builds it.

- **files**:
  - docs/runbooks/rds-bootstrap.md
  - docs/adr/00NN-web-hosting-on-aws.md (only if the owner changes ADR 0004)
- **steps**:
  - 1. Runbook: create the RDS instance with the parameter group from OPS-07, connect as the RDS master
    user (which has `rds_superuser`, not `SUPERUSER`), create the `aip` and `keycloak` databases, read the
    role passwords from Secrets Manager, and run `00_cluster.sql` with SCRAM verifiers (or with logging
    off, as the file says). Then run `aip-db migrate` as `aip_owner`.
  - 2. Prove on a real RDS instance (or note what differs) that `CREATE EXTENSION vector`, the role
    flags and the `REVOKE CONNECT` lines work as `rds_superuser`, and that the platform-roles revision's
    privilege check passes.
  - 3. Web hosting: the owner's production service list puts the web app behind the ALB on Fargate;
    ADR 0004 and OPS-07 say S3 + CloudFront with `/api/*` sent to the ALB. Ask the owner, record the
    answer in `tracking/OPEN-QUESTIONS.md`, and if it changes ADR 0004, write the superseding ADR and
    update OPS-07's step 3.
- **acceptance**:
  - Someone who has not seen the repo can bootstrap an empty RDS instance by following the runbook.
  - The web hosting choice is recorded and OPS-07 matches it.
- **tests**:
  - **integration**:
    - Run `00_cluster.sql` as a non-superuser role holding `CREATEROLE` and owning the database (the
      closest local stand-in for `rds_superuser`). Expected: it completes, or the runbook lists each
      statement that needs the RDS master user.
