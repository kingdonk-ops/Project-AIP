# Architecture decision records

ADRs override the blueprint (see precedence in [AGENTS.md](../../AGENTS.md)). Copy
[0000-template.md](0000-template.md) to add one. Every ADR needs `- **Status:**` and `- **Date:**`
bullets and a row here; `tools/ci/check_adrs.py` enforces this in CI (`make check-docs`).

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-greenfield-python-backend.md) | Greenfield build: Python backend (FastAPI), TypeScript frontends; AIP code not used | accepted |
| [0002](0002-data-access-and-migrations.md) | SQLAlchemy Core + Alembic raw-SQL forward-only migrations; `with_tenant` + `SET LOCAL`; DB roles | accepted |
| [0003](0003-jobs-outbox-and-sidecar.md) | Procrastinate (Postgres) jobs; Postgres outbox; sandboxed Python workers | accepted |
| [0004](0004-repository-layout.md) | Repo layout: Python API/worker, three Vite TS apps (web, field PWA, portal) | accepted |
| [0005](0005-identity-architecture.md) | Keycloak handles all staff sign-in (SSO, password, MFA); backend issues sessions, field PIN, portal links, SCIM | accepted |
| [0006](0006-per-tenant-envelope-keys.md) | One AWS KMS key per tenant (reverses shared key; enables crypto-shred) | proposed |
| [0007](0007-mvp-scope-and-strangler.md) | Walking skeleton → trimmed P0 → R1 "Kaefer live" | proposed |
| [0008](0008-entitlements-and-commercial-model.md) | One entitlement service; sales-led; contract billing at launch | proposed |
| [0009](0009-ocr-and-licensing.md) | Only permissive open-source or AWS services; OCR = Tesseract + pypdfium2, Textract optional | accepted |
| [0010](0010-signoff-assurance.md) | Sign-off assurance: one quick check at signing (passkey, device+PIN, TOTP or IdP MFA), per-tenant minimum, countersign fallback | accepted |
| [0011](0011-licence-policy-details.md) | Licence check details: more permissive licences allowed; image OS packages judged as aggregation (AGPL/SSPL/Ghostscript still denied) | accepted |
| [0012](0012-runtime-roles-in-cluster-bootstrap.md) | Runtime DB roles (`aip_app`, `aip_jobs`, `aip_readonly`) are created by the superuser cluster bootstrap; revisions only verify and grant | accepted |
| [0013](0013-security-scanning-and-signing.md) | Security CI: permissive free scanners, expiring vuln exceptions, key-based cosign without public log | accepted |
| [0014](0014-ofl-fonts-allowed.md) | SIL OFL-1.1 allowed in the licence policy so IBM Plex fonts can be self-hosted | accepted |
| [0015](0015-tenant-row-and-tenant-resolution.md) | `tenants` read-only for the app (RLS `id = app.tenant_id`), shared fixture tenant ids, fail-closed tenant resolution errors | proposed |
| [0016](0016-job-runner-semantics.md) | Job runner on Procrastinate: queue tables in public with narrow grants, lock slots for the per-tenant cap, `max_attempts` = total tries, atomic enqueue | accepted |
| [0017](0017-company-systems-and-contract-link.md) | Company systems (CRM, contracts, invoicing, support, GRC) stay outside the product; `contract_ref` links a tenant to its contract; operator console on its own origin; no standing operator access to tenant data | accepted |
| [0018](0018-module-groups-and-navigation.md) | Six domain groups and a job-area menu as documentation overlay; no module merges now | accepted |
