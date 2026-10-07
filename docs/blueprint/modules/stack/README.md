# Tech stack (`stack`)

- **Group:** Foundations & architecture
- **Phase:** P0

What it is
The record of the product's technology stack: the languages, frameworks, libraries and services it is built with, and the one library chosen for each capability. It sits in Foundations and architecture (suggested phase P0). The product is AIP, already built in the owner's repo kingdonk-ops/erp with 48 phases done and deployed on Coolify. OpenConstructionERP (AGPL-3.0) is a feature reference only.

What it does
Resolves the conflict between the scope document (TypeScript rebuild with NestJS, Drizzle and React) and the running AIP stack (Python FastAPI, SQLAlchemy, Postgres/PostGIS, React/Vite/TypeScript). Advisors favoured continuing AIP, but the owner has decided on a TypeScript rebuild, and that decision wins. The scope document and ADR 0002 must record this single decision so auditors see one story. Library and licence choices feed the security review and SBOM. Swapping a library changes one adapter file and an environment setting, not calling modules.

Features
- Backend: TypeScript rebuild (Node 22; the scope doc named NestJS, Drizzle, Zod and BullMQ, but the owner has fixed Alembic raw-SQL migrations with templates and a Redis queue via arq or Celery, so framework and tooling details need reconciling). A Python sidecar remains for IFC, CAD and OCR
- Frontend: React with Next.js, TypeScript, TanStack Query/Table, shadcn/ui on Radix, Tailwind, dnd-kit (already in AIP), Dexie
- Generated typed API client from the API's OpenAPI schema with a CI check that the frontend builds against the current schema; generated output is never hand-edited (accepted)
- Data: PostgreSQL with ltree, JSONB, PostGIS, pgvector; Postgres FTS plus pgvector for search; Redis for queues and cache
- Identity: Keycloak self-hosted; local authentication built in-app on libraries; authorisation by a custom policy service plus RLS
- Files: S3 (AWS) in production, RustFS/MinIO on Coolify; pdf-lib/pdfcpu for stamping; Gotenberg (Chromium) for HTML-to-PDF
- Storage and queue adapter interfaces with RustFS/MinIO and S3 conformance tests, so the same code is proven on Coolify and AWS (accepted)
- Capability interfaces (PdfRenderer, Sealer, Ocr, ObjectStore, IdentityProvider) with swappable adapters
- Viewer: PDF.js plus Konva
- IFC: IfcOpenShell in a Python worker; That Open Engine (web-ifc) or xeokit in the browser; ODA or APS for DWG
- OCR: AWS Textract (Sydney) or OCRmyPDF/Tesseract
- Offline: PWA first, with service worker and IndexedDB (Dexie/RxDB)
- Form logic: JSONLogic as the single expression language, with a shared evaluator and test harness for forms, rules and workflows, instead of arbitrary JavaScript (accepted)
- AI: direct model vendor API
- Hosting and IaC: AWS ECS Fargate in Sydney; Terraform/OpenTofu
- ADR folder including a licence-decision record covering AGPL reference-only status and clean-room rules (accepted)
- Licence allow-list check in CI that blocks GPL/AGPL dependencies in the shipped image; CycloneDX SBOM per release (accepted)
- Pinned and scanned dependencies, with secrets hygiene, in both the Python and JS stacks

Interactions
- Architecture and module boundaries: implements the module boundaries
- Operations, hosting and deployment: decides how it is built, hosted and deployed
- Offline field app and sync: the field-app technology choice lives here
- Security and compliance programme: library and licence choices feed the security review and SBOM; an SBOM policy violation blocks a release
- Events emitted: platform.release.deployed, platform.dependency.vulnerability_flagged. Consumed: security.sbom.policy_violation

Data
- Built stack today: FastAPI, SQLAlchemy async, Alembic, PostGIS/ltree, React/Vite/TS, shadcn/ui, dnd-kit, docker-compose, deployed to Coolify (TASKS section 45). Phase 1 chose FastAPI over NestJS
- Files: dependency manifests and lockfiles for each stack, frontend package.json, OpenAPI client generator config, docker-compose.yml (api, worker, sidecar, postgres/postgis, redis, minio), tools/sbom.sh
- Docs: ADR 0002 stack decision (TypeScript rebuild, consequences, revisit triggers), 0003 capability library choices, 0004 AGPL clean-room (reference-only policy, legal review, provenance log)
- Optional platform-level tables (no customer tenant data): platform_adr_index (files remain source of truth), capability_adapter_settings (capability, adapter_key, non-secret config JSONB, nullable tenant_id for deployment default, unique per capability), and an SBOM/licence results table; add CI allow-list entries for global tables
- Config not code: adapter per capability via environment, dependency pins, licence allow-list, per-environment endpoints (Coolify vs AWS), expression dialect as a setting
- Settings: licence allow and deny lists, vulnerability severity SLAs, SBOM format and retention, exception approver role, pinned runtime versions

Pages
- ADR index (/admin/platform/adrs) and ADR detail (/admin/platform/adrs/:adrNo)
- Capability and library register (/admin/platform/capabilities) with conformance results and open questions
- Licence policy and exceptions (/admin/platform/licences): allow/deny lists, SBOM violations, time-boxed exceptions, provenance log link
- Platform version and generated client status: GET /api/v1/platform/version (build, commit, dependency versions); OpenAPI schema as the contract source; SBOM artefact per release
- Notifications: release deployed, vulnerability flagged, SBOM violation blocking release, licence exception expiring, client drift in CI

Decisions and notes
- Owner decisions: TypeScript rebuild; Next.js; Keycloak; PWA first; JSONLogic; Gotenberg; PDF.js plus Konva; Postgres FTS plus pgvector; Redis queue; Alembic raw SQL; AWS ECS Fargate Sydney; Terraform/OpenTofu; direct model vendor API; defer external e-signature provider
- Owner accepted: ADR folder with licence-decision record; CI licence allow-list; storage and queue adapters with conformance tests; single expression language; generated typed client with CI check
- Settle AGPL status in week 0, before schema design: take legal advice, use OpenConstructionERP only as a functional reference, write own specs and schemas from the owner's brief, keep a provenance log. Single-tenant on-prem delivery to Kaefer still counts as distribution. Kaefer and Rio Tinto procurement will ask about code provenance
- File pipeline hardening: presigned uploads to a quarantine bucket, ClamAV scan, magic-byte validation, size and decompression caps; IfcOpenShell, CAD, OCR and PDF renderers in sandboxed, network-isolated, non-root containers with resource limits; files served from a separate domain; SVG and HTML sanitised; EXIF GPS controlled; conversion outputs tenant-scoped
- BIM is phase 2, as inspection work mostly needs drawings, photos and PDFs
- Security advice stands: pin and scan dependencies, keep AGPL code out of the repo, and update the scope document

Open questions
- IFC browser viewer: That Open Engine or xeokit (licence check needed)?
- DWG: ODA commercial licence or APS fallback?
- OCR: AWS Textract (Sydney) or OCRmyPDF/Tesseract?
- Backend framework and ORM details under the TypeScript rebuild, given the owner's Alembic and Redis queue decisions (NestJS/Drizzle in the scope doc vs Python tooling for migrations and jobs)

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`advice-stack.md`](advice-stack.md) — Tech stack advisor
- [`advice-security.md`](advice-security.md) — Security advisor
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
