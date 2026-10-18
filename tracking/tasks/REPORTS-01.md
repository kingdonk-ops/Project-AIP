# REPORTS-01 — Report templates as data and the sanitised HTML render contract

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`report_engine`](../../docs/blueprint/modules/report_engine/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | PLAN-R1 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/report_engine/README.md`](../../docs/blueprint/modules/report_engine/README.md), and for columns only [`data-model.md`](../../docs/blueprint/modules/report_engine/data-model.md) (`report_templates`)
3. [`advice-security.md`](../../docs/blueprint/modules/report_engine/advice-security.md) (no network, no JavaScript, sanitised templates)
4. ADRs: [0002](../../docs/adr/0002-data-access-and-migrations.md) (SQLAlchemy Core, raw-SQL Alembic, `with_tenant`), [0004](../../docs/adr/0004-repository-layout.md) (`config/report-templates/`, only `api.py` crosses modules), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) (R1 scope, no designer), [0014](../../docs/adr/0014-ofl-fonts-allowed.md) (embedded fonts), [0025](../../docs/adr/0025-time-and-timezones.md) (UTC stored, local only at presentation), [0027](../../docs/adr/0027-default-role-permission-expansion.md) (permission verbs), [0036](../../docs/adr/0036-r1-module-decisions.md) (R1 decisions, reports store a hash only)
5. Code to copy patterns from: `apps/api/aip/modules/projects/` (module layout, `routes.py` with `requires(...)`, `tests/conftest.py`), `apps/api/aip/modules/terms/templating.py` and `loader.py` (Jinja filters, a config loader), `apps/api/migrations/versions/202610181200_approvals_decision_history.py`

## Spec

Create the `report_engine` module with versioned report templates stored as data (`config/report-templates/` packages loaded into `report_templates`, immutable once published) and one render contract that turns a template plus a data dict into a self-contained, script-free, network-free HTML document that REPORTS-02 hands to Gotenberg (tag: extend).

R1 has no template designer (ADR 0007, ADR 0036). A template is a package written by a developer or tenant admin: a JSON
definition, a Jinja2 body, a stylesheet and inlined assets. It is installed by the loader or uploaded through the API.
The data a template sees is a plain dict. Building that dict from a record (the data snapshot) is REPORTS-02's job, and
the inspection data is REPORTS-03's.

- **files**:
  - apps/api/aip/modules/report_engine/__init__.py
  - apps/api/aip/modules/report_engine/manifest.toml
  - apps/api/aip/modules/report_engine/api.py
  - apps/api/aip/modules/report_engine/tables.py
  - apps/api/aip/modules/report_engine/schemas.py
  - apps/api/aip/modules/report_engine/repository.py
  - apps/api/aip/modules/report_engine/service.py
  - apps/api/aip/modules/report_engine/policies.py
  - apps/api/aip/modules/report_engine/events.py
  - apps/api/aip/modules/report_engine/routes.py
  - apps/api/aip/modules/report_engine/jobs.py
  - apps/api/aip/modules/report_engine/template_package.py
  - apps/api/aip/modules/report_engine/html_policy.py
  - apps/api/aip/modules/report_engine/render.py
  - apps/api/aip/modules/report_engine/loader.py
  - apps/api/aip/modules/report_engine/tests/__init__.py
  - apps/api/aip/modules/report_engine/tests/conftest.py
  - apps/api/aip/modules/report_engine/tests/test_smoke.py
  - apps/api/aip/modules/report_engine/tests/test_html_policy.py
  - apps/api/aip/modules/report_engine/tests/test_render.py
  - apps/api/aip/modules/report_engine/tests/test_template_package.py
  - apps/api/aip/modules/report_engine/tests/test_templates_db.py
  - apps/api/aip/modules/report_engine/tests/fixtures/ (bad packages: `script-tag`, `external-img`, `onclick`, `css-import`, `include-tag`, `asset-too-large`)
  - apps/api/migrations/versions/<timestamp>_report_engine_templates.py
  - packages/contracts/report-templates/report-template.schema.json
  - config/report-templates/project-summary/internal/v1/template.json
  - config/report-templates/project-summary/internal/v1/body.html.j2
  - config/report-templates/project-summary/internal/v1/style.css
  - config/report-templates/project-summary/internal/v1/sample-data.json
  - config/report-templates/project-summary/internal/v1/assets/logo.png
  - config/terms/en-AU/report_engine.json
  - infra/docker-compose.yml
  - infra/coolify/docker-compose.coolify.yml
- **steps**:
  - 1. **Scaffold.** Run `python tools/new_module.py report_engine`. Manifest: `id = "report_engine"`,
    `context = "report_engine"`, `depends_on = ["tenancy", "terms"]`, `permission_namespaces = ["report"]`, and
    permissions `report.template.view` ("View report templates") and `report.template.manage` ("Upload, publish and
    retire report templates"). Per ADR 0027, `view` reaches every role with a `view` level on "Report engine &
    published records" and `manage` reaches `admin` roles only. Event `report.template_published` v1 (payload
    `{templateId, key, variant, version, recordType}`): a Pydantic model registered with
    `aip.platform.events.register_event` in `events.py`, as in `projects/events.py`.
  - 2. **Template package contract** (`packages/contracts/report-templates/report-template.schema.json`, JSON Schema
    2020-12, `additionalProperties: false` everywhere). `template.json` holds:
    - `key` (`^[a-z][a-z0-9-]{1,62}$`, stable across versions), `version` (integer ≥ 1), `variant` (`internal` |
      `client` | `certificate`), `recordType` (`^[a-z][a-z_]{1,40}$`, e.g. `project`, `inspection`), `nameKey` (a term
      key, never display text), `orientation` (`portrait` | `landscape`), `paper` (`A4` | `A3`), `marginsMm`
      (`{top, right, bottom, left}`, each 0–50), `termKeys` (the term keys the body uses, max 300),
      `assets` (array of `{name, contentType}`: `name` matches `^[a-z0-9][a-z0-9._-]{0,62}$` and is never
      `index.html`; `contentType` is `image/png` | `image/jpeg` | `image/webp` | `font/woff2`), `fontLicences`
      (required when a `font/woff2` asset is declared; each `OFL-1.1`, ADR 0014), `dataSchemaVersion` (integer,
      currently 1).
    - The package folder is `config/report-templates/<key>/<variant>/v<version>/` with `template.json`,
      `body.html.j2`, `style.css`, `sample-data.json` (data for previews and tests) and `assets/<name>`.
    - Limits: body ≤ 256 KB, stylesheet ≤ 128 KB, each asset ≤ 1 MB, all assets ≤ 4 MB, at most 20 assets. An
      asset's magic bytes must match its declared type (PNG `89 50 4E 47`, JPEG `FF D8 FF`, WebP `RIFF....WEBP`,
      WOFF2 `wOF2`).
  - 3. **`template_package.py`**: `load_package(path) -> TemplatePackage` (a folder) and `parse_package(body) ->
    TemplatePackage` (an API upload: the same parts as JSON, assets base64). Both validate against the JSON Schema
    (`jsonschema`), apply the limits, run `html_policy.check_template` on the body and `check_css` on the stylesheet,
    and compile the body in the sandbox (step 5). `content_sha256` is the sha256 (hex) of the RFC 8785 canonical
    JSON (`rfc8785`, as `approvals/decision_chain.py` uses it) of `{definition, body, css, sampleData, assets: {name:
    sha256}}`, so the same package always hashes the same. Every failure is a `TemplatePackageError(code, path,
    detail)` with a stable code: `SCHEMA_INVALID`, `ASSET_TOO_LARGE`, `ASSET_TYPE_MISMATCH`, `HTML_POLICY`,
    `CSS_POLICY` or `TEMPLATE_SYNTAX`.
  - 4. **`html_policy.py`** (stdlib `html.parser`, no new dependency): `check_html(html, *, asset_names) ->
    list[HtmlViolation]` and `check_css(css, *, asset_names) -> list[HtmlViolation]`. The same check runs on the
    template source (`check_template` first blanks out Jinja `{{ }}`, `{% %}` and `{# #}` spans) and on the rendered
    output.
    - Forbidden elements: `script`, `noscript`, `iframe`, `frame`, `frameset`, `object`, `embed`, `applet`, `link`,
      `base`, `meta`, `form`, `input`, `button`, `textarea`, `select`, `video`, `audio`, `source`, `track`,
      `portal`, `foreignobject` and `title` (the wrapper owns `<head>`).
    - Forbidden attributes: every `on*` handler, `srcdoc`, `formaction`, `http-equiv` and `ping`.
    - URL-bearing attributes (`href`, `src`, `srcset`, `xlink:href`, `poster`, `background`, `data`, `action`,
      `cite`, `longdesc`, `usemap`) may only hold a `#fragment`, a declared asset name, or a
      `data:image/(png|jpeg|webp);base64,` URI. Anything with a scheme (`http:`, `https:`, `file:`, `javascript:`,
      `ftp:`, `blob:`), a protocol-relative `//host`, a path (`/x`, `../x`) or an undeclared name is a violation.
      Entity-encoded and whitespace-split schemes (`jav&#x61;script:`, `java\tscript:`) are decoded before the check.
    - CSS (in `<style>`, `style=""` and `style.css`): `@import`, `expression(`, `-moz-binding` and `behavior:` are
      violations, and every `url(...)` follows the URL rule above (fonts may be `font/woff2` assets).
    - Each violation carries `{rule, element, attribute, line}`. The message never echoes more than 80 characters of
      the offending value.
  - 5. **`render.py`, the render contract.** `render_html(template: TemplateRow | TemplatePackage, data: Mapping,
    *, labels: Mapping[str, str], locale: str, time_zone: str, unit_system: UnitSystem) -> RenderedDocument`
    (`html: str`, `assets: dict[str, bytes]`, `page: PageSpec(paper, orientation, margins_mm)`). It is pure: no DB,
    no network, no clock.
    - Environment: `jinja2.sandbox.ImmutableSandboxedEnvironment(autoescape=True, undefined=StrictUndefined,
      loader=None, auto_reload=False)`. Remove the `safe` filter. `check_template` also rejects `|safe`,
      `{% autoescape false %}` and `markup`, and (by walking `env.parse(...)`) `Include`, `Import`, `FromImport` and
      `Extends` nodes, so a template can only use its own body.
    - Filters (no hard-coded labels or units):
      - `t(key, **args)` reads `labels`, which the caller has resolved and frozen. A key not declared in `termKeys`
        or missing from `labels` raises `RenderContractError('UNKNOWN_TERM_KEY')`. ICU arguments are formatted with
        `aip.modules.terms.api.format_message`.
      - `fmt_datetime(value, style='medium')` and `fmt_date(value)` take a UTC RFC 3339 string or `datetime` and
        show it in `time_zone` (an IANA zone, `zoneinfo`) with the zone abbreviation (ADR 0025).
      - `fmt_measure(value_si, unit)` uses `aip.modules.terms.api.to_display(value, unit, unit_system).format(locale)`.
      - `asset(name)` returns the declared asset's file name (a sibling file for Gotenberg) or raises `UNKNOWN_ASSET`.
    - The wrapper builds the whole document: `<!doctype html><html lang="{locale}"><head><meta charset="utf-8">`; a
      Content-Security-Policy meta `default-src 'none'; img-src data: file:; font-src data: file:; style-src
      'unsafe-inline'` (a second layer: templates may not add any `meta`); an `@page { size: <paper> <orientation>;
      margin: ... }` rule from the definition; the template stylesheet; then the rendered body.
    - Output limits: the rendered body is at most 5 MB (streamed with `generate()` and aborted above it with
      `RenderContractError('OUTPUT_TOO_LARGE')`). The rendered document goes through `check_html` again, so a data
      value such as `javascript:alert(1)` placed in an `href` fails with `RenderContractError('HTML_POLICY')`.
      Sandbox breaches (`jinja2.exceptions.SecurityError`) become `RenderContractError('SANDBOX')`.
  - 6. **Migration** `<timestamp>_report_engine_templates.py`: create `report_templates` by rendering
    `aip.platform.db.templates.render_template("tenant_table", table="report_templates", columns=...)`. That gives
    `tenant_id`, the uuid PK (UUIDv7, set by the app), `created_at`/`updated_at`/`deleted_at`, FORCE RLS with the
    fail-closed policy, and the template's `aip_app` grants.
    - Columns: `key text`, `version integer CHECK (version >= 1)`, `variant text CHECK (variant IN
      ('internal','client','certificate'))`, `record_type text`, `name_key text`, `orientation text CHECK
      (orientation IN ('portrait','landscape'))`, `paper text CHECK (paper IN ('A4','A3'))`, `definition jsonb`,
      `body text`, `css text`, `assets jsonb` (`{name: {contentType, sha256, sizeBytes, dataBase64}}`),
      `content_sha256 text CHECK (content_sha256 ~ '^[0-9a-f]{64}$')`, `status text CHECK (status IN
      ('draft','published','retired'))`, `source text CHECK (source IN ('config','upload'))`, `client_company_id uuid
      NULL` (branding later; no FK yet), `published_at timestamptz NULL`, `published_by uuid NULL`.
    - Constraints: `UNIQUE (tenant_id, key, variant, version)` (the data model's `(tenant_id, key, version)` plus
      `variant`, so one key carries its internal and client variants); index `(tenant_id, record_type, variant,
      status)`; `CHECK (status <> 'published' OR published_at IS NOT NULL)`.
    - Trigger `report_templates_published_immutable` (BEFORE UPDATE): when `OLD.status <> 'draft'` and any of `key,
      version, variant, record_type, definition, body, css, assets, content_sha256, orientation, paper` changes, raise
      SQLSTATE `23514` with the message `report template is published`. On a published row only `status`
      (`published` → `retired`) and `updated_at` may change, and only a draft may get a `deleted_at`.
  - 7. **Service and repository.** `TemplateService` (SQLAlchemy Core on the `with_tenant` connection):
    - `create_draft(conn, actor, package)` takes the next `version` for `(key, variant)` (`max + 1`, under
      `SELECT ... FOR UPDATE` of the existing rows). The package's own `version` must equal it, else 409
      `TEMPLATE_VERSION_CONFLICT`. Status `draft`, source `upload`.
    - `publish(conn, actor, template_id)` sets `published` and `published_at = now()`, and emits
      `report.template_published` v1 with `aip.platform.events.outbox.emit` in the same transaction. Publishing a
      non-draft → 409 `TEMPLATE_NOT_DRAFT`.
    - `retire(conn, actor, template_id)` sets `retired`. The row is kept for re-rendering pinned reports and never
      deleted.
    - `get_published(conn, key, variant) -> TemplateRow | None` (the highest published version), `get(conn,
      template_id)` (any status, this tenant only), `list(conn, *, record_type=None, status=None, cursor, limit)`.
    - `delete_draft(conn, template_id)` soft-deletes a draft only (409 `TEMPLATE_NOT_DRAFT` otherwise).
  - 8. **Routes** under `/api/v1/reports/templates`, each with `requires(...)` and `require_active_tenant` as in
    `projects/routes.py`, explicit `operation_id`s, and strict request models (`extra="forbid"`, an unknown key → 422):
    - `GET ""` (`report.template.view`, `reports_templates_list`): filters `recordType` and `status`, cursor paging
      (limit 1–200). Items omit `body`, `css` and asset data.
    - `GET "/{template_id}"` (`report.template.view`): definition, body, css, asset names and sizes.
    - `POST ""` (`report.template.manage`): the package as JSON → 201 draft. Package errors → 422 with
      `{code, path, detail}`.
    - `POST "/{template_id}/publish"`, `POST "/{template_id}/retire"` and `DELETE "/{template_id}"`
      (`report.template.manage`).
    - `POST "/{template_id}/preview"` (`report.template.view`) renders the template with its stored sample data
      (`definition.sampleData`), en-AU labels from `aip.modules.terms.api.bulk_resolve` and the tenant's display unit
      system. It returns `text/html` with the headers `Content-Security-Policy: default-src 'none'; img-src data:;
      style-src 'unsafe-inline'; font-src data:; sandbox` and `X-Content-Type-Options: nosniff`. Assets are inlined
      as `data:` URIs for the preview only.
    - Another tenant's template id → 404 `TEMPLATE_NOT_FOUND` (RLS hides the row).
  - 9. **Loader** `python -m aip.modules.report_engine.loader config/report-templates --tenant <uuid> [--tenant ...]`.
    Like `access.roles.cli seed-roles`, it runs as `aip_app` (`DATABASE_URL`) with one `with_tenant` transaction per
    tenant. Per package:
    - absent `(key, variant, version)` → insert as `published` with `source = 'config'` and emit
      `report.template_published`;
    - present with the same `content_sha256` → skip;
    - present with a different hash → exit 1 with `TEMPLATE_VERSION_CHANGED key=<key> variant=<variant>
      version=<n>`, writing nothing for that tenant (a changed template needs a new version folder).

    It prints `installed N, unchanged M` per tenant. Add a one-shot `report-templates-load` service to
    `infra/docker-compose.yml` after `tenancy-seed` (tenants `...0a` and `...0b`, as `access-seed` does) and to
    `infra/coolify/docker-compose.coolify.yml` for the demo tenant.
  - 10. **Example package** `config/report-templates/project-summary/internal/v1/`: record type `project`, portrait
    A4. It prints the project code and name, the status label (`t('project.status.' ~ project.status)`), the time
    zone, `fmt_datetime(project.createdAt)`, the tenant logo asset, and a footer with `generatedAt`. REPORTS-02 uses
    it as the smoke template. Its term keys go in `config/terms/en-AU/report_engine.json`
    (`report.template.project_summary`, `report.label.generated_at`, `report.label.page`, and an error text
    `report.error.<code>` for every code above).
  - 11. **Published interface** (`api.py`): `ReportTemplatesApi.get_published(conn, key, variant)`,
    `ReportTemplatesApi.get(conn, template_id)`, `render_html`, `RenderedDocument`, `PageSpec` and
    `RenderContractError`. In R1 only report_engine's own REPORTS-02 code renders; no other module builds PDF HTML.
- **acceptance**:
  - The scaffolded module plus the files above pass `make check` (ruff, pyright, manifest validation). The permission
    catalogue lists `report.template.view` and `report.template.manage` under `report_engine`.
  - The loader installs `project-summary/internal/v1` for both dev tenants. A second run reports `installed 0,
    unchanged 1`.
  - No path can change a published template's content: the API answers 409, and a direct `UPDATE` as `aip_app` fails
    with SQLSTATE 23514.
  - No template can produce HTML containing a script, an event handler, a frame, or any URL other than a declared
    asset, a fragment or an image `data:` URI. Such HTML is rejected at upload and again after rendering.
  - Rendering is deterministic: the same template, data, labels, locale and zone give byte-identical HTML.
- **tests**:
  - **unit**:
    - These run `test_html_policy.py`, `test_render.py` and `test_template_package.py` with no database.
    - `check_html('<p>ok</p><img src="logo.png">', asset_names={'logo.png'})` → `[]`.
    - `<script>x</script>` → 1 violation `forbidden_element:script`. `<SCRIPT>` and `<svg><script>` → the same rule.
    - `<img src="http://169.254.169.254/latest/meta-data/">` → `external_url`. `<img src="//evil.test/x.png">` →
      `external_url`. `<img src="file:///etc/passwd">` → `external_url`. `<img src="other.png">` with only `logo.png`
      declared → `undeclared_asset`.
    - `<a href="jav&#x61;script:alert(1)">` → `external_url`. `<p onclick="x()">` → `forbidden_attribute:onclick`.
      `<iframe srcdoc="...">` → 2 violations (the element and the attribute).
    - `check_css('@import url(https://x.test/a.css);')` → `css_import`. `div{background:url("https://x.test/a.png")}`
      → `external_url`. `@font-face{src:url(inter.woff2)}` with `inter.woff2` declared → `[]`.
    - `data:image/png;base64,iVBOR...` in `src` → `[]`. `data:text/html;base64,...` → `external_url`.
      `data:image/svg+xml,...` → `external_url`.
    - Template `{{ name }}` with `name = '<b>x</b>'` → the output contains `&lt;b&gt;x&lt;/b&gt;` (autoescape).
    - Template `{{ name|safe }}` → `TemplatePackageError('HTML_POLICY')` at load. `{% include 'x' %}` →
      `HTML_POLICY` with rule `include_not_allowed`.
    - Template `{{ ''.__class__.__mro__ }}` → `RenderContractError('SANDBOX')`. `{{ items.append(1) }}` on a list →
      `SANDBOX` (immutable sandbox).
    - Template `<a href="{{ link }}">x</a>` with `link='javascript:alert(1)'` → `RenderContractError('HTML_POLICY')`.
      With `link='#section-2'` → renders.
    - `{{ 'report.label.page' | t }}` with `labels={'report.label.page': 'Page'}` and the key in `termKeys` → `Page`.
      A key not in `termKeys` → `UNKNOWN_TERM_KEY`.
    - `fmt_datetime('2026-10-18T02:30:00Z')` with `time_zone='Australia/Perth'` → `18 Oct 2026, 10:30 am AWST`. With
      `Australia/Sydney` → `18 Oct 2026, 1:30 pm AEDT`.
    - `fmt_measure(0.0123, 'mm')` with the metric display system → `12.3 mm` (through `to_display`).
    - Definition `orientation: landscape`, `paper: A4` → the document contains `@page { size: A4 landscape;`, and
      `RenderedDocument.page.orientation == 'landscape'`.
    - A body that renders 6 MB (`{% for i in range(60000) %}` of 100 characters) → `OUTPUT_TOO_LARGE`.
    - The same inputs rendered twice → identical strings. `content_sha256` of the example package loaded twice →
      identical 64-hex strings; changing one byte of `style.css` changes it.
    - Each bad fixture package → its code: `script-tag` → `HTML_POLICY`, `external-img` → `HTML_POLICY`, `onclick` →
      `HTML_POLICY`, `css-import` → `CSS_POLICY`, `include-tag` → `HTML_POLICY`, `asset-too-large` (a 1.2 MB PNG) →
      `ASSET_TOO_LARGE`. A `.png` asset holding JPEG bytes → `ASSET_TYPE_MISMATCH`. `template.json` with an extra key
      `"script": "x"` → `SCHEMA_INVALID` with path `script`.
  - **integration**:
    - These run `test_templates_db.py` with pytest and testcontainers-python Postgres, the TESTING-01 tenants
      `kaefer-demo` and `tenant-b`, and permissions from a test grant provider as in `projects/tests/conftest.py`.
    - Run the loader for both tenants → 1 `report_templates` row per tenant with `status = 'published'`, `source =
      'config'` and `version = 1`, and 1 `report.template_published` row in `domain_events` per tenant. A second run
      prints `installed 0, unchanged 1`, still with 1 row and 1 event per tenant.
    - Change `style.css` in a temporary copy of the package without bumping the version, then run the loader → exit 1,
      the message contains `TEMPLATE_VERSION_CHANGED key=project-summary variant=internal version=1`, and the row is
      unchanged.
    - As a `report.template.manage` user, `POST /api/v1/reports/templates` with the example package as `version: 2`
      → 201, `status: 'draft'`. `POST .../publish` → 200, `status: 'published'`. The same package as version 2
      again → 409 `TEMPLATE_VERSION_CONFLICT`.
    - `POST` the `script-tag` fixture → 422 `{code: 'HTML_POLICY', path: 'body', ...}`, and no new row.
    - Publish a published row again → 409 `TEMPLATE_NOT_DRAFT`. `DELETE` a published row → 409.
    - As `aip_app` in a `with_tenant` transaction: `UPDATE report_templates SET body = '<p>x</p>'` on the published
      row → SQLSTATE 23514 `report template is published`. `UPDATE report_templates SET status = 'retired'` on the
      same row → 1 row updated.
    - Without `with_tenant`, `SELECT count(*) FROM report_templates` as `aip_app` → 0 (fail-closed RLS).
    - A `tenant-b` user calling `GET /api/v1/reports/templates/{kaefer template id}` → 404 `TEMPLATE_NOT_FOUND`.
      `GET /api/v1/reports/templates` as `tenant-b` → only `tenant-b`'s row.
    - A user without `report.template.view` → 403 on the list. With `view` but without `manage` → 403 on `POST`.
    - `POST .../preview` → 200 `text/html` with the CSP header above. The body contains the project code from
      `sample-data.json` and `data:image/png;base64,` for the logo, and no `http`.
  - **e2e**:
    - No Playwright journey: this task has no page and calls no Gotenberg, so the integration tests above cover the
      API contract. The first browser journey over reports is REPORTS-04 (register and download), and the first real
      PDF is REPORTS-02's integration test against the compose Gotenberg.
