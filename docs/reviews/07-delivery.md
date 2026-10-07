# Development lead review

## Verdict
**Agents can't run the P0 plan in order as written. Don't start it until it has been rewritten.** The phase goals are reasonable, but the task list has five blocking defects:

1. **Two codebases are mixed in one task set.** About 33 of the 59 tasks target a Python/FastAPI layout that doesn't exist: `backend/app/...py`, `backend/migrations/xxxx.py`, `frontend/src`, pytest, Hypothesis, SQLAlchemy, arq, `pyproject.toml`. The other 26 target the TypeScript layout (`apps/api`, `apps/web`, `migrations/versions/*.sql`). Every OPS task except OPS-07, every SECURITY task, every TERMS task, every TESTING task and DATABASE-01 is Python-era. An agent following these specs will create a second backend.
2. **Several tasks assume an existing AIP codebase and data that aren't in this repo.** Examples:
   - DATABASE-01 "audit existing AIP schema"
   - DATABASE-03 "tenant_id backfill"
   - TENANCY-01 "seed Kaefer from the existing top-level AIP org"
   - TENANCY-03 "replace Phase 24 join helpers"
   - TERMS-01 "extract hard-coded labels from AIP"
   - DATABASE-05 (inspection_responses, sync_operations)
   - OPS-08 "existing Coolify Postgres"
   - TESTING-06 (AIP lifecycle and golden report)

   The task conventions also require "port AIP behaviour as golden tests", which can't be done without access to the AIP source or specs.
3. **Referenced artefacts don't exist.** `docs/adr/` doesn't exist, yet every task's "read before starting" points to it and the conventions file cites ADR 0002. `tracking/BOARD.md` is linked from every task and is also missing.
4. **Decision conflicts are unresolved, and agents will pick differently each time.**
   - Owner decisions say "Keep Alembic raw SQL" and "arq or Celery" for a greenfield TypeScript repo where there is nothing to keep.
   - The conventions say migrations are "forward-only", but TESTING-05 and DATABASE-03 require up-down-up.
   - The identity README says WorkOS; the owner decision says Keycloak.
   - The default DoD says "demonstrated on staging" and "audit events emitted", but staging and audit come late in P0. Early tasks can never meet that DoD.
5. **Hidden and missing dependencies.**
   - Fourteen tasks list no dependencies but need the monorepo, a migration runner and the DB roles: SECURITY-02, OPS-01, TERMS-01, TESTING-01, OPS-04, OPS-07, SECURITY-08 and others.
   - No task chooses or installs a migration runner at all.
   - TENANCY-01, ARCH-04 and DATABASE-02 need verified Keycloak tokens, but identity has no tasks.
   - TESTING-04 and DATABASE-07 need a permission catalogue and OpenAPI routes (the access module has no tasks).
   - TENANCY-04 needs assets (P1). TESTING-06 needs inspections, RSW, eligibility (P1) and the report engine (P2). TESTING-07 needs offline sync (P2).

**Critical path today:** ARCH-01 → migration runner (missing) → DATABASE-02 → TENANCY-01, which is blocked on identity (missing) → policy service (missing) → projects (missing) → approvals and uploads (missing). Seven of the 15 P0 modules have no tasks, and they sit on the critical path.

**Is P0 too big before Kaefer sees value?** Yes. It is 15 modules, an estimated 100+ tasks, and none of it touches assets or inspections. Split P0 into three parts:
- **M0, the walking skeleton** (about 20 tasks).
- **P0-core**: what P1 actually consumes, namely identity basics, policy service, projects, audit writer, approvals engine and uploads core.
- **P0-hardening**, run in parallel with P1: SCIM, compliance registers, offboarding and crypto-shred, quotas, term packs, k6, backup evidence, S3 anchoring.

Then cut a thin P1 slice (asset tree plus one inspection) as M1, the first Kaefer demo.

## Problems with the current task list
| Task | Problem | Fix |
|---|---|---|
| All | Links to `docs/adr/` and `tracking/BOARD.md`, which don't exist | DOCS-01 creates BOARD.md; STACK-01 creates the ADRs. Both land first |
| All | DoD requires staging demo, audit events and a catalogue regen that don't exist yet | Staged DoD: before OPS-09, "green CI"; before AUDIT-02, "events written to outbox" |
| DATABASE-01 | Audits an AIP schema that isn't here; Python checker; duplicates TESTING-02 | Rewrite as "schema conventions doc + TS pg_catalog checker" and merge with TESTING-02 |
| DATABASE-02 | Depends on DATABASE-01; needs a migration runner and Testcontainers that don't exist; e2e needs auth | Depend on DATABASE-08 (new) only. Bring a minimal Testcontainers harness. Move the e2e into TESTING-09 |
| DATABASE-03 | Backfill of non-existent AIP tables; "Kaefer user asset tree" e2e | Delete from P0. Move the AIP data import to P1 (DATA_IO "AIP migration and reconciliation"). Repoint its dependents to DATABASE-02/TESTING-02 |
| DATABASE-05 | Grants on inspection_responses (P1) and sync_operations (P2); partitioning of P1 tables | Keep only the generic append-only grant helper and audit_log. Move partitioning to P1 inspections |
| DATABASE-06 | Legal hold and recycle bin belong to the audit module; `modules/records` folder isn't in the blueprint | Re-home as AUDIT-05 |
| DATABASE-07 | Depends on DATABASE-03; needs OpenAPI routes | Depend on TESTING-02, STACK-03, ACCESS-01 |
| TENANCY-01 | Seeds Kaefer from the "existing AIP org"; e2e needs Keycloak | Seed fixture tenants `kaefer-demo` and `tenant-b`. Depend on IDENTITY-01 |
| TENANCY-03 | Depends on DATABASE-03; "Phase 24 helpers" don't exist; project-scoped roles duplicate the access module | Narrow to organisations CRUD and type. Move project-scoped roles to ACCESS-02. Depend on PROJECTS-01 |
| TENANCY-04 | Shares assets (P1) and serves the portal (P2) | Move to P2 (portal) |
| TENANCY-05 | Needs terminology load and admin invite, but doesn't depend on them | Add deps TERMS-01, IDENTITY-04 |
| TENANCY-06/07 | Quotas, support access, crypto-shred: not needed for a single pilot tenant | Move to P0-hardening, running alongside P1 |
| SECURITY-02..08 | Python paths. 03/04/05 are SOC 2 registers, and SOC 2 evidence is a P2 exit criterion | Rewrite in TS. Defer 03/04/05 to P2. Split 06: masking to ACCESS (P1), EXIF to UPLOADS-04. 07 depends on IDENTITY-03 |
| OPS-01/02 | Python. arq conflicts with STACK-01 (BullMQ) | Rewrite in TS (`apps/worker`) after the owner confirms BullMQ vs pg-boss |
| OPS-03/05/06 | Python and frontend paths; not on the critical path | Rewrite in TS. Defer 05/06 to P1 |
| OPS-07 | Mis-sized M: VPC, RDS, ElastiCache, S3, ECS, Trivy, cosign, prod approval and rollback; needs a Dockerfile but has no deps | Split: OPS-07 (network + data + ECS staging), OPS-09 (build, scan, deploy staging), OPS-10 (cosign, prod approval, rollback). Depend on STACK-05 |
| OPS-08 | "Existing Coolify Postgres" | Target RDS PITR plus a restore drill. Late P0 |
| TESTING-01 | Python/Alembic; overlaps DATABASE-02 (both create the app role and tenant session) | DATABASE-02 owns roles and the session. TESTING-01 becomes TS fixture helpers (tenantA/B, asTenant) |
| TESTING-03 | Python; tests Redis/S3/search isolation before they exist | TS. Depend on TENANCY-02, OPS-02, UPLOADS-01 |
| TESTING-04 | Python; needs the catalogue and OpenAPI | TS. Depend on ACCESS-01, STACK-03 |
| TESTING-05 | Up-down-up contradicts "forward-only" | Owner decides. Default: forward-only, with a test that migrates from empty and re-runs idempotently |
| TESTING-06 | Hold points, RSW, certificates and PDF report are P1/P2 | Split: lifecycle golden tests become APPROVALS-05 (P0). The rest moves to P1 inspections and P2 report engine |
| TESTING-07 | Offline sync is P2 | Move to P2 offline |
| TESTING-08 | k6 at 5,000 VUs, mobile PIN/offline journeys, `pyproject.toml` | Keep CI gates only (P0). k6 and mobile move to P2 |
| TERMS-01..08 | Python and `frontend/` paths; 01 extracts AIP labels | Rewrite in TS (`apps/api/src/modules/terms`, `apps/web`). Seed en-AU from the blueprint vocab decisions |
| TERMS-04/06 | Pack import and rollback (second market is P4); aliases for import and search (P1/P2) | Defer 04 to P4 and 06 to P1 data_io |
| TERMS-08 | Provider plus admin screen in one M task | Split: provider and `useT` (P0), dictionary admin (late P0) |
| STACK-01 | Must resolve migrations, queue and sidecar first; still says "Alembic … standalone container" | Make it task #1 with an explicit owner sign-off. Drop the sidecar from ARCH-01 and STACK-05 until a Python need exists |
| ARCH-05/08, TENANCY-01 etc. | Hard-coded migration numbers (0100–0170) collide when agents work in parallel | Use timestamped migration filenames, assigned at PR time |

## Milestone M0: walking skeleton
**Goal:** two tenants. A Keycloak user signs in to the Next.js shell, sees and creates projects in a Projects register, and can't see the other tenant's projects. RLS enforces this, CI proves it, and the pipeline deploys it to AWS staging. Run steps sharing a number in parallel.
1. DOCS-01: board, staged DoD, conventions fixes. STACK-01: ADRs plus owner sign-off on migrations and queue.
2. ARCH-01: monorepo without the Python sidecar.
3. DATABASE-08 (migration runner + baseline), ARCH-03 (CI + boundary lint), ARCH-04 (request context), STACK-05 (compose + Dockerfiles), OPS-04 (health/logging), IDENTITY-01 (Keycloak realm + JWT verify), DESIGN-01 (tokens + ui package).
4. DATABASE-02 (roles, template, withTenantTx), TESTING-02 (schema guard, merged with DATABASE-01), DESIGN-02 (shell + OIDC login), OPS-07 (staging infra).
5. TENANCY-01 (tenants, regions, guard), TESTING-01 (fixtures), STACK-03 (OpenAPI client), OPS-09 (build → staging).
6. IDENTITY-02 (users, membership, JIT, `/me`).
7. ACCESS-01 (catalogue + PolicyService, deny by default).
8. PROJECTS-01 (projects/sites API with RLS).
9. PROJECTS-02 (Projects register page via the generated client). Labels come from a static en-AU key file read through `t()`; TERMS-01/02 later replaces the source without changing call sites.
10. TESTING-09: Playwright skeleton e2e on CI and on staging smoke. Tenant A creates a project; tenant B gets 404; the unset-tenant query returns 0 rows.

**Exit:** steps 1–10 merged, the staging URL is live, and Kaefer can log in to a branded shell. That's about 22 tasks.

## P0 execution waves
Tasks within a wave can run in parallel. An asterisk (*) marks a task that must be rewritten before it starts. Waves 0–5 together make up M0.

| Wave | Tasks |
|---|---|
| 0 | DOCS-01, STACK-01*, SECURITY-01*, ARCH-01* |
| 1 | DATABASE-08, ARCH-02, ARCH-03, ARCH-04, STACK-02, STACK-04, STACK-05*, OPS-04*, IDENTITY-01, DESIGN-01 |
| 2 | DATABASE-02*, TESTING-02* (absorbs DATABASE-01), STACK-03, OPS-07*, DESIGN-02 |
| 3 | TENANCY-01*, TESTING-01*, OPS-09, ARCH-05, DATABASE-04, TERMS-01*, OPS-01* |
| 4 | IDENTITY-02, TENANCY-02, ARCH-06, ARCH-08, TERMS-02*, OPS-02*, DATABASE-05*, SECURITY-02* |
| 5 | ACCESS-01, ARCH-07, TERMS-03*, TERMS-07*, TERMS-08* (provider), AUDIT-01, DESIGN-03 → PROJECTS-01 → PROJECTS-02, TESTING-09 (M0 done) |
| 6 | ACCESS-02, IDENTITY-03, TENANCY-03*, AUDIT-02, APPROVALS-01, UPLOADS-01, DATABASE-07*, TESTING-04*, TERMS-05*, DESIGN-04, OPS-03* |
| 7 | ACCESS-03, ACCESS-04, PROJECTS-03, IDENTITY-04, APPROVALS-02, UPLOADS-02, UPLOADS-03, TESTING-03*, TESTING-05*, SECURITY-08*, OPS-10 |
| 8 | APPROVALS-03, APPROVALS-04, APPROVALS-05, UPLOADS-04, UPLOADS-05, IDENTITY-05, ACCESS-05, PROJECTS-04, AUDIT-03, AUDIT-04, TENANCY-05*, DESIGN-05 |
| 9 (P0 exit) | APPROVALS-06, UPLOADS-06, IDENTITY-06, AUDIT-05 (was DATABASE-06), SECURITY-07*, OPS-08*, TESTING-08* (CI gates only) |
| Hardening, in parallel with P1 | TENANCY-06, TENANCY-07, SECURITY-03/04/05/06 (split), OPS-05, OPS-06, TERMS-08 admin screen |
| Moved out of P0 | DATABASE-03 → P1 data_io; TENANCY-04 → P2; TESTING-06 → P1/P2 (split); TESTING-07 → P2; TERMS-04 → P4; TERMS-06 → P1 |

**P0-core critical path:** ARCH-01 → DATABASE-08 → DATABASE-02 → TENANCY-01 → IDENTITY-02 → ACCESS-01 → ACCESS-02 → APPROVALS-02 → APPROVALS-04 → APPROVALS-06. That is about 10 sequential tasks. Uploads (via OPS-02) and audit (via ARCH-07) run alongside.

## Missing P0 tasks to create
| ID | Title | Module | Size | Depends on | Goal |
|---|---|---|---|---|---|
| DOCS-01 | Board, staged DoD, conventions/README conflict fixes | arch | S | — | Fix the Alembic, forward-only and WorkOS contradictions; create BOARD.md |
| DATABASE-08 | Raw-SQL migration runner, migrator container, baseline + extensions | database | M | ARCH-01, STACK-01 | One schema authority runnable from TS CI (extensions: ltree, pgcrypto, PostGIS, pgvector) |
| IDENTITY-01 | Keycloak dev realm in compose + API OIDC/JWKS verification, tenant claim mapper | identity | M | ARCH-01, STACK-05 | Verified tokens for every guard |
| IDENTITY-02 | Users and tenant membership, JIT provisioning, GET /me | identity | M | DATABASE-02, TENANCY-01, IDENTITY-01 | Local user record per tenant |
| IDENTITY-03 | Server-side sessions, refresh rotation, revocation (Next.js BFF) | identity | M | IDENTITY-02, DESIGN-02 | Revocable sessions, with 15-minute access tokens |
| IDENTITY-04 | Invite/accept flow; local email+password+MFA per owner decision | identity | M | IDENTITY-03, STACK-02 | Non-SSO customers can sign in |
| IDENTITY-05 | SCIM deprovision revokes sessions and keys in one transaction; user.deactivated | identity | M | IDENTITY-03, ARCH-05 | Meets the P0 exit criterion |
| IDENTITY-06 | Hashed, scoped, expiring API keys | identity | S | ACCESS-01, IDENTITY-02 | Integration auth |
| ACCESS-01 | Permission catalogue from manifests + PolicyService.can + Nest guard | access | M | ARCH-02, ARCH-04, IDENTITY-02 | One deny-by-default authorisation layer |
| ACCESS-02 | Roles, default role seed, tenant/project role assignments API | access | M | ACCESS-01, PROJECTS-01 | Project-scoped roles |
| ACCESS-03 | Membership scope tables and RLS project predicates; policy/RLS parity tests | access | M | ACCESS-02 | Enforcement in the data layer |
| ACCESS-04 | Teams, membership, cache invalidation event | access | M | ACCESS-02, ARCH-07 | Team visibility, approver targets |
| ACCESS-05 | Users & Roles UI, permission matrix page and export | access | M | ACCESS-02, DESIGN-03 | Admin usability, review evidence |
| PROJECTS-01 | Projects + sites tables and CRUD API (code unique per tenant, status) | projects | M | DATABASE-02, TENANCY-01, ACCESS-01 | First real register |
| PROJECTS-02 | Projects register page + create form | projects | M | PROJECTS-01, DESIGN-02, STACK-03 | M0 UI slice |
| PROJECTS-03 | Project membership, header switcher, X-Project-Id enforcement | projects | M | ACCESS-02, ARCH-04 | Project scoping by default |
| PROJECTS-04 | Tenant work-type classification + project settings overrides | projects | M | PROJECTS-01, TERMS-02 | Drives P1 requirement bundles |
| DESIGN-01 | Tokens, IBM Plex, shadcn/ui package, axe lint | design | M | ARCH-01 | Shared UI base |
| DESIGN-02 | App shell (header, nav rail) + OIDC login/logout | design | M | DESIGN-01, IDENTITY-01 | Frame for every page |
| DESIGN-03 | Register table standard (dense, filters, server pagination, CSV) | design | M | DESIGN-02 | Reused by every P1 register |
| DESIGN-04 | Record detail pattern, dialogs, toasts, empty/loading/error states | design | M | DESIGN-02 | Reused by P1 detail pages |
| DESIGN-05 | Tenant accent theme + Playwright visual regression | design | S | DESIGN-03 | Kaefer branding |
| AUDIT-01 | Append-only hash-chained audit_log, writer role, REVOKE | audit | M | DATABASE-05, ARCH-05 | Tamper-evident store |
| AUDIT-02 | Universal writer from outbox + security stream (auth events) | audit | M | AUDIT-01, ARCH-07, IDENTITY-02 | Every change audited |
| AUDIT-03 | Chain verifier CLI + S3 Object Lock anchoring job | audit | M | AUDIT-01, OPS-02, OPS-07 | Independent verification |
| AUDIT-04 | Activity/timeline API (cursor, permission-filtered) + project activity tab | audit | M | AUDIT-02, ACCESS-01, DESIGN-04 | Visible history |
| AUDIT-05 | Legal hold + recycle bin (replaces DATABASE-06) | audit | M | AUDIT-01, DATABASE-04 | Defensible purge |
| APPROVALS-01 | Versioned workflow_definitions/instances + pure state-machine evaluator | approvals | M | DATABASE-04, ARCH-02 | Engine core |
| APPROVALS-02 | Transition service: policy check, version pinning, hash-chained decisions, events | approvals | M | APPROVALS-01, ACCESS-01, AUDIT-01 | Single status model |
| APPROVALS-03 | Server-side JSONLogic guards (minimal; full rules engine in P1) | approvals | S | APPROVALS-02 | Guarded transitions |
| APPROVALS-04 | Approval routes: sequential/parallel steps, user/role/team approvers | approvals | M | APPROVALS-02, ACCESS-04 | Review chains |
| APPROVALS-05 | Inspection lifecycle preset (neutral codes + term keys) + golden tests | approvals | M | APPROVALS-02, TERMS-01 | P0 exit criterion; **blocked on AIP lifecycle spec** |
| APPROVALS-06 | Approvals inbox API + page | approvals | M | APPROVALS-04, DESIGN-03 | User-facing approvals |
| UPLOADS-01 | Upload sessions + presign to quarantine with tenant prefix and policy | uploads | M | STACK-02, TENANCY-02, ACCESS-01 | Single entry path |
| UPLOADS-02 | Scan worker: ClamAV, magic bytes, caps, fail-closed release, events, "no direct S3" lint | uploads | M | UPLOADS-01, OPS-02, ARCH-05 | P0 exit criterion |
| UPLOADS-03 | Resumable S3 multipart | uploads | M | UPLOADS-01 | Poor-connection sites |
| UPLOADS-04 | EXIF/GPS policy + thumbnails in sandboxed worker (absorbs SECURITY-06 EXIF) | uploads | M | UPLOADS-02 | Safe previews |
| UPLOADS-05 | Per-file-type policy table + storage quota counters | uploads | S | UPLOADS-02 | Abuse limits |
| UPLOADS-06 | Upload tray + scan status chip | uploads | M | UPLOADS-02, DESIGN-03 | Attachments UI for P1 |
| OPS-09 | Build once, Trivy scan, push to ECR, deploy staging, smoke | ops | M | OPS-07, STACK-05 | M0 deploy |
| OPS-10 | Cosign, prod promotion approval, digest rollback | ops | M | OPS-09 | Rest of the original OPS-07 |
| TESTING-09 | Walking-skeleton e2e (two tenants, login, register, isolation) on CI + staging | testing | S | PROJECTS-02, OPS-09 | M0 proof |

## Just-in-time task generation process for later phases
1. **Rolling horizon.** Only the current phase and the next one get task files. Generate P1 tasks when P0-core reaches wave 6, and P2 tasks only once P1 passes its midpoint. P3/P4 stay as module READMEs.
2. **Gate before generation.** For each module, before writing tasks, resolve its README "Open questions" with the owner and record the answers as ADR lines. Examples: tus vs multipart, CASL vs OpenFGA, WorkOS vs Keycloak. Generator input = README + data-model + ADRs + the actual repo tree and published interfaces of modules already merged. It must never use the AIP-era `04-code-layout.md`.
3. **Two passes per module.**
   - Pass A is a slice plan: 4–8 tasks, the "minimum to unblock dependents" first, accepted features after.
   - Pass B writes full specs only for the first 3 tasks. The rest stay as one-line stubs until their dependencies merge, so specs cite real file paths and signatures.
4. **Mechanical lint on every generated task:**
   - Paths only under `apps/`, `packages/`, `migrations/`, `infrastructure/`; reject `backend/`, `.py` and `frontend/`.
   - Every dependency exists or is already merged.
   - Size is no bigger than M, with at most one migration.
   - Tests reference only tables and routes that exist.
   - Exactly one module folder.
   - An extend/harden/port tag, and a port tag only if the AIP source is cited and available.
5. **Phase-entry review.** A human or lead agent reviews the wave table before agents start. Cap work in progress at about 8 parallel agents, and run the critical path first.
6. **Feedback loop.** When a task is blocked or re-scoped, the agent writes a stub follow-up task rather than expanding scope. The generator re-runs for that module only.
7. **Defer by default.** Anything not named in a phase exit criterion becomes a "hardening" or later-phase stub, not a current-phase task.

## Questions for the owner
1. **AIP source access.** Will the AIP repo, schema and specs (TASKS §, E-stories, Phase 24, lifecycle, Scope Portal pixel specs) be made available to agents? If not, all "port/golden" tasks need written specs instead.
2. **Migrations.** "Keep Alembic" has nothing to keep in a greenfield TS repo. Do you approve raw SQL files run by a TS-native runner (e.g. node-pg-migrate or dbmate) and no Python toolchain? Forward-only, or up-down-up?
3. **Job queue.** BullMQ (STACK-01 default) or pg-boss (no Redis dependency for jobs)? arq and Celery don't fit a TS worker.
4. **Identity.** Keycloak is the decision, but the identity README says WorkOS. Should local email+password+MFA live in Keycloak, or be built in-app as "build in-app on libraries" suggests?
5. **Python sidecar.** Is one needed in P0 at all? I propose dropping it until a concrete need such as OCR appears.
6. **M0 deploy target.** Can it go to AWS staging immediately (needs an AWS account, IAM and budget), or Coolify demo first?
7. **Kaefer demo timing.** Is M1 (asset tree plus one inspection, right after P0-core) acceptable, with compliance hardening running in parallel with P1?
8. **Re-authentication.** Which transitions beyond hold-point release and final sign-off need it? This affects APPROVALS-02.
9. **Resumable uploads and OCR.** tus or S3 multipart, and Textract or Tesseract? This blocks UPLOADS-03/04.

The main files behind this review:
- `/home/user/Project-AIP/docs/blueprint/06-build-order.md`
- `/home/user/Project-AIP/docs/blueprint/07-task-conventions.md`
- `/home/user/Project-AIP/docs/blueprint/01-decisions.md`
- `/home/user/Project-AIP/docs/blueprint/modules/identity/README.md` (the WorkOS conflict)
- `/home/user/Project-AIP/tracking/tasks/*.md`
