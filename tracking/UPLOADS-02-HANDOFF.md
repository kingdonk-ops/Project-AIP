# UPLOADS-02 — Handoff for the remaining work

**Branch:** `claudeK/uploads-02-scan-worker`  ·  **PR:** #135  ·  **Task spec:** `tracking/tasks/UPLOADS-02.md`

This is a handoff for a fresh agent. The foundation and the pure pipeline stages are done and
pushed; this file lists exactly what is left, the real (Python) APIs to build it against, and the
traps already hit so you don't repeat them. Read `tracking/tasks/UPLOADS-02.md` for the acceptance
criteria — but note its file list and package names are the **old TypeScript blueprint**; this
repo is the Python port (see "Stack realities").

---

## Stack realities (the spec predates the port)

| Spec says (TS blueprint) | This repo actually uses |
|---|---|
| `apps/api/src/modules/uploads/*.ts` | `apps/api/aip/modules/uploads/*.py` |
| BullMQ queues / processors | **Procrastinate** via the `ops` module (`ops.register` / `ops.enqueue`) |
| `db/migrations/*.sql` | **Alembic** forward-only raw-SQL migrations in `apps/api/migrations/versions/` |
| dependency-cruiser "no direct S3" | **import-linter** contract (`apps/api/pyproject.toml` / its `.importlinter`) |
| `emit(tx, ...)` | `aip.platform.events.outbox.emit(conn, name, version, Aggregate(type,id), payload)` |

Run everything from `apps/api` with `uv run` (e.g. `cd apps/api && uv run pytest ...`).

---

## DONE and pushed (do not redo)

- **Migration** `apps/api/migrations/versions/202610251400_uploads_stored_files_scan.py`:
  `stored_files` (tenant table, soft-delete, FORCE RLS, `scan_status`/`preview_status` CHECKs,
  `legal_hold` default, `(id, tenant_id)` UNIQUE) + the **project-scope RLS policy** (ACCESS-03)
  + `scan_results` (append-only, FORCE RLS, `REVOKE UPDATE/DELETE/TRUNCATE FROM aip_app`,
  stage/outcome CHECKs) + the tenant-safe FK `upload_sessions(file_id,tenant_id) → stored_files`.
- **Table declarations** `apps/api/aip/modules/uploads/tables.py`: `stored_files`, `scan_results`.
- **Schema snapshot** `db/schema.snapshot.sql` regenerated to match.
- **Pure stages** `apps/api/aip/modules/uploads/pipeline/`:
  - `magic_bytes.py` — `detect_mime`, `check_magic_bytes` (first 4 KB; OOXML-zip compatible; SVG/HTML
    denied; text must be UTF-8 no-NUL).
  - `caps.py` — `size_cap`, `ratio_cap`, `evaluate_zip_entries`, `image_dimensions` (header-only).
  - `clamav_client.py` — async clamd `INSTREAM`/`VERSION` over TCP, timeout → `ClamdError`.
  - `types.py` — `StageResult(stage, outcome, detail)`, `Stage`/`Outcome` literals.
  - `reducer.py` — `run_scan(ScanInput, ClamdSettings) -> ScanVerdict`: runs size → magic → ratio →
    clamav in order, stops at first non-`pass`, catches `ClamdError` into a `clamav`/`error`
    stage (**fail-closed**). Returns `outcome`, `detected_mime`, and one `StageResult` per stage.
  - Tests: `tests/test_pipeline_stages.py` (12), `tests/test_clamav_client.py` (6),
    `tests/test_pipeline_reducer.py` (6) — all against local stub sockets, no Docker.
- **Isolation + coverage guards updated** for the new project-scoped table:
  `tests/isolation/overrides.toml` (`stored_files` → `principal_kind = "system"`) and the ACCESS-03
  coverage test passes.

---

## REMAINING (in dependency order)

### 1. Stateful pipeline runner — `pipeline/runner.py` (new) or into `service.py`
Entry point the worker calls, e.g. `UploadsApi.run_scan_pipeline(session_id)`:
1. In a `with_tenant` tx: load the session (`repo.get_session`), set status `scanning`
   (`repo.set_status(conn, id, "scanning")`). The `upload_sessions` status CHECK **already allows**
   `scanning`, `released`, `rejected` — no migration needed.
2. Fetch the quarantine object bytes once: `get_object_store().get(ObjectKey(session["quarantine_key"]))`.
   Compute `sha256` over those bytes (hashlib). The 100 MiB single-part cap makes whole-object
   in-memory acceptable.
3. Build `ScanInput(data, declared_mime=session["declared_mime"],
   declared_size=int(session["declared_size_bytes"]), platform_max=SINGLE_PART_MAX_BYTES)` and call
   `run_scan`. Write **one `scan_results` row per returned `StageResult`** (insert via a new
   `repo.insert_scan_result`). `scan_results` is append-only; `aip_app` has SELECT/INSERT only.
4. Branch on `verdict.outcome`:
   - `pass` → call `release(...)` (step 2 below).
   - `fail` → reject immediately with the failing stage as reason (step 3 below).
   - `error` → **raise** so Procrastinate retries. On the **last attempt** (see `JobView`/spec: 3
     attempts), reject with reason `scan_error`. Decide "last attempt" in the handler (step 4) — it
     has the attempt context; the runner can take an `is_last_attempt: bool` arg.

### 2. `release` — private, pipeline-only (not exported from `api.py`)
- Released key: `tenant_key(ctx.tenant_id, "files", str(file_id))` (`aip.platform.capabilities.keys`).
- **No server-side copy exists** on the `ObjectStore` protocol — reuse the bytes already read in
  step 1: `store.put(released_key, data, content_type=detected_mime, kms_key_id=...)`. (KMS key ref
  is still `None` until UPLOADS-07, mirror `service._resolve_kms_key_ref`.)
- Insert `stored_files` (`scan_status='clean'`, detected_mime, size_bytes, sha256, storage_key,
  uploaded_by, project_id, `preview_status='pending'` or `'none'`, `legal_hold=false`).
- `repo.set_status` the session to `released` and set `file_id` (add a repo helper for file_id).
- `emit('upload.completed', 1, Aggregate('upload_session', session_id), {...})` **in the same tx**.
- Delete the quarantine object **after commit** (`store.delete(quarantine_key)`).

### 3. Reject path (both `fail` and last-attempt `error`)
- `repo.set_status(conn, id, "rejected", reject_reason=<stage or 'scan_error'>)`.
- `emit('upload.rejected', 1, Aggregate('upload_session', session_id), {sessionId, projectId, reason})`.
- **Keep** the quarantine object (30-day lifecycle is OPS-06, out of scope).

### 4. Register the two events — **guarded, do all four parts or CI fails**
`aip/platform/events/registry.py` uses `register_event(name, version, model, owner)`. Requirements
(each has a CI guard):
1. Define pydantic payload models for `upload.completed` v1 and `upload.rejected` v1.
2. Register them where the uploads module registers (follow an existing module that emits events;
   grep for `register_event(` usages).
3. Add both to the uploads **`manifest.toml` `events`** list — the manifest and the registered set
   must match exactly (`ManifestEventMismatchError`).
4. Export the committed JSON schema to `packages/contracts/events/upload.completed.v1.json` (and
   `.rejected`) via `export_event_schemas` — a registered model that doesn't match its committed
   schema raises `ReleasedSchemaChangedError`.

### 5. Procrastinate handler — `uploads.scan`
In `jobs.py` (next to `expire_sessions`): `async def scan(conn, job: ops.JobView) -> str|None` that
reads `session_id` from `job.payload`, decides last-attempt from the job, and calls the runner
inside the job's `with_tenant` tx. Register with
`ops.register("uploads.scan", scan, queue="uploads-scan", timeout_s=120, max_attempts=3)`.
Keep the handler thin (spec step 2: "imports nothing else from the module").

### 6. Enqueue on confirm
In `service.py::confirm`, after `set_status(..., "uploaded")`, in the same tx:
`await ops.enqueue(conn, "uploads.scan", {"session_id": str(session_id)}, idempotency_key=str(session_id))`.
The `idempotency_key = session_id` gives the spec's "jobId = sessionId" (enqueue twice → one job →
one `stored_files` row).

### 7. `GET /api/v1/uploads/files/{id}/url`
Route in `routes.py` + service method: only when `stored_files.scan_status='clean'` **and** the
`uploads.view` policy passes for the file's project; return a presigned GET (`store.presign_get`,
TTL 300s). Any other status → 409 `NOT_RELEASED`. Cross-tenant → 404 (RLS makes the row invisible).

### 8. import-linter "no direct S3" contract
Add a forbidden-import contract: nothing may import `aip.platform.capabilities` object-store
internals (or boto3/aioboto3) **except** `aip.platform.capabilities.**` and
`aip.modules.uploads.**`. Put it in the import-linter config (grep `importlinter` /
`[tool.importlinter]`). Add a fixture module that violates it and assert the contract fails, to
mirror the spec's acceptance test.

### 9. compose `clamav` service
`infra/docker-compose.yml` (or the repo's compose file): add `clamav/clamav:stable` with freshclam,
attached only to an `internal: true` network shared with the worker. Point the worker's
`ClamdSettings(host="clamav", port=3310)` at it.

### 10. Integration + e2e tests
- Integration (testcontainers Postgres + object store + `clamav/clamav`): clean `sample.pdf` →
  `released`, 1 `stored_files` (clean), 4 `scan_results` (all pass), 1 `upload.completed`,
  quarantine gone, released key under `tenant/<A>/files/`. EICAR → `rejected`, `clamav` row `fail`
  with `detail.signature` ~ EICAR, 1 `upload.rejected`, no `stored_files`. HTML-as-jpg → rejected at
  `magic_bytes`. clamav stopped → after 3 attempts `rejected/scan_error`. Enqueue twice → 1 row.
  `GET /files/:id/url`: clean → downloads bytes with matching sha256; rejected → 409/404; tenant-B →
  404. As `aip_app`: `UPDATE scan_results` → permission denied.
- e2e (`e2e/`): Playwright API project on the compose stack; EICAR generated at runtime (never
  committed) → `rejected` within 60s; a real photo → `released` with matching sha256.

---

## Traps already hit (avoid the re-learn)

- **Any new `project_id` table** needs: the `project_scoped_policy` template rendered in the
  migration, an `overrides.toml` `principal_kind = "system"` entry (else the generated isolation
  test fails "own row not visible"), and it must **not** go in `project_scope_allowlist.yaml` (that
  is only for non-record tables). `stored_files` is already done — this is for any further tables.
- **Regenerate `db/schema.snapshot.sql`** after any migration change, or
  `test_snapshot_of_a_fresh_database_matches_the_committed_file` fails in CI. Quick way: a throwaway
  test using the `empty_db` fixture → `bootstrap()`, `aip_db("migrate")`, `aip_db("snapshot",
  "--output", db/schema.snapshot.sql)`; delete the throwaway after. (pg_dump is available locally.)
- **CI job logs via `get_job_logs` return only the Postgres service-container teardown**, not the
  pytest step — you cannot read the `FAILED` line from them. To find a CI failure, reproduce with
  the **full local suite**: `cd apps/api && uv run pytest -q -rf -p no:cacheprovider` (~22 min). It
  is the reliable source; filter its output for `^FAILED`/summary lines.
- **pyright in CI is scoped to `apps/api`.** The 5 pre-existing errors in `tools/ci/` do not fail
  CI; don't chase them.
- The full suite is slow (~22 min) and this task's schema-wide guard tests (`tests/isolation`,
  `tests/access`, `tests/security`, `tests/platform/db`) are the ones most sensitive to new RLS
  policies/tables — run those four dirs first for fast feedback before the full suite.

---

## Validation before each push

```
cd apps/api
uv run ruff check .
uv run pyright aip/            # new files clean; CI scopes to apps/api
uv run pytest -q tests/isolation tests/access tests/security tests/platform/db aip/modules/uploads
# then, before the final push, the full suite once:
uv run pytest -q -rf -p no:cacheprovider
```

One validated push beats three speculative ones (branch protection requires the branch up-to-date;
a red push costs a ~22 min CI cycle).

---

## Conventions for this repo

- **Board-done-on-PR** (user convention): set this task's row in `tracking/BOARD.md` to `done` when
  its PR is opened (not review-then-done-on-merge), and add a `tracking/PROGRESS.md` line.
- Commit trailers / PR footer: use the session's attribution (Co-Authored-By + Claude-Session for
  commits; the 🤖 Generated line + session URL for PR bodies). Do **not** put any model identifier in
  committed artifacts.
- `confirm`/sessions live in `service.py` + `repository.py` + `routes.py` + `schemas.py`; the `ops`
  published interface is `aip/modules/ops/api.py` (import only that from other modules).
