# Tech stack and architecture decision review

**Scope:** the brief, owner decisions, advisor summaries, ADRs 0001–0008, reviews 02/03/05/06/07, and the arch, offline and tenancy module READMEs. This is a review at the design stage. There is no code in this repo, and the AIP FastAPI source is not here either.

**Bottom line:**
- **Python vs TypeScript:** for a solo builder with a live customer, continuing the Python backend probably beats a TypeScript rebuild. It isn't a landslide. I recommend a one-week audit of the AIP code with pass/fail criteria (below) before any rebuild code is written, with "continue Python" as the default.
- **Everything else holds up well whichever language wins.** Most of the architecture is sound and language-neutral: modular monolith, pooled Postgres with RLS, outbox, Postgres search, Gotenberg, JSONLogic, ECS in Sydney.
- **Four specific changes are worth making:**
  1. Use a Postgres-backed job queue instead of BullMQ.
  2. Build all three frontends as Vite SPAs instead of Next.js plus two Vite apps.
  3. Use one AWS KMS key per tenant instead of app-held data keys under a shared key. As written, ADR 0006 cannot crypto-shred S3 data.
  4. Keep Coolify off the critical path.

---

## 1. TypeScript rebuild vs continue Python FastAPI AIP

| Option | Pros | Cons | Risk | Effort before Kaefer sees new value |
|---|---|---|---|---|
| **A. TS rebuild (current, ADR 0001)** | One language across API, web, field app and portal. Shared Zod contracts, JSONLogic evaluator, terms and sync types. Clean RLS-first schema with no retrofit. NestJS structure suits agents. | Throws away 48 shipped phases. The SaaS review estimates 9–15 months solo to P1 parity, or 4–6 months for a trimmed R1. Needs a big-bang data migration and cutover. The golden tests need AIP specs the agents don't have (07-delivery Q1). Still two languages: PAdES signing (pyHanko), IFC and OCR all sit in the Python sidecar. | High: time-to-value and cutover | Highest |
| **B. Continue AIP, evolve it in place** (advisor view) | Kaefer keeps getting features every month. No data migration. The domain logic already works: ltree, review lifecycle, hold points, RSW gate, certificate hard-block. Best libraries for signing, IFC, OCR and WeasyPrint sit in-process. Two owner decisions (Alembic, arq/Celery) only make sense on this path. | AIP was built single-tenant: org isolation is in app code (Phase 24) and status flows are hardcoded. So the foundation work (tenant_id plus RLS everywhere, outbox, workflow engine, terms keys, audit chain, new identity) touches most tables either way. JSONLogic would run in Python on the server and JS on the client, so the two can drift. All 8 ADRs and about 33 tasks would need rewriting, but those are documents and cheap. | Medium: retrofit could be messier than it looks | Lowest |
| **C. Strangler with a mixed backend** (new modules in TS, old in Python) | Gradual move | Two backends, two RLS and session layers, two auth stacks. The worst of both for one person. | High | High |
| **D. Python backend plus all-TS frontends** (B made explicit) | End-to-end types through OpenAPI → openapi-typescript/orval. TS where it matters most: field PWA, portal, form renderer. | Offline sync and form rules need shared JSON Schema contracts and golden test vectors across the two languages. | Medium | Low |

**Assessment:**
- **AI agents** are about equally productive in Python (with pyright strict and Pydantic) and TypeScript.
- **Hiring** is fine for both in AU and UK.
- **"End-to-end type safety"** is achievable on both paths through generated OpenAPI clients.
- **Library fit favours Python.** PAdES/LTV sealing has no mature Node equivalent to pyHanko, and sealing is on the records path, not a later IFC nicety.
- **The decisive factors are time-to-value and cutover risk with a paying customer, and both favour B/D.**
- **Where the TS rebuild genuinely wins:** sharing one rules evaluator and one sync model between client and server, and a clean RLS-first schema.

**Verdict: CHANGE to D (continue the AIP Python backend, all frontends in TS). Confidence medium, about 60%. It depends on a 5-day AIP audit.** Keep the TS rebuild only if the audit fails or one of the conditions below holds.

**Audit pass criteria** (continue Python if most of these pass):
- AIP has meaningful automated tests on the core lifecycles.
- Adding tenant_id with FORCE RLS and a `SET LOCAL` session hook is mechanical, roughly under 30% of files.
- Status flows can be extracted behind a workflow interface without rewriting the screens.
- The schema can be repaired forward with Alembic.
- The owner can comfortably review Python code written by agents.

**What would have to be true for the TS rebuild to be right:**
1. The AIP code fails the audit (tangled, untested, or the tenancy retrofit touches most of it).
2. The owner reviews TS far better than Python. For a solo builder supervising agents, the reviewer's fluency is the binding constraint.
3. Kaefer agrees in writing to new features only on the new platform, with an R1 date of about 6 months (ADR 0007).
4. TS hires are planned within 12 months.
5. Shared client/server rule evaluation is treated as a hard requirement.

If the owner stays with TS, sections 2–10 below already assume it, and ADR 0007 (AIP keeps running, trimmed R1) becomes mandatory rather than "proposed".

## 2. Architecture style
| Option | Pros | Cons |
|---|---|---|
| **Modular monolith + worker + sidecar (current)** | One deployable, one transaction boundary for RLS and outbox, cheap to run, matches the team size | Boundaries depend on lint (dependency-cruiser) and discipline |
| Microservices | Independent scaling | Distributed transactions, a tenant context to carry across hops, N times the SOC 2 surface. Absurd for one person. |
| Serverless (Lambda) | Scales to zero | Chromium/PDF jobs, connection pooling with `SET LOCAL`, cold starts, harder to keep long sync uploads alive |

**Verdict: KEEP. Confidence high.** Gotenberg and the sidecar should be separate ECS services with no egress, as planned. Count Keycloak as a fourth service in the ops budget.

## 3. Backend framework (TS path)
| Option | Pros | Cons |
|---|---|---|
| **NestJS on the Fastify adapter (current)** | Opinionated modules and DI that map onto the bounded modules. Agents produce consistent code from lots of examples. Guards and pipes suit the policy service and Zod. | Decorator metadata (Vitest needs swc). Heavier. DI does not enforce module boundaries. |
| Fastify plus awilix/plain modules | Lighter, faster, fewer abstractions | Agents invent structure task by task, so drift creeps in |
| Hono | Small, fast, edge-friendly | Built for edge runtimes, thinner ecosystem for enterprise auth and OpenAPI |

**Verdict: KEEP-WITH-CONDITIONS. Confidence medium-high.**
- Controllers stay thin.
- Cross-module effects go only through the outbox.
- `forwardRef` needs an ADR.
- On the Python path, FastAPI is already in place.

## 4. Data access and migrations
| Option | Pros | Cons |
|---|---|---|
| **Kysely + forward-only SQL via node-pg-migrate (ADR 0002)** | SQL-first. Handles ltree, pgvector, FTS, partitions and RLS without fighting the tool. An explicit `Trx` handle makes "no query outside `withTenant`" a compile error. | Needs hand-written codecs for ltree and vector. Less "magic" than an ORM. |
| Drizzle | Popular, good TypeScript ergonomics, RLS helpers now exist | drizzle-kit wants to own the DDL, which clashes with hand-written RLS SQL. Needs custom types. |
| Prisma | Best developer experience for basic CRUD | Opaque engine. `SET LOCAL` only works inside interactive transactions, which is fragile. ltree, vector and tsvector are `Unsupported`. |

**Verdict: KEEP. Confidence high.**
- The owner still has to retire the "Keep Alembic" decision text.
- On the Python path, the equivalent is SQLAlchemy 2 Core plus Alembic with raw-SQL operations, which is what the owner originally decided.

## 5. Tenancy
| Option | Pros | Cons |
|---|---|---|
| **Pooled Postgres + FORCE RLS, fail-closed `set_config(...,true)` (current)** | One schema and one migration run. Cheapest. Isolation enforced in the database. Same schema can be deployed as a silo. | Every pooler, worker and cache path must carry tenant context. RLS mistakes are silent. |
| Schema-per-tenant | Feels more isolated | Migrations fan out N times, search_path pitfalls with poolers, no real audit gain over RLS |
| DB-per-tenant | Strongest isolation, simple per-tenant restore | Cost and ops multiply. Only justified by contract. |

**Verdict: KEEP. Confidence high.** Conditions:
- The PgBouncer transaction-mode isolation test runs as a permanent CI job.
- No RDS Proxy on the RLS path.
- Write a silo-criteria ADR: IRAP PROTECTED or a contractual mandate triggers a silo, built only on a signed contract and priced as Enterprise.
- The cross-tenant role for the dispatcher and purge jobs is decided in writing (narrow BYPASSRLS role or SECURITY DEFINER functions). This is a SOC 2 question.

## 6. Jobs and events
| Option | Pros | Cons |
|---|---|---|
| **BullMQ + Postgres outbox + Postgres `jobs` state (ADR 0003)** | Mature: delays, repeats, rate limits, Bull Board | State lives in two places (Redis transport plus Postgres record). Needs an outbox→BullMQ dispatcher (a dual-write hop). **Per-tenant fairness ("groups") is a paid BullMQ Pro feature**, so the fairness ADR 0003 promises needs custom code. Adds Redis to the durability, backup and DR story. |
| **pg-boss or Graphile Worker** | Enqueue happens in the same transaction as the domain change: atomic, no dispatcher bridge for jobs. One state store. Backups and PITR cover jobs. Testcontainers needs only Postgres. Easily handles this workload (hundreds of jobs per minute at 5,000 users). | Adds load to the primary database. Smaller ecosystem and admin UI. Fairness is still custom code. |
| SQS | Managed, very durable | AWS-only (breaks Coolify/dev parity), no transactional enqueue, still needs the outbox |

**Verdict: CHANGE to a Postgres-backed queue (Graphile Worker or pg-boss). Confidence medium (about 65%).**
- Keep the `domain_events` outbox for audit, timeline and replay.
- Keep Redis for cache, rate limits, session cache and SSE pub/sub only.
- Python-path equivalent: Procrastinate.
- Tripwire to move transport to BullMQ or SQS: sustained queue load above about 15% of database CPU, or more than about 200 jobs per second.

## 7. Identity
| Option | Pros | Cons |
|---|---|---|
| **Keycloak as federation broker only; app issues all sessions and credentials; SCIM built in-app (ADR 0005)** | Self-hosted in Sydney (fits residency and IRAP). No per-connection fees. Battle-tested SAML, avoiding XML-signature pitfalls. Clean revocation through opaque cookies. | A Java service to run HA, patch and monitor, with its own database, and it's in SOC 2 scope. Brokered MFA claims are inconsistent. The app still builds passwords, MFA, WebAuthn, magic links, PIN and SCIM, a large security-critical surface. |
| WorkOS (SSO + Directory Sync) | Fastest to SSO and SCIM. Customer IT self-service admin portal. Removes the need to build an in-app SCIM server. | About USD 125 per connection per month for each of SSO and SCIM (confirm pricing). US processing (Privacy Act APP 8 disclosure). Not IRAP-assessed. Vendor lock-in for federation. |
| Auth0 / Okta CIC | Has an AU region, broad features | Expensive for B2B enterprise connections. Overlaps with the in-app credential decision. |
| Zitadel (self-hosted) | Go, lighter than Keycloak, multi-tenant organisations built in | Smaller ecosystem. Verify SCIM server maturity before relying on it. |
| Fully in-app SAML (`@node-saml`, or python3-saml/pysaml2) | No extra service | XML signature-wrapping risk you own. Recurring CVEs in xml-crypto-class libraries. |

**Verdict: KEEP-WITH-CONDITIONS. Confidence medium.** Conditions:
- Pin Keycloak 26.x, two ECS tasks, its own database, realm configuration as code (keycloak-config-cli).
- Patching SLA of 14 days or less for critical CVEs.
- Treat the in-app SCIM server and the ≤60 s deprovisioning target as R1 must-haves only if Kaefer requires SCIM. Otherwise use JIT provisioning first.
- **Tripwire to switch to WorkOS:** Keycloak ops takes more than about 2 days a month, or SSO customers want self-service setup and no IRAP deal is in sight.

## 8. Frontend and offline
| Option | Pros | Cons |
|---|---|---|
| **Next.js desktop + Vite field PWA + Vite portal (current, ADR 0004)** | Next has the largest ecosystem. The field app is correctly kept off the App Router. | Two frameworks and two routing and data models for one person. Adds a Node SSR tier to run, scale and secure (RSC/middleware CVEs in 2025 show that surface is real), with no SEO need. The BFF is redundant because NestJS already issues the cookies. |
| **Vite + React + TanStack Router for all three** | One toolchain and routing model. Static assets on S3/CloudFront, so no SSR service. Desktop screens can reuse offline-core later. Trivial for agents to keep consistent. Wraps cleanly in Capacitor. | No SSR or RSC, so bundles must be code-split. Overturns an owner decision. |
| Single Next.js app for everything | One framework | Offline boot only works as a static export, which removes Next's value. Portal isolation gets harder. |

**Verdict: CHANGE to Vite SPAs for desktop, field and portal. Confidence medium (about 65%), and preference-sensitive.**
- Serve each SPA through CloudFront, with `/api/*` path-routed to the ALB, so cookies stay same-origin `__Host-` cookies.
- The portal keeps its own origin.
- If the owner insists on Next.js for desktop, it is acceptable with minimal server components and no business logic in the Next server.

**Offline approach:**
- **Dexie with a custom cursor-pull and idempotent-push sync engine: KEEP. Confidence medium-high.**
  - PowerSync and ElectricSQL read the replication stream and bypass RLS. Their own sync rules would duplicate authorisation outside Postgres, adding a service to certify and a second isolation model for auditors.
  - They are worth revisiting only for very large offline datasets, and wa-sqlite/OPFS is the next step before that.
- **Add a Capacitor-ready condition:** the same Vite build should be wrappable for iOS (avoids the 7-day storage eviction, gives MDM distribution, better camera access).
- **Tripwire for Capacitor:** iOS eviction or lost data shows up in the Kaefer offline pilot, or devices can't be installed to the Home Screen.

## 9. Search, PDF and rules
**Search: Postgres FTS + pg_trgm + pgvector — KEEP. Confidence high.**
- OpenSearch adds about USD 300–700 a month for a multi-AZ minimum, another tenant-isolation surface and an indexing pipeline.
- pgvector caveat: tenant filtering after an HNSW index scan can return too few results. Use `hnsw.iterative_scan` (pgvector 0.8) and test recall with a small tenant next to a large one.
- Tripwire: more than about 10M indexed chunks, or p95 search latency above 500 ms after tuning.

**PDF: Gotenberg (Chromium) — KEEP-WITH-CONDITIONS. Confidence medium-high.**
- Alternatives considered:
  - Puppeteer in the worker: same engine, but you own the browser sandbox.
  - WeasyPrint: better paged-media CSS, no JavaScript, Python only.
  - Prince or DocRaptor: best print typesetting, paid licence.
  - Typst: deterministic and fast, but not HTML.
  - react-pdf: weak at complex layouts.
- Conditions: no egress, fonts embedded, PDF/A output where records require it, and per-tenant concurrency caps.
- **Gap:** PAdES sealing is not decided. Put pyHanko plus KMS in the sidecar and plan it for R1/R2. On the TS path, that makes the sidecar a critical-path dependency, not a "later" item.

**Rules: JSONLogic — KEEP-WITH-CONDITIONS. Confidence medium-high.**
- Against CEL: JSONLogic is a JSON AST that visual builders such as react-querybuilder emit natively, and it runs in browsers. CEL reads better, is typed and has cost limits, but its JS and Python ports are less mature.
- Conditions:
  - Pin one evaluator (json-logic-js semantics) with an allow-listed operator set and no custom operations that have side effects.
  - Store the evaluator version on each form revision.
  - Ship shared golden vectors in `packages/contracts`.
  - On the Python path, CI must run those vectors against the Python evaluator, or the server must call a small Node evaluator.

## 10. Hosting, IaC and keys
**Hosting: ECS Fargate in ap-southeast-2 + OpenTofu — KEEP. Confidence high.**

| Option | Pros | Cons |
|---|---|---|
| **ECS Fargate in Sydney (current)** | RDS with pgaudit and PITR. Sydney services are IRAP-assessed. Low ops. | AWS lock-in, which is acceptable |
| Azure Container Apps (Australia East) | Viable, also IRAP-assessed, fits Microsoft-heavy customers | Weaker Postgres features than RDS |
| EKS | Flexible | Kubernetes ops for one person |
| Fly.io | Has Sydney and is simple | Weaker enterprise compliance and managed Postgres story |
| Render | Simple | No AU region (verify), so it fails residency |

**Coolify: KEEP-WITH-CONDITIONS.**
- Demo and dev only, synthetic data only.
- M0 deploys straight to AWS staging, as ADR 0007 already says.
- Never maintain two production-grade deploy definitions.

**Keys (ADR 0006) — KEEP the intent, CHANGE the mechanism. Confidence high.**
- **The flaw:** SSE-KMS encrypts S3 objects under the KMS key named in the request. An app-held tenant data key plays no part, so deleting the wrapped tenant key does not make that tenant's S3 objects unreadable. The planned crypto-shred does not work.
- **The fix:** one customer-managed KMS key per tenant, about USD 1 per month each.
  - Set it on the presigned PUT (`x-amz-server-side-encryption-aws-kms-key-id`) and enforce it with a bucket policy per tenant prefix.
  - Use the same key to wrap data keys for field-level encrypted columns.
  - Crypto-shred = legal-hold check, then schedule key deletion (7–30 day window).
  - This also leaves room for BYOK later.
- **Document the limits:** rows in RDS are deleted, not shredded, and backups age out within PITR retention (35 days or less). Manual snapshots need a purge procedure.

---

## Summary
| Decision | Current | Verdict | Confidence | One-line reason |
|---|---|---|---|---|
| Backend language | TS rebuild | **CHANGE (gated)**: continue Python backend, TS frontends | Medium (60%) | Time-to-value, no cutover, pyHanko/IFC/OCR fit. The audit decides. |
| Architecture style | Modular monolith + worker + sidecar | KEEP | High | Right size, one RLS/outbox transaction boundary |
| Framework (TS path) | NestJS (Fastify) | KEEP-WITH-CONDITIONS | Med-high | Structure helps agents; boundaries come from lint, not DI |
| Data access | Kysely + SQL migrations | KEEP | High | SQL-heavy Postgres features; Prisma and Drizzle fight RLS or DDL |
| Tenancy | Pooled + FORCE RLS | KEEP | High | Correct; silo as a deploy variant on contract |
| Jobs | BullMQ + outbox | **CHANGE**: Graphile Worker / pg-boss | Medium | Transactional enqueue, one state store; BullMQ fairness is a Pro feature |
| Identity | Keycloak broker + in-app sessions | KEEP-WITH-CONDITIONS | Medium | Residency and IRAP fit; ops burden is the tripwire |
| Frontend | Next + Vite + Vite | **CHANGE**: Vite SPAs ×3 | Medium | One toolchain, no SSR tier, offline/Capacitor-ready |
| Offline | Dexie + custom sync | KEEP + Capacitor-ready | Med-high | Keeps RLS as the only isolation model |
| Search | Postgres FTS + pgvector | KEEP | High | Enough at this scale; no second isolation surface |
| PDF | Gotenberg | KEEP-WITH-CONDITIONS | Med-high | Solid; add a PAdES (pyHanko) plan |
| Rules | JSONLogic | KEEP-WITH-CONDITIONS | Med-high | Builder-friendly; pin the evaluator plus golden vectors |
| Hosting | ECS Fargate Sydney + OpenTofu | KEEP | High | Compliance-ready, low ops |
| Keys | Per-tenant data key under a shared KMS key | **CHANGE**: per-tenant CMK | High | As specified, it cannot crypto-shred S3 objects |

## Changes we should make now (ranked)
1. **Run the 5-day AIP audit and record the result in ADR 0001** (continue Python, or rebuild in TS with ADR 0007 mandatory). Nothing else should start before this.
2. **Fix ADR 0006:** per-tenant KMS keys, SSE-KMS key ID enforced on presigned uploads, documented limits for database and backups.
3. **Replace BullMQ with Graphile Worker or pg-boss** (Procrastinate on the Python path). Update ADR 0003 and OPS-01/02.
4. **Rewrite ADR 0004 frontends as three Vite SPAs** behind CloudFront path routing, keeping a Capacitor-wrappable field build. Get owner sign-off, since this overturns "Next.js".
5. **Decide PAdES sealing** (pyHanko plus KMS in the sidecar) and when the sidecar is needed. On the TS path it moves earlier.
6. **Keycloak runbook ADR:** HA, own database, realm as code, patch SLA, plus the WorkOS tripwire.
7. **Retire contradictory owner decision text** (Alembic, arq/Celery, "shared key", "Direct model vendor API" vs Bedrock Sydney) so agents stop getting mixed signals.

## Tripwires (revisit if any of these happen)
- **AIP audit fails, or the owner commits to TS hires:** go to the TS rebuild under ADR 0007.
- **R1 slips more than 2 months past its ADR date on either path:** cut scope further. Do not swap stacks again.
- **Postgres queue load above about 15% of database CPU, or more than about 200 jobs per second:** move job transport to BullMQ or SQS.
- **Keycloak ops above about 2 days a month, or 3 or more customers asking for self-service SSO setup with no IRAP deal:** move to WorkOS.
- **Pilot shows iOS eviction or data loss, or IndexedDB queries too slow:** move to Capacitor, then wa-sqlite/OPFS.
- **FTS p95 above 500 ms or more than 10M chunks:** add OpenSearch.
- **A contract requires IRAP PROTECTED or a dedicated deployment:** build the silo stack, priced as Enterprise.

## Top 3 risks of the final stack
1. **Offline sync is a custom build on iOS PWA limits.** It is the riskiest component on any stack: no Background Sync, 7-day eviction, memory limits for large drawings. Mitigations: build the sync engine as a pure state machine, property-test it with fast-check (or Hypothesis on the Python path), and run a real-device Kaefer pilot before committing to a release scope.
2. **Delivery capacity versus scope (64 modules for one person).** The language choice moves this risk around but doesn't remove it. Mitigations: enforce ADR 0007/0008 scope governance, buy Vanta or Drata, and have the operator author configuration until customer #2 pays.
3. **Security-critical surface built in-house.** Tenant isolation across the pooler, workers, caches and S3, plus an in-app credential stack (passwords, MFA, WebAuthn, magic links, PIN, SCIM). Mitigations: generated isolation and IDOR tests as CI gates from M0, an external pen test before go-live, and keeping bearer credentials narrow, as the security reviews specify.

## Files reviewed
- `/home/user/Project-AIP/docs/blueprint/00-brief.md`, `01-decisions.md`, `02-advisor-summaries.md`
- `/home/user/Project-AIP/docs/adr/0001` through `0008`. 0003, 0004 and 0006 need the changes above.
- `/home/user/Project-AIP/docs/reviews/02-identity-login.md`, `03-saas.md`, `05-stack-data.md`, `06-stack-typescript.md`, `07-delivery.md`
- `/home/user/Project-AIP/docs/blueprint/modules/{arch,offline,tenancy}/README.md`
