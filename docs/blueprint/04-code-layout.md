# Folders, files and shared code

> NOTE: this section describes the old AIP codebase, which is NOT used. The backend is a greenfield
> Python build; the canonical module layout is `apps/api/aip/modules/<name>/` in ADR 0004 and the
> frontends are Vite apps. Where this text differs (paths, `services/api/app`, `frontend/`), ADR 0004 wins.


- **module template**:
  - **backend**:
```
modules/<name>/
  __init__.py  - exports only the public interface from api.py
  api.py  - published service interface (Protocol + functions) other modules may import
  models.py  - SQLAlchemy tables using platform mixins (tenant_id, uuid, timestamps, sync_version)
  schemas.py  - Pydantic request/response and event payload models
  repository.py  - queries; extends the generic repository, only custom queries here
  service.py  - business logic and use cases; the only writer to this module's tables
  policies.py  - permission checks and scope rules registered into the platform catalogue
  events.py  - domain events emitted and handlers for events consumed
  routes.py  - thin FastAPI router; declares the register or CRUD from config where possible
  workflow.py  - links to a workflow definition key and guard rule keys (no state logic inline)
  jobs.py  - background job handlers registered with the worker
  module.toml  - manifest: id, permissions, nav entry, terms keys, events, allowed dependencies
  tests/
    test_service.py  - integration tests on real Postgres
    test_policies.py  - rows of the permission matrix
    test_isolation.py  - tenant and IDOR scenarios
```

  - **frontend**:
```
features/<name>/
  index.ts  - public exports (routes and hooks) used by the app shell only
  routes.tsx  - route definitions and lazy pages registered in the shell
  api.ts  - thin wrappers and TanStack Query hooks over the generated client
  pages/
    ListPage.tsx  - DataTable driven by column config
    DetailPage.tsx  - tabs: details, activity, comments, files
  columns.ts  - column and filter definitions for the data table
  forms.ts  - form schema or template key for the form renderer
  components/  - module-specific components that are not reusable elsewhere
  permissions.ts  - ability keys from the generated catalogue used to gate UI
  terms.ts  - label keys used by this feature
  offline.ts  - sync scope and Dexie stores, only if the module is field-capable
  __tests__/  - component tests and Playwright journey fragments
```

- **repo tree**:
```
erp/
  services/
    api/
      pyproject.toml
      importlinter.ini
      app/
        main.py
        container.py
        config/
          settings.py
        platform/
          db/ (session, rls, base model mixins, outbox)
          crud/ (generic repository, register router factory)
          access/ (policy engine, permission catalogue)
          workflow/ (state machine, approval routes)
          forms/ (schema validation, revisions)
          rules/ (JSONLogic/CEL evaluator)
          audit/ (hash-chained log, outbox consumer)
          events/ (event bus, outbox relay)
          files/ (upload, quarantine, storage port)
          notify/ (channels, preferences, digests)
          terms/ (dictionary, overrides)
          identity/ (WorkOS verify, local auth, magic link)
          tenancy/ (context, scope chain)
          search/ (FTS, saved views)
        modules/
          assets/
          item_types/
          components/
          scope_work/
          inspections/
          eligibility/
          issues/
          documents/
          inventory/
          equipment/
          certificates/
          diary/
          procurement/
          ... (one folder per selected module)
        api_v1.py
    worker/
      app/
        main.py
        jobs/ (thin job adapters calling module services)
    sidecar/
      ifc/
      cad/
      ocr/
      contracts/ (JSON schema for sidecar IO)
  frontend/
    package.json
    src/
      app/ (shell, router, providers, scope bar)
      platform/
        ui/ (shadcn wrappers, tokens)
        data-table/
        form-renderer/
        workflow-bar/
        comments/
        files/
        terms/
        access/
      features/
        assets/
        inspections/
        ... (one folder per module)
      portal/ (separate origin entry)
      field/ (offline PWA entry: Dexie, sync)
  packages/
    api-client/ (generated from OpenAPI)
    permissions/ (generated catalogue)
    terms-keys/ (generated keys + defaults)
    config-schemas/ (JSON schema for forms, workflows, rules, report templates)
  migrations/
    versions/ (forward-only raw SQL, one folder per module prefix)
    tests/ (up-down-up)
  config/
    workflows/ (preset definitions as data)
    report-templates/
    terms/ (en-AU default, market packs)
    ref-packs/
  infra/
    docker-compose.yml
    coolify/
    terraform/ (ECS, RDS, S3, KMS, WAF, per environment)
  tests/
    isolation/
    permission-matrix/
    workflow/
    audit-chain/
    contract/ (sidecar)
    e2e/ (Playwright)
  docs/
    adr/
    modules/
  tools/
    scaffold/ (new-module generator)
    codegen/ (openapi, permissions, terms)
```

- **rules**:
  - Modules import only another module's api.py (or events); import-linter contracts fail CI on any import of models, repository, or service from another module.
  - Only a module's service.py writes its tables; other modules never query them directly, and cross-module reads go through api.py or the read model.
  - Cross-module side effects happen through domain events via the transactional outbox, never by calling another module inside a request transaction.
  - platform/ never imports from modules/; modules depend downward on platform only, and the dependency direction is enforced by the same lint config.
  - Each module declares its permissions, terms keys, nav entry, events and allowed dependencies in module.toml; the catalogue, nav, and terms are generated from manifests.
  - Status models, approvals, validation and reminders are configuration (workflow, rules, forms definitions in config/ or DB), not code in a module; a new status is a data change.
  - Every table uses platform mixins (tenant_id, uuid, timestamps, sync_version) with FORCE RLS; a CI check fails any table missing tenant_id or RLS policy.
  - Frontend features import only from platform/, packages/ and their own folder; ESLint no-restricted-imports blocks feature-to-feature imports, and shared pieces are promoted to platform/.
  - No literal user-facing strings: labels use terms keys, and a lint rule flags hard-coded JSX text and status names.
  - The API client and permission catalogue are generated, never edited by hand; CI regenerates and fails on diff.
  - Migrations are forward-only raw SQL, namespaced per module, and each PR touching a model must include its migration; up-down-up runs in CI.
  - Worker jobs are thin adapters that call module services, must be idempotent, and carry tenant context explicitly.
  - Sidecar interaction goes only through platform/files with versioned JSON contracts and contract tests; modules never call it directly.
  - A new module is created with tools/scaffold so layout, tests, manifest and lint registration are identical every time.
- **shared**:
  -
    - **name**: platform/crud (register factory)
    - **purpose**: Generic repository and router factory producing list, filter, sort, paginate, create, update, soft-delete, and bulk endpoints from a declarative register config, with tenant scoping and optimistic concurrency built in.
    - **removes duplication of**: Per-module CRUD routes, pagination, filtering, soft-delete and sync_version handling
  -
    - **name**: frontend DataTable
    - **purpose**: Config-driven table with server-side paging, saved views, column chooser, bulk actions, export, and tree mode, fed by the same register config the API exposes.
    - **removes duplication of**: Hand-built list pages, filter bars, saved view logic, and CSV export per module
  -
    - **name**: FormRenderer + forms engine
    - **purpose**: One renderer (web and PWA) and one server validator for versioned form schemas covering field types, conditionals, calculations and attribute schemas; used by templates, item types, permits and admin forms.
    - **removes duplication of**: Separate inspection forms, attribute editors, permit forms, and validation code on client and server
  -
    - **name**: platform/workflow
    - **purpose**: Data-defined state machines and approval routes with roles, guards from the rules engine, side effects via events, a generic WorkflowBar UI and approvals inbox.
    - **removes duplication of**: Per-module status enums, transition checks, and approver logic for inspections, issues, documents, POs, and variations
  -
    - **name**: platform/access + permissions package
    - **purpose**: Single policy engine (role, project, team, asset subtree, deny by default) generating the catalogue, route guards, UI ability checks and the permission-matrix tests.
    - **removes duplication of**: Scattered permission checks, duplicated UI visibility logic, and hand-written authz tests
  -
    - **name**: platform/audit + events (outbox)
    - **purpose**: Transactional outbox, event bus, and hash-chained append-only audit writer; activity feeds and timelines are views over it.
    - **removes duplication of**: Manual audit inserts, ad hoc activity feed tables, and direct cross-module calls for side effects
  -
    - **name**: platform/files
    - **purpose**: Presigned and resumable upload, quarantine-scan-validate-release pipeline, sidecar dispatch, thumbnails, storage port with tenant prefixes, and a shared attachment component.
    - **removes duplication of**: Per-module upload endpoints, file validation, storage paths, and attachment widgets
  -
    - **name**: platform/notify + comments
    - **purpose**: Event-driven notifications (in-app, email, push, chat) with preferences and digests, plus one threaded-comments service keyed by record type and id.
    - **removes duplication of**: Per-module email sending, reminder cron jobs, and comment tables
  -
    - **name**: platform/terms + terms-keys package
    - **purpose**: Key-based dictionary with tenant and client overrides applied to UI, emails, PDFs and exports; keys generated from module manifests.
    - **removes duplication of**: Hard-coded labels and status names, and per-market forks of text
  -
    - **name**: packages/api-client (codegen)
    - **purpose**: TypeScript types and TanStack Query client generated from FastAPI OpenAPI in CI; fails the build if the committed output drifts.
    - **removes duplication of**: Hand-written frontend types, fetch wrappers, and DTO drift between backend and frontend
  -
    - **name**: platform/rules + eligibility interface
    - **purpose**: Rule expressions evaluated server-side for validation and workflow guards, plus one is_valid_for(subject, step) call used by inspections, scopes and equipment.
    - **removes duplication of**: Scattered expiry and compliance checks and hard-coded gate conditions
