# FORMS-04 — Template register and detail pages: JSON upload, revision history and compare

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: full spec written by FORMS-04 (2026-10-30) -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-03, FORMS-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`FORMS-01.md`](FORMS-01.md) (the template API these pages call: `apps/api/aip/modules/forms/routes.py`, `schemas.py`, and the generated `@aip/api-client` hooks `useFormsTemplates*`, `useFormsRevisions*`, `useFormsLint`)
3. [`docs/blueprint/modules/forms/README.md`](../../docs/blueprint/modules/forms/README.md) and [`routes.md`](../../docs/blueprint/modules/forms/routes.md) ("Template register", "Template detail", "Revision compare"; the designer, create wizard, settings and library pages are not this task)
4. [`DESIGN-03.md`](DESIGN-03.md) (register standard), [`DESIGN-04.md`](DESIGN-04.md) (RecordDetail, `confirm()`, toasts, states) and [`PROJECTS-06.md`](PROJECTS-06.md) (a register built on `RegisterTable`)
5. ADRs: [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) §4 (no designer in R1: templates are JSON), [0018](../../docs/adr/0018-module-groups-and-navigation.md) (forms surfaces under Settings), [0025](../../docs/adr/0025-time-and-timezones.md) (local time only at presentation), [0036](../../docs/adr/0036-r1-module-decisions.md)

## Spec

Give template admins a form template register at `/templates` and a template detail page at `/templates/$templateId` where they upload a template or a new draft revision as JSON (file or pasted) and see the server's lint issues, read the revision history, publish a draft, and compare two revisions as a structural diff of sections and fields (tag: extend).

The compare is a tab of the detail page (`?tab=compare&from=1&to=2`), not a separate route. The revision view is a read-only **outline** (sections and their fields) plus the raw JSON, not a rendered form.

> **Out of scope:** a visual designer (ADR 0007 §4), the FORMS-03 renderer preview (FORMS-03 is built in
> parallel; embedding `@aip/form-renderer` in the revision view is a follow-up once it merges), "restore as new
> draft" from the compare, template rename / retire / clone / export, the usage, report-mapping and audit tabs,
> and any server change. The list API has no cursor or sort (FORMS-01: ordered by code, `limit ≤ 200`), so the
> register shows up to 200 templates in code order; paging and sort are FORMS-09.

- **files**:
  - apps/web/src/features/forms/nav.ts
  - apps/web/src/features/forms/search.ts
  - apps/web/src/features/forms/templateJson.ts
  - apps/web/src/features/forms/issues.ts
  - apps/web/src/features/forms/diff.ts
  - apps/web/src/features/forms/columns.tsx
  - apps/web/src/features/forms/TemplatesRegister.tsx
  - apps/web/src/features/forms/JsonInput.tsx
  - apps/web/src/features/forms/IssueList.tsx
  - apps/web/src/features/forms/TemplateUploadDialog.tsx
  - apps/web/src/features/forms/RevisionDialog.tsx
  - apps/web/src/features/forms/TemplateDetail.tsx
  - apps/web/src/features/forms/RevisionHistory.tsx
  - apps/web/src/features/forms/RevisionOutline.tsx
  - apps/web/src/features/forms/RevisionCompare.tsx
  - apps/web/src/features/forms/forms.css
  - apps/web/src/features/forms/__tests__/fixtures.ts
  - apps/web/src/features/forms/__tests__/templateJson.test.ts
  - apps/web/src/features/forms/__tests__/diff.test.ts
  - apps/web/src/features/forms/__tests__/TemplatesRegister.test.tsx
  - apps/web/src/features/forms/__tests__/TemplateDetail.test.tsx
  - apps/web/src/routes/_app/templates/index.tsx
  - apps/web/src/routes/_app/templates/$templateId.tsx
  - apps/web/src/router.ts
  - config/terms/en-AU/forms.json (a self-contained `forms.templates.*` block)
  - e2e/web/form-templates.spec.ts
  - e2e/playwright.config.ts (add the spec to the skeleton lane)
- **steps**:
  - 1. `nav.ts`: `registerNavItem({id: "form-templates", section: "settings", to: "/templates", icon: "folder", termKey: "forms.templates.nav", permission: "form.view"})` (ADR 0018: Settings > Forms and rules). The pages need `form.view`; Upload, New draft, Replace draft and Discard draft render only with `form.manage`, Publish only with `form.publish`. The server checks every call.
  - 2. `search.ts`: the register's URL state in DESIGN-03's flat format (`kind`, `status`, `q`, `cols`) through `decodeRegisterQuery` / `encodeRegisterQuery`; one page size of 200 (the API maximum) and no sortable columns. `toListParams(query)` → `{kind?, status?, q?, limit: 200}`. The detail page's search `validateTemplateSearch` keeps `tab` (`revisions` | `compare`), `rev`, `from` and `to` (positive integers); anything else is dropped, never thrown.
  - 3. `/templates` (`TemplatesRegister`): `RegisterTable` with columns code (mono, a link to the detail page), name, kind (`forms.kind.<kind>`), status chip (`forms.template.status.<status>`), current revision (`v{n}` or "Not published"), updated (local time). Quick filters kind and status; search on code or name (the API's `q`). `useQuery` adapts `useFormsTemplatesList` to `{items, nextCursor: null}`. Enter on a row opens the detail page. With `form.manage`: an "Upload template" button and an empty-state call to action open `TemplateUploadDialog`.
  - 4. `templateJson.ts`: `parseTemplateJson(text)` → `{ok: true, schema, meta}` or `{ok: false, error: {messageKey, line?, column?}}`. Accepts either a revision schema (an object with `sections`) or an upload body (`{code?, name?, kind?, changeNote?, schema: {...}}`, whose other keys pre-fill the dialog's empty fields as `meta`). Empty text → `forms.templates.json.empty`; a parse error → `forms.templates.json.parse_error` with a 1-based line and column (from the engine's `position N` or `(line L column C)`); a non-object, or an object with neither `sections` nor `schema` → `forms.templates.json.not_a_template`. It does not lint: the server's `POST /lint` is the check.
  - 5. `JsonInput`: a labelled file input (`.json`, ≤ 512 KB, else `forms.templates.json.too_large`) whose text replaces a labelled monospace `<textarea>` (paste also works), the parse error shown under it, and a "Check" button (`POST /forms/lint`, `form.manage`) that lists the issues or announces "No issues found" in a `role="status"`.
  - 6. `issues.ts` + `IssueList`: normalise a lint `issues` array (`{path, code, message}`) and a request-validation `detail` array (`{loc, msg}`) into `{path, code, message}`; format a path as `sections[0].fields[2].key`. The list (`role="alert"` heading "The server found {count} issues") shows each issue's text from `forms.lint.<CODE>` when the code is a known lint code, else the server's message, and the path in mono.
  - 7. `TemplateUploadDialog` (`form.manage`): code, name, kind (native `<select>` over the five kinds), change note and `JsonInput`. Upload → `POST /forms/templates`; 201 → close, success toast, invalidate the list, open the new template's page; 422 `TEMPLATE_INVALID` → the `IssueList`, text kept; 409 `CODE_TAKEN` → the error on the code field; 422 request validation on `code`/`name` → the error on that field, other paths in the `IssueList`.
  - 8. `/templates/$templateId` (`TemplateDetail` on `RecordDetail`): id = code, title = name, status chip, breadcrumb back to the register, kind and current revision under the header; tabs `revisions|compare` controlled by the route search. Another tenant's id or a missing one renders DESIGN-04's `ErrorState` (404 → "Not found").
    - Header actions: with `form.manage` and no open draft, "New draft" opens `RevisionDialog` (empty JSON copies the published revision when there is one: `POST /templates/{id}/revisions` without `schema`); with an open draft, "Replace draft" (`PUT /revisions/{id}`) and "Discard draft" (`confirm`, danger → `DELETE`); with `form.publish` and an open draft, "Publish v{n}" (`confirm` → `POST /revisions/{id}/publish {expectedSyncVersion: template.syncVersion}`). 422 `TEMPLATE_INVALID` on publish shows the `IssueList`; 409 `VERSION_CONFLICT` / `REVISION_FROZEN` / `DRAFT_EXISTS` refetch and show an error toast. Every success invalidates the template and the list and shows a toast.
    - Revisions tab (`RevisionHistory`): a table, newest first: revision (`v{n}`), status chip, change note, published at (local time, or "—"), created at; a "View" button per row sets `?rev=n`. Below it, the selected revision (default: the open draft, else the current one) loaded with `useFormsRevisionsGet`: `RevisionOutline` (each section's label and key, then its fields: label, key in mono, field type from `item_types.field_type.<type>` when known else the raw type, "Required" when `required`, "Conditional" when it has `visibleIf`/`requiredIf`), the schema hash (mono) when published, and the JSON in a read-only `<pre>` behind a `<details>` toggle.
    - Compare tab (`RevisionCompare`): with fewer than two revisions an empty state; otherwise two labelled `<select>`s From and To (defaults: the two newest), held in `?from=&to=`, both revisions loaded, and the `diffSchemas` result as a summary line ("{added} added, {removed} removed, {changed} changed, {moved} moved") and a table: change chip, item (section or field), key (mono), section, details (each changed property as `name: before → after`, values as compact JSON). Equal revisions → "No structural differences".
  - 9. `diff.ts`: `diffSchemas(from, to)` → `{changes, counts}`. Sections are matched by `key`, fields by `key` across the whole revision (FORMS-01: one key namespace). A field in a different section is `moved` (with `fromSection`/`toSection`), also listing any changed properties; a field or section whose position among the keys both revisions share changed is `moved`. Changed properties compare every property but `key` (and `fields` for sections) by canonical JSON, so `visibleIf`, `validations`, `options`, `rules` changes all show. Top-level properties other than `sections` (`schemaVersion`) appear as `template` changes. Order: the target revision's order, with removed items after the section they were in.
  - 10. Register the two routes under `appRoute` in `apps/web/src/router.ts`. All text comes from `forms.*` keys in `config/terms/en-AU/forms.json` (the existing `forms.kind.*`, `forms.*.status.*` and `forms.lint.*` plus a new `forms.templates.*` block) and `item_types.field_type.*`.
- **acceptance**:
  - A template admin can, without the API docs, upload a JSON template from a file, see and fix a server-reported issue, open the template, start a second draft, publish it, and see what changed between v1 and v2.
  - A user with only `form.view` sees the pages read-only: no Upload, New draft, Replace, Discard or Publish controls.
  - Register filters, the detail tab and the compared revisions survive a reload and a copied URL.
  - Another tenant's template id shows the not-found state; every page has no serious or critical axe violations.
  - No hand-written fetch: every call goes through the generated `@aip/api-client`.
- **tests**:
  - **unit** (Vitest + Testing Library, API mocked with MSW in front of the generated client):
    - `parseTemplateJson('{"schemaVersion":1,"sections":[]}')` → ok with that schema and empty `meta`; `{"code":"x","name":"X","kind":"itp","schema":{"schemaVersion":1,"sections":[]}}` → ok, `meta = {code: "x", name: "X", kind: "itp"}`; `'{"sections": [}'` → `forms.templates.json.parse_error` with line 1 and a column ≥ 1; `"[1]"` and `'{"a":1}'` → `forms.templates.json.not_a_template`; `"  "` → `forms.templates.json.empty`.
    - `diffSchemas`: v1 (sections `prep` [`surface_prepared` boolean, `dft_avg` measurement mm], `final` [`remarks` text]) vs v2 (`prep` [`dft_avg` with `unit: "um"` and `required: true`, `blast_standard` dropdown], `final` [`remarks`, `surface_prepared`]) → `blast_standard` added in `prep`; `surface_prepared` moved `prep` → `final`; `dft_avg` changed with properties `required` (undefined → true) and `unit` ("mm" → "um"); counts `{added: 1, removed: 0, changed: 1, moved: 1}`. Removing a section reports it and each of its fields as removed. Identical schemas with keys in a different JSON order → no changes. A changed `visibleIf` → a `visibleIf` property change. `schemaVersion` changed → a `template` change.
    - `TemplatesRegister` with 2 templates → 2 rows with code, kind label and "v1" / "Not published"; choosing kind "ITP" requests `kind=itp`; with `["form.view"]` no "Upload template" button; with `form.manage` the dialog uploads a pasted body (`POST /forms/templates` receives code, name, kind and schema), and a mocked 422 `TEMPLATE_INVALID` with `issues [{path: ["sections",0,"fields",0,"type"], code: "UNKNOWN_FIELD_TYPE"}]` shows `forms.lint.UNKNOWN_FIELD_TYPE` text and `sections[0].fields[0].type`, keeping the text; 409 `CODE_TAKEN` puts an error on the code field; "Check" lists `POST /forms/lint` issues.
    - `TemplateDetail` with 2 revisions (v1 superseded, v2 published) → the history lists both, newest first; the outline of v2 shows the section label and the field keys; a 404 → "Not found"; with `["form.view"]` no New draft or Publish; with `form.manage` + `form.publish` and an open draft v3 → Publish sends `expectedSyncVersion` after confirm, and Discard sends `DELETE` after confirm; New draft with empty JSON posts no `schema`.
    - `RevisionCompare` via `?tab=compare&from=1&to=2` → the summary counts and a "Moved" row for `surface_prepared`.
    - axe (`axe-core`, serious and critical) on the register, the upload dialog with issues, the detail page on each tab → 0 violations.
  - **integration**:
    - None beyond FORMS-01: this task adds no server code. `pnpm --filter @aip/web typecheck` and lint pass.
  - **e2e** (`e2e/web/form-templates.spec.ts`, Playwright skeleton lane on the compose stack, `@skeleton`: `loginAs` with `tenantUsers()`, codes suffixed with `runId()`; not `@staging`, because published revisions cannot be deleted and would fill the demo tenant):
    - Main journey as the `kaefer-demo` admin (A): open `/templates` → Upload template → code `e2e-tpl-<run>`, kind Inspection, paste a schema with an unknown field type → Upload → the issue list shows `UNKNOWN_FIELD_TYPE` text → fix the type → Upload → the detail page shows the code and "Draft" → Publish v1 → "Published" → New draft with a changed schema (a field moved and one added) → Publish v2 → Compare tab with From v1, To v2 → the summary shows 1 added and 1 moved.
    - Cross-tenant: the `tenant-b` user (B) opens A's `/templates/<id>` → the not-found state; B's `/templates` register with `q=e2e-tpl-<run>` shows no rows.
    - Axe (`@axe-core/playwright`, serious and critical) on the register, the upload dialog showing issues, the detail page on both tabs, and B's not-found page → 0 violations.

## Delivery notes (2026-10-30, ClaudeK)

- Built on branch `claudeK/forms-04-template-pages` as specified; no server change. Every call goes through the generated `@aip/api-client` hooks; every label is a `forms.templates.*` key (one self-contained block in `config/terms/en-AU/forms.json`), plus the existing `forms.kind.*`, `forms.*.status.*`, `forms.lint.*` and ITEMTYPES-01's `item_types.field_type.*`.
- Routes `/templates` and `/templates/$templateId` (the blueprint paths); the compare is a tab (`?tab=compare&from=&to=`) and the shown revision is `?rev=`. The nav entry sits under Settings (ADR 0018), gated on `form.view`. The CSS is imported by the two route files, so `main.tsx` is unchanged.
- JSON parse errors report line and column from a small scanner (`jsonErrorOffset`), because V8's `JSON.parse` messages often name no position.
- The upload dialog also accepts a full upload body (`{code, name, kind, changeNote, schema}`) and pre-fills the fields the user left empty.
- API gaps recorded as **FORMS-09** (todo): the template list has no cursor or sort (the register asks for one page of 200, the API maximum, in code order), and revision summaries carry no `createdBy` / `publishedBy`.
- Follow-ups not on the board: embed the FORMS-03 renderer as a read-only preview in the revision view once FORMS-03 merges; "restore as new draft" from the compare (the API already supports it: `POST /templates/{id}/revisions` with the old schema).
- Tests: 42 Vitest cases in `apps/web/src/features/forms/__tests__` (parse, diff, search, register, upload dialog, detail actions, compare, axe). `e2e/web/form-templates.spec.ts` runs in the skeleton lane (`--project web --grep @skeleton`; added to `SKELETON` in `e2e/playwright.config.ts`). It was not run locally: it needs the compose stack and Keycloak.
- Noticed, not changed: `e2e/web/forms-templates-api.spec.ts` (FORMS-01) is tagged `@skeleton` but is not in the `SKELETON` list, so the skeleton job never runs it and the default lanes skip it for lack of credentials.
