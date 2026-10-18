# ISSUES-01 — Issues and NCR basics: issue types, severities and issues on an approvals workflow

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`issues`](../../docs/blueprint/modules/issues/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | APPROVALS-08, ASSETS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/issues/README.md`](../../docs/blueprint/modules/issues/README.md) ("Features", "Decisions and notes") and [`data-model.md`](../../docs/blueprint/modules/issues/data-model.md) (`issue_types`, `issue_severities`, the `issues` columns in "notes")
3. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (SQLAlchemy Core, raw-SQL Alembic, `with_tenant`), [0003](../../docs/adr/0003-jobs-outbox-and-sidecar.md) (outbox in the same transaction), [0004](../../docs/adr/0004-repository-layout.md) (`config/workflows/`, only `api.py` crosses modules), [0025](../../docs/adr/0025-time-and-timezones.md) (point 5: calendar-day dates are UTC), [0027](../../docs/adr/0027-default-role-permission-expansion.md) (permission verbs), [0035](../../docs/adr/0035-transition-service-implementation.md) (how the transition service, guards and record resolvers really work), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 decisions)
4. [`APPROVALS-08.md`](APPROVALS-08.md) (the preset installer and exported evaluator) and [`APPROVALS-05.md`](APPROVALS-05.md) steps 1 and 5 only: how a workflow preset ships as JSON in `config/workflows/`
5. Code to copy patterns from: `apps/api/aip/modules/projects/` (module layout, tests, conftest), `apps/api/aip/modules/approvals/api.py` and `guards/context_providers.py`

> **Dependency note.** The preset installer (`ApprovalsApi.install_preset`) and the exported guard evaluator come
> from APPROVALS-08 (a dependency of this row). Never write a definition installer inside issues: approvals owns
> definitions, and `DefinitionsService` is not part of its published interface.

## Spec

Create the `issues` module with admin-configurable issue types and severities and issues raised against an asset, whose lifecycle runs on a shipped `issue` workflow preset through `ApprovalsApi`, with an independent verifier enforced by a JSONLogic guard (tag: extend).

Out of scope: raise rules and auto-raise (ISSUES-02); NCR details and the ITP hold flag (ISSUES-03); pages
(ISSUES-04); CAPA (ISSUES-05); root cause (ISSUES-06, OPEN-QUESTIONS #46); `responsible_company_id` and portal
scoping (no portal in R1); overdue notifications.

- **files**:
  - apps/api/migrations/versions/<timestamp>_issues_core.py
  - apps/api/aip/modules/issues/__init__.py
  - apps/api/aip/modules/issues/manifest.toml
  - apps/api/aip/modules/issues/tables.py
  - apps/api/aip/modules/issues/schemas.py
  - apps/api/aip/modules/issues/repository.py
  - apps/api/aip/modules/issues/service.py
  - apps/api/aip/modules/issues/workflow.py
  - apps/api/aip/modules/issues/policies.py
  - apps/api/aip/modules/issues/events.py
  - apps/api/aip/modules/issues/routes.py
  - apps/api/aip/modules/issues/api.py
  - apps/api/aip/modules/issues/tests/__init__.py
  - apps/api/aip/modules/issues/tests/conftest.py
  - apps/api/aip/modules/issues/tests/test_unit.py
  - apps/api/aip/modules/issues/tests/test_issues_db.py
  - apps/api/aip/modules/issues/tests/test_issue_workflow.py
  - config/workflows/issue.standard.json
  - config/issues/defaults.json
  - config/terms/en-AU/issues.json
- **steps**:
  - 1. Scaffold with `python tools/new_module.py issues`. `manifest.toml`: `id = "issues"`, `context = "issues"`,
    `depends_on = ["access", "approvals", "assets", "identity", "projects", "tenancy"]`,
    `permission_namespaces = ["issue"]`. Permissions (ADR 0027 verbs, so the default roles pick them up at the right
    level):
    - `issue.view` — view issues, types and severities
    - `issue.create` — raise an issue
    - `issue.update` — edit an open issue and take the work transitions (assess, assign, start, submit)
    - `issue.approve` — verify, reject verification and close
    - `issue.manage` — configure issue types and severities and run setup

    Events: `issue.raised` v1 and `issue.state_changed` v1.
  - 2. Migration `<timestamp>_issues_core.py` (one revision, every table rendered with
    `render_template("tenant_table", ...)`, so each has `tenant_id`, uuid `id`, `created_at`, `updated_at`,
    `deleted_at`, `FORCE ROW LEVEL SECURITY` with the fail-closed policy and the `aip_app` grants; plus
    `FOREIGN KEY (tenant_id) REFERENCES tenants (id)` and `UNIQUE (id, tenant_id)` for in-module composite FKs, as
    `202610161400_approvals_workflows.py` does):
    - create `issue_types`: `code text NOT NULL` (snake_case check), `name text NULL` (tenant rename; display falls
      back to term `issues.type.<code>`), `is_ncr boolean NOT NULL DEFAULT false`, `default_due_days integer NULL
      CHECK (default_due_days BETWEEN 0 AND 365)`; `UNIQUE (tenant_id, code) WHERE deleted_at IS NULL`.
    - create `issue_severities`: `code text NOT NULL`, `name text NULL` (falls back to `issues.severity.<code>`),
      `rank integer NOT NULL`, `sla_days integer NULL CHECK (sla_days BETWEEN 0 AND 365)`,
      `blocks_itp_step boolean NOT NULL DEFAULT false` (read by ISSUES-03); `UNIQUE (tenant_id, code) WHERE
      deleted_at IS NULL`.
    - create `issues` (with `sync=True`, so `client_generated_id` and `sync_version` exist): `seq integer NOT NULL`
      (per-tenant number shown as the reference), `issue_type_id`, `severity_id` (composite FKs to the two tables
      above), `asset_id uuid NOT NULL` and `project_id uuid NULL` (no cross-module FK; checked through the owning
      modules' `api.py`), `title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200)`, `description text NULL`,
      `state text NOT NULL DEFAULT 'open'` (a read copy of the workflow instance's `current_state` for registers
      and filters; the instance stays the source of truth), `due_date date NULL`, `responsible_user_id uuid NULL`,
      `raised_by uuid NULL`, `source text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','inspection'))`,
      `source_inspection_id uuid NULL`, `source_response_id uuid NULL`, `itp_step_id uuid NULL` (the last three are
      set by ISSUES-02/03; no FK, the inspections tables belong to inspections), `closed_at timestamptz NULL`.
      Indexes: `UNIQUE (tenant_id, seq)`, `(tenant_id, asset_id)`, `(tenant_id, state)`, and the overdue index
      `(tenant_id, due_date) WHERE state <> 'closed' AND deleted_at IS NULL`.
    - Downgrade drops the three tables in reverse order.
  - 3. `tables.py` (SQLAlchemy Core `Table`s mirroring the migration) and `repository.py` (Core queries only, every
    read filters `deleted_at IS NULL`). `seq` is assigned as `coalesce(max(seq), 0) + 1` under
    `pg_advisory_xact_lock(hashtext('issues.seq:' || tenant_id))`, so two concurrent creates never collide.
  - 4. Workflow preset `config/workflows/issue.standard.json`, in the preset envelope APPROVALS-08 defines
    (`presetKey: "issue.standard"`, definition key `issue`, `recordType: "issue"`, a `WorkflowDefinitionSpec` that
    `aip.modules.approvals.schemas.validate_spec` accepts). Only codes and term keys, never display text.
    - States: `open` (initial), `assessed`, `action_assigned`, `in_progress`, `ready_for_verification`,
      `verified`, `closed` (terminal). Each `labelKey` is `workflow.issue.state.<code>`.
    - Transitions (`labelKey` `workflow.issue.action.<action>`):
      - `assess` open→assessed (`issue.update`)
      - `assign_action` assessed→action_assigned (`issue.update`), guard
        `{"!!":[{"var":"record.responsibleUserId"}]}`, `guardMessageKey` `workflow.issue.guard.responsible_required`
      - `start` action_assigned→in_progress (`issue.update`)
      - `reassign` in_progress→action_assigned (`issue.update`), same guard as `assign_action`
      - `submit_for_verification` in_progress→ready_for_verification (`issue.update`)
      - `verify` ready_for_verification→verified (`issue.approve`)
      - `reject_verification` ready_for_verification→in_progress (`issue.approve`)
      - `close` verified→closed (`issue.approve`)
    - The verifier is independent of the assignee: `verify` and `reject_verification` carry the guard
      `{"and":[{"!!":[{"var":"record.responsibleUserId"}]},{"!=":[{"var":"actor.id"},{"var":"record.responsibleUserId"}]}]}`
      with `guardMessageKey` `workflow.issue.guard.verifier_independent`. It uses only allow-listed operators, and
      guard data is `{record, actor:{id, roles}, instance}` as ADR 0035 describes (`actor.id` is a string, so the
      provider returns `responsibleUserId` as a string too).
    - No transition is `critical` in this task: ADR 0010 sign-off assurance on verify/close is not asked for by the
      README and can be added as a preset version later without engine changes.
  - 5. `workflow.py`, registered at import of the module:
    - `register_record_resolver("issue", resolve)`: returns `RecordRef(project_id=issues.project_id)` for a live
      issue visible on the connection, else `None`.
    - `register_guard_context_provider("issue", facts)`: returns `{"responsibleUserId": str | None,
      "raisedBy": str | None, "severityRank": int, "isNcr": bool}` read from issues' own tables only.
    - `install(conn)`: calls `aip.modules.approvals.api.ApprovalsApi.install_preset(conn, "issue.standard")`
      (idempotent per preset version) and upserts the default types and severities from `config/issues/defaults.json`
      by `code` (existing codes are left untouched, so tenant renames survive). Defaults:
      - types `defect` (`is_ncr` false, 14 days) and `ncr` (`is_ncr` true, 28 days);
      - severities `low` (rank 10, 28 days), `medium` (rank 20, 14 days), `high` (rank 30, 7 days, blocks ITP step),
        `critical` (rank 40, 2 days, blocks ITP step).
  - 6. `service.py`, every write in one `with_tenant` transaction:
    - `create_issue`: checks `issue.create` on the project (or tenant when `projectId` is null); validates the asset
      with `aip.modules.assets.api.AssetsApi.assert_asset_exists(conn, asset_id)` and the project with
      `aip.modules.projects.api.ProjectsApi.assert_project_exists`; a type or severity that is not live in this
      tenant → 422 `ISSUE_TYPE_UNKNOWN` / `ISSUE_SEVERITY_UNKNOWN`; a `responsibleUserId` is checked with
      `aip.modules.identity.api.get_user` (unknown → 422 `USER_UNKNOWN`). Sets `due_date` = UTC date of creation +
      `coalesce(severity.sla_days, type.default_due_days)` (null when both are null; ADR 0025 point 5). Inserts the
      row (idempotent on `client_generated_id` through `aip.platform.db.idempotency.create_idempotent`), starts the
      workflow with `ApprovalsApi.get_or_start_instance(conn, "issue", issue_id, project_id)` (host already
      authorised the create), and emits `issue.raised` v1 `{issueId, seq, assetId, projectId, issueTypeCode,
      severityCode, isNcr, source}` with `asset_id=` set.
    - `update_issue` (PATCH `title`, `description`, `severityId`, `dueDate`, `responsibleUserId`): `issue.update`;
      refused with 409 `ISSUE_CLOSED` when `state` is `verified` or `closed`; optimistic concurrency through
      `aip.platform.db.concurrency.update_with_version` (stale `expectedSyncVersion` → 409).
    - `transition_issue(issue_id, action, comment, expected_sync_version)`: `issue.view` on the issue, then
      `ApprovalsApi.transition(conn, policy, actor, instance_id, action, ...)` (approvals checks the transition's
      permission and guard and writes the hash-chained decision). When the result is applied, copy the new state to
      `issues.state`, set `closed_at` on `closed`, and emit `issue.state_changed` v1 `{issueId, assetId, projectId,
      from, to, action}`. A `reject_verification` without a comment → 422 `COMMENT_REQUIRED` before approvals is
      called. Approvals' errors pass through unchanged (409 `INVALID_TRANSITION`, 403, 422 `GUARD_FAILED` with
      `messageKey`).
    - Another tenant's issue id → 404 everywhere (RLS hides it; the service raises `NotFoundError`).
  - 7. `routes.py` under `/api/v1/issues` (every route `authenticated()`; the service checks the project-scoped
    permission, as ADR 0035 §6 does). Request bodies are Pydantic models with `extra="forbid"` and camelCase JSON:
    - `GET /issues?state=&assetId=&severityCode=&cursor=` (`issue.view`, filtered to what the caller may see)
    - `POST /issues` → 201; `GET /issues/{id}` → the issue plus `workflow: {currentState, availableTransitions}`
      from `ApprovalsApi.available_transitions`; `PATCH /issues/{id}`
    - `POST /issues/{id}/transition {action, comment?, expectedSyncVersion?}`; `GET /issues/{id}/history` (from
      `ApprovalsApi.get_history`, with `chainValid`)
    - `GET/POST/PATCH /issues/types` and `/issues/severities` (`issue.manage` to write; soft delete only, refused
      with 409 `IN_USE` when a live issue references the row)
    - `POST /issues/setup` (`issue.manage`) → runs `workflow.install` and returns `{workflowVersion, typesCreated,
      severitiesCreated}`.
  - 8. `api.py`: `IssuesApi.get_issue(conn, issue_id)`, `IssuesApi.create_issue(conn, actor_id, data)` (no
    permission check; for ISSUES-02's subscriber, which runs as the event's actor) and `IssuesApi.get_state(conn,
    issue_id)`. `events.py` registers both event payload models with `register_event`.
  - 9. Terms in `config/terms/en-AU/issues.json` (TERMS-01 format, `text` + `description`):
    `workflow.issue.state.<code>` for all 7 states, `workflow.issue.action.<action>` for all 8 actions,
    `workflow.issue.guard.responsible_required`, `workflow.issue.guard.verifier_independent`, `issues.type.defect`,
    `issues.type.ncr`, `issues.severity.{low,medium,high,critical}`, and the error keys used above.
- **acceptance**:
  - `POST /issues/setup` installs exactly one active `issue` definition and the default types and severities; a
    second call changes nothing.
  - An issue is created against a live asset of the caller's tenant, gets the next `seq`, a due date from its
    severity, a workflow instance in `open`, and one `issue.raised` event, all in one transaction.
  - The full lifecycle open → closed runs through `ApprovalsApi`, and `issues.state` always equals the instance's
    `current_state` after an applied transition.
  - The assignee can never verify or reject verification of their own issue; another user with `issue.approve` can.
  - Another tenant's issue, asset, type or severity is never visible or usable (404 / 422), and every table forces RLS.
- **tests**:
  - **unit** (`test_unit.py`):
    - `validate_spec(issue.standard.json["spec"])` → passes; 7 states, initial `open`, `closed` terminal, every
      state reachable.
    - Every `labelKey` and `guardMessageKey` in the preset exists in `config/terms/en-AU/issues.json` → 0 missing.
    - `aip.modules.approvals.api.allowed_actions(spec, state, granted)` with all five `issue.*` codes granted: at
      `open` → `["assess"]`; at `ready_for_verification` → `["verify", "reject_verification"]` (spec order); at
      `closed` → `[]`; at `ready_for_verification` with only `issue.update` granted → `[]`.
    - `due_date_for(created_at=2026-10-18T23:30:00Z, sla_days=7, default_due_days=14)` → `2026-10-25`;
      `sla_days=None, default_due_days=14` → `2026-11-01`; both `None` → `None`.
    - `IssueCreate` with an unknown key `{"title":"x", ..., "state":"closed"}` → `ValidationError`.
  - **integration** (`test_issues_db.py`, `test_issue_workflow.py`; pytest + testcontainers-python on real
    Postgres, TESTING-01 tenants `kaefer-demo` and `tenant-b`, users Alice and Bob plus a third `kaefer-demo` user
    Carol seeded in the issues conftest; one asset per tenant created with `AssetsApi.create_asset`):
    - `POST /api/v1/issues/setup` as a `kaefer-demo` user with `issue.manage` → 200 `{workflowVersion: 1,
      typesCreated: 2, severitiesCreated: 4}`; again → `{workflowVersion: 1, typesCreated: 0,
      severitiesCreated: 0}`, and `SELECT count(*) FROM workflow_definitions WHERE key = 'issue' AND status =
      'active'` → 1.
    - Alice (`issue.create`, `issue.update`) `POST /api/v1/issues {assetId, projectId: A1, issueTypeId: defect,
      severityId: high, title: "Cladding seam open"}` on 2026-10-18 (frozen clock) → 201 with `seq: 1`,
      `state: "open"`, `dueDate: "2026-10-25"`; 1 `issues` row; 1 `domain_events` row `issue.raised` with
      `payload.severityCode = "high"` and `asset_id` set; `ApprovalsApi.get_active_definition(conn, "issue")`
      version 1 and the instance `current_state = 'open'`.
    - A second create → `seq: 2`. Two creates fired with `asyncio.gather` → `seq` 3 and 4, no unique violation.
    - The same create replayed with the same `clientGeneratedId` → 200, the same `id`, still 1 new row.
    - `assetId` of the `tenant-b` asset → 404 `NOT_FOUND`; a `tenant-b` severity id → 422
      `ISSUE_SEVERITY_UNKNOWN`; a user without `issue.create` → 403 and 0 new `issues` rows.
    - Lifecycle: Alice `assess` → 200 `open → assessed`. Alice `assign_action` with no responsible user → 422
      `GUARD_FAILED`, `messageKey: "workflow.issue.guard.responsible_required"`, state still `assessed`. Alice PATCH
      `responsibleUserId: Bob` → 200; `assign_action` → 200. Bob `start`, `submit_for_verification` → 200 each.
    - Independence: Bob (given `issue.approve` for this test) `verify` → 422 `GUARD_FAILED`, `messageKey:
      "workflow.issue.guard.verifier_independent"`; the history count is unchanged. Carol (`issue.approve`)
      `reject_verification` with no comment → 422 `COMMENT_REQUIRED`; with comment "Seam still open" → 200,
      state `in_progress`. Bob `submit_for_verification`, Carol `verify` → 200 `verified`; Carol `close` → 200,
      `state: "closed"`, `closedAt` set.
    - After the lifecycle: `GET /issues/{id}/history` → 8 entries and `chainValid: true`; 8 `domain_events` rows
      `issue.state_changed` for this issue; `issues.state = 'closed'`.
    - PATCH a `closed` issue → 409 `ISSUE_CLOSED`. `verify` at `open` → 409 `INVALID_TRANSITION`. A user with only
      `issue.view` taking `assess` → 403, nothing written.
    - Two `assess` transitions on the same issue with `asyncio.gather` → one 200, one 409; history has 1 entry.
    - A `tenant-b` user `GET /api/v1/issues/{kaefer issue id}` → 404; `POST .../transition` → 404; their
      `GET /api/v1/issues` → 0 items.
    - As `aip_app` with `app.tenant_id` unset: `SELECT count(*) FROM issues` → 0; an `INSERT INTO issue_types` →
      SQLSTATE 42501.
    - Soft-delete the `high` severity while an issue uses it → 409 `IN_USE`.
  - **e2e**:
    - None in this task: it ships no page, and no `issue` definition or fixture users are seeded on the compose
      stack (the same reason as ADR 0035 §9). The HTTP journeys above run in-process; ISSUES-04 adds the
      Playwright journey (register, raise, detail, cross-tenant 404 and axe) once the pages exist.
