# Project-AIP

Asset-centric inspection, quality and handover platform for EPC / megaproject teams, inspection firms
and main contractors. The first customer is Kaefer on Rio Tinto remediation projects. Multi-tenant SaaS
(AU / NZ / Asia / UK), targeting SOC 2, ISO 27001 and later IRAP.

**Status:** planning complete, build not started. See [tracking/PROGRESS.md](tracking/PROGRESS.md).

## Stack (see [ADRs](docs/adr/README.md))

Greenfield build (the old AIP code is not used). **Backend:** Python 3.12 · FastAPI · SQLAlchemy Core · Alembic ·
PostgreSQL (pooled tenancy, FORCE RLS) · Procrastinate jobs · Redis (cache only) · sandboxed Python workers for
IFC/OCR/PDF signing. **Frontends:** TypeScript · Vite + React (web, offline field PWA, client portal).
**Platform:** Keycloak (SSO broker) · Gotenberg · AWS ECS Fargate Sydney (Coolify for dev/demo) · OpenTofu.

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
| Data-tier stack | RLS/pooling patterns still apply; its TypeScript tool picks are superseded by review 08 and the Python-backend decision | [05](docs/reviews/05-stack-data.md) |
| App stack | Frontend and offline guidance still applies (Vite PWA, Dexie); backend parts superseded by review 08 | [06](docs/reviews/06-stack-typescript.md) |
| Development lead | P0 not executable as written; walking skeleton first; 40+ missing P0 tasks | [07](docs/reviews/07-delivery.md) |
| Stack & architecture | Mostly keep; Python backend + TS frontends; Postgres job queue, Vite SPAs, per-tenant KMS keys (adopted) | [08](docs/reviews/08-stack-decision.md) |

What we did about it: ADRs 0001–0008 resolve the contradictions, the board is ordered into waves starting
with an M0 walking skeleton, and owner decisions still needed are listed in OPEN-QUESTIONS.

## Working on this repo

```bash
python3 tools/next_task.py         # what to do next, and exactly which files to read
python3 tools/next_task.py --check # validate the board (also runs in CI)
```

One task per branch and PR, tests first, board and progress log updated in the same PR.
Full rules are in [AGENTS.md](AGENTS.md).
