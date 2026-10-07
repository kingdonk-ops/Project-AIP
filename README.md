# Project-AIP

Asset-centric inspection, quality and handover platform for EPC / megaproject teams, inspection firms
and main contractors. The first customer is Kaefer on Rio Tinto remediation projects. Multi-tenant SaaS
(AU / NZ / Asia / UK), targeting SOC 2, ISO 27001 and later IRAP.

**Status:** planning complete, build not started. See [tracking/PROGRESS.md](tracking/PROGRESS.md).

## Stack (see [ADRs](docs/adr/README.md))

TypeScript end to end: Node 22 · NestJS · Kysely · PostgreSQL (pooled tenancy, FORCE RLS) · Redis + BullMQ ·
Next.js (desktop) · Vite PWA (field, offline) · Vite (client portal) · Keycloak (SSO broker) · Gotenberg ·
Python sidecar for IFC/CAD/OCR · AWS ECS Fargate Sydney (Coolify for dev/demo) · OpenTofu.

## Repository map

| Path | What |
|---|---|
| [AGENTS.md](AGENTS.md) | **Start here if you're an agent.** The one-task loop and what to read |
| [tracking/BOARD.md](tracking/BOARD.md) | Every task, its wave, dependencies and status |
| [tracking/PROGRESS.md](tracking/PROGRESS.md) | Milestones and the change log |
| [tracking/OPEN-QUESTIONS.md](tracking/OPEN-QUESTIONS.md) | Decisions waiting on the owner |
| [tracking/tasks/](tracking/tasks/) | One spec file per task |
| [docs/adr/](docs/adr/README.md) | Architecture decisions. These override the blueprint |
| [docs/reviews/](docs/reviews/) | Specialist panel reviews of the blueprint |
| [docs/blueprint/](docs/blueprint/INDEX.md) | The product blueprint, split into 64 module folders + reference files |
| [tools/](tools/) | `next_task.py` (pick/validate tasks), `split_blueprint.py` (regenerate the split) |

## Specialist panel review (2026-10-07)

| Specialist | Verdict in one line | Review |
|---|---|---|
| Security | Strong intent, not yet safe to build: shared encryption key, unset credential policy, no upload/audit tasks | [01](docs/reviews/01-security.md) |
| Identity & login | Feasible if Keycloak only brokers SSO and the app issues all sessions; build SCIM in-app | [02](docs/reviews/02-identity-login.md) |
| SaaS platform | Excellent tenancy and config design; scope far too big; billing and entitlements missing | [03](docs/reviews/03-saas.md) |
| Enterprise readiness | Engineering controls good; DPA, SLA, sub-processors, DR and evidence clock missing | [04](docs/reviews/04-enterprise.md) |
| Data-tier stack | Python-era decisions (Alembic, arq) contradict the TS rebuild; use Kysely + SQL migrations + BullMQ | [05](docs/reviews/05-stack-data.md) |
| App stack | Sound stack; fix path chaos; offline field PWA should be a Vite app, not Next.js | [06](docs/reviews/06-stack-typescript.md) |
| Development lead | P0 not executable as written; walking skeleton first; 40+ missing P0 tasks | [07](docs/reviews/07-delivery.md) |
| Stack & architecture | Mostly keep; audit AIP before committing to the TS rebuild; switch to a Postgres job queue, Vite SPAs, per-tenant KMS keys | [08](docs/reviews/08-stack-decision.md) |

What we did about it: ADRs 0001–0008 resolve the contradictions, the board is ordered into waves starting
with an M0 walking skeleton, and owner decisions still needed are listed in OPEN-QUESTIONS.

## Working on this repo

```bash
python3 tools/next_task.py         # what to do next, and exactly which files to read
python3 tools/next_task.py --check # validate the board (also runs in CI)
```

One task per branch and PR, tests first, board and progress log updated in the same PR.
Full rules are in [AGENTS.md](AGENTS.md).
