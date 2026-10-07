# Operations, hosting & deployment (`ops`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
Operations, hosting and deployment is the foundation module (suggested phase P0) covering how the product is built, deployed, monitored, backed up and kept running. Coolify (bytedock.io) hosts local, dev and demo environments with synthetic or dev data only. AWS ap-southeast-2 hosts staging and production, provisioned with infrastructure as code from day one so the audited environment is the one customers actually use. Images are built once, scanned, signed and promoted.

What it does
Provides repeatable environments, a single build-and-promote pipeline, a background job runner with visible state, observability, a scrubbed browser error sink, encrypted backups with tested restores, and a storage lifecycle that never expires evidence. It also supports a siloed (dedicated single-tenant) stack from the same codebase as the pooled regional stack, a customer UAT sandbox, published recovery targets and per-tenant cost reporting.

Features
- Environments: local docker-compose, dev and demo on Coolify, staging and prod on AWS via IaC.
- AWS: ECS Fargate, RDS Postgres Multi-AZ with PITR, ElastiCache Redis, S3 with per-tenant prefixes and KMS, CloudFront, WAF, private subnets, Secrets Manager. Keep Fargate and RDS footprints small until real load arrives.
- Build once, scan, sign and promote images; required CI gates before promotion; branch protection, required reviews and a change log for SOC 2.
- Automated rollback and a migration pre-flight check against a production-size snapshot in the pipeline (accepted).
- Siloed-stack pipeline template parameterised by customer, region and KMS key, delivering the dedicated deployment option for IRAP and mining clients from one codebase (accepted).
- Job runner (arq recommended in Python) with idempotent jobs, time and memory limits, tenant-scoped queues and payloads, and job state persisted in Postgres because Redis is not the system of record. My jobs drawer in a notifications style with progress; admin queue view with status, retry and cancel; failure detail with correlation id. Cancellation checks the requester's permission. Emits job.completed and job.failed to notifications. Job status is not a competitive feature: keep it a small panel, not a product area.
- Observability: OpenTelemetry (ADOT) traces, structured JSON logs with tenant_id and request id and no PII, SLO alerts on latency, queue depth and failed jobs; liveness and readiness endpoints.
- Client error sink: anonymised, rate-limited (per IP and per tenant), size-capped, schema-validated, scrubbed of URLs, tokens and form values, no project or personal data; reports treated as hostile input and never rendered unescaped; forwards to the logging stack.
- Backups: encrypted, cross-AZ, in-region copies only; quarterly restore tests with recorded evidence; back up the Kaefer AIP Postgres now with PITR to RustFS or S3 and a documented restore test (accepted).
- Storage lifecycle: Standard, then Standard-IA after 365 days, then Glacier Instant after 7 years; no expiration rule ever on evidence.
- Customer UAT sandbox tenant seeded from a config bundle and reset on demand (accepted).
- Status page and incident template with RPO/RTO commitments in the contract pack (accepted).
- Per-tenant cost and usage reporting for storage, jobs and AI calls (accepted).
- Documented admin access paths with MFA and session logging; patch cadence.
- Running cost estimate at 500-5,000 users: USD 1.5-4k/month infra plus monitoring/WAF plus WorkOS per connection.

Interactions
- Tech stack: what gets deployed.
- Tenancy, organisations and data residency: pooled and siloed pipelines, per-region deployment, per-tenant KMS keys and prefixes.
- Security and compliance programme: pipeline controls and evidence.
- Data import, export and backup: customer backup and export.
- Testing and quality engineering: CI gates before promotion.
- Notifications: job events. Onboarding, imports, OCR, exports, report packs and integrations use the job runner via a type registry; other modules register handlers without touching the runner.

Data
- Job: type, tenant, project, asset, requester, status (queued, running, succeeded, failed, cancelled), progress, idempotency key, payload, result reference, error, correlation id, timeout, attempts, timestamps.
- JobEvent log.
- ClientErrorReport: release version, route, stack, user agent, tenant and project hashes; rate-limit counters (restricted insert-only path, short retention, consider time partitioning).
- StorageLifecyclePolicy and DeploymentInfo.
- Settings: job limits, retry policy, tenant queue quotas, log level and PII scrubbing, error rate limits, backup schedule, SLO thresholds, RPO/RTO, sandbox reset schedule.

Pages
- My jobs drawer (any user, own jobs; bottom sheet on mobile).
- Admin queue page (/admin/jobs) with retry, cancel, failure detail and bulk actions.
- Environments and deployments (/admin/ops/environments): health, versions, pipeline status, SLOs, recovery targets.
- Backups and restore evidence (/admin/ops/backups).
- Settings > Storage Lifecycle (planned): super-admin defaults and per-project overrides, permission storage_lifecycle:manage; renders s3-lifecycle.json and guards against any expiration rule on evidence.
- Ops settings, including sandbox reset.
- Developer error view via the logging stack (no end-user screen).

Decisions and notes
- AIP repo status: TASKS section 45 Docker/Coolify deployment built (real docker build not exercised in-session); operate/storage-lifecycle.md, infrastructure/s3-lifecycle.json and scripts/apply-s3-lifecycle.sh exist.
- Planned files: backend/app/modules/ops (models, jobs, client_errors, observability, health, storage_lifecycle), infrastructure/terraform, infrastructure/coolify, .github/workflows/build-promote.yml, scripts/restore-test.sh.
- Coolify is dev data only; the Kaefer AIP Postgres is intentionally not backed up today and the uploads volume is backed up daily to RustFS. To be fixed by the accepted backup item.
- Coolify should hold no production or client data.

Open questions
- Client error sink: build in-house, Sentry (self-hosted or AU region; tech stack advisor favours Sentry) or CloudWatch RUM? Owner has not decided.
- Job runner: arq, Procrastinate (tech stack advisor says either arq or Procrastinate fits), Celery or BullMQ (mentioned by earlier notes while the stack is Python).
- Tenancy model (pooled with RLS plus siloed option) and AGPL handling of the OpenConstructionERP reference are advised as urgent but belong to other modules; confirm owner decision.
- Terraform or CDK not yet chosen.

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
