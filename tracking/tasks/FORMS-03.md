# FORMS-03 — Form renderer package for the web (sections, field types, conditions)

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->
<!-- hand-edited: delivery notes added (FORMS-03 build) -->

| Field | Value |
|---|---|
| Module | [`forms`](../../docs/blueprint/modules/forms/README.md) |
| Phase | R1 |
| Size | M |
| Depends on | DESIGN-01, FORMS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`FORMS-01.md`](FORMS-01.md) (template contract) and [`FORMS-02.md`](FORMS-02.md) (evaluation semantics, `evaluateAnswers`)
3. ADRs: [0004](../../docs/adr/0004-repository-layout.md) (`packages/*`, Vite apps, Vitest, Playwright), [0007](../../docs/adr/0007-mvp-scope-and-strangler.md) §4 (web only, no offline, no designer in R1), [0025](../../docs/adr/0025-time-and-timezones.md) (dates shown in local time, stored as given)
4. Code: [`packages/ui/src/index.ts`](../../packages/ui/src/index.ts) (`FormField`, `Input`, `Select`, `Checkbox`, `Combobox`, `StatusChip`, `Button`), [`packages/ui/src/test/axe.ts`](../../packages/ui/src/test/axe.ts) and [`translate.ts`](../../packages/ui/src/test/translate.ts) (the `tKey` test translator), [`apps/web/src/routes/__fixtures/ui.tsx`](../../apps/web/src/routes/__fixtures/ui.tsx) with [`e2e/web/ui-fixture.spec.ts`](../../e2e/web/ui-fixture.spec.ts) (dev-only fixture page and its Playwright check)

## Spec

Add React components to `@aip/form-renderer` that render a frozen form revision as an accessible, editable or read-only form, driving visibility, required markers, validation messages and fail flags from the FORMS-02 evaluator, with no knowledge of the API so inspections (INSPECTIONS-04) can embed it (tag: extend).

> **Out of scope:** saving answers and the inspection page (INSPECTIONS-04), uploading files (the host passes a
> media adapter that calls the uploads pipeline), display-unit conversion (measurements are entered and shown in
> the field's SI unit in R1), the field app, offline, a designer preview (FORMS-04 may reuse this component).

- **files**:
  - packages/form-renderer/package.json
  - packages/form-renderer/src/index.ts
  - packages/form-renderer/src/exports.test.ts
  - packages/form-renderer/src/FormRenderer.tsx
  - packages/form-renderer/src/FormRenderer.test.tsx
  - packages/form-renderer/src/FormSection.tsx
  - packages/form-renderer/src/ErrorSummary.tsx
  - packages/form-renderer/src/adapters.ts
  - packages/form-renderer/src/labels.ts
  - packages/form-renderer/src/fields/registry.ts
  - packages/form-renderer/src/fields/TextField.tsx
  - packages/form-renderer/src/fields/NumberField.tsx
  - packages/form-renderer/src/fields/DateField.tsx
  - packages/form-renderer/src/fields/ChoiceFields.tsx
  - packages/form-renderer/src/fields/MeasurementField.tsx
  - packages/form-renderer/src/fields/BooleanField.tsx
  - packages/form-renderer/src/fields/MediaFields.tsx
  - packages/form-renderer/src/fields/ReferenceFields.tsx
  - packages/form-renderer/src/fields/fields.test.tsx
  - packages/form-renderer/src/form-renderer.css
  - packages/form-renderer/src/fixtures/coating-itr.json
  - config/terms/en-AU/forms.json
  - apps/web/package.json
  - apps/web/src/router.ts
  - apps/web/src/routes/__fixtures/form.tsx
  - e2e/web/form-renderer.spec.ts
- **steps**:
  - 1. `package.json`: add `react`/`react-dom` ^19 as peer dependencies and `@aip/ui: workspace:*` as a dependency; devDependencies as `packages/ui` (Testing Library, `vitest-axe`, `axe-core`, jsdom, `eslint-plugin-jsx-a11y`). Build like `packages/ui` (`tsc -p tsconfig.build.json`, CSS copied to `dist/form-renderer.css`); export `"."` and `"./styles.css"`.
  - 2. `adapters.ts` (the only way out of the package):
    - `MediaAdapter { pick(fieldKey, kind: "photo" | "signature"): Promise<{fileId: string; name: string} | null>; thumbnailUrl(fileId): string | null }`.
    - `ReferenceAdapter { search(kind: "asset" | "user", query): Promise<{id: string; label: string}[]>; label(kind, id): Promise<string | null> }`.
    - `RendererAdapters { media?: MediaAdapter; references?: ReferenceAdapter }`. A missing adapter renders the field read-only with `forms.renderer.adapter_missing`, never a crash.
  - 3. `FormRenderer` props: `schema: FormSchema`, `answers: Answers`, `onChange(next: Answers, changedKey: string)`, `mode: "draft" | "submit"`, `context?`, `t: Translate` (the `@aip/ui` type), `adapters?`, `readOnly?`, `showErrors?: "touched" | "all"` (default `"touched"`), `serverErrors?: AnswerError[]` (errors the API returned, shown like local ones), `id?`.
    - It calls `evaluateAnswers(schema, answers, {mode, context})` in a `useMemo` on every render. Hidden sections and fields are not rendered (not just visually hidden), and their answers are left untouched in `answers` (the server ignores them, FORMS-02).
    - Each section is a `<fieldset>` with a `<legend>`; each field uses `@aip/ui` `FormField` so label, hint (`helpKey`) and error are wired by id; required fields get `aria-required="true"` and a visible marker with the text `t("forms.renderer.required")` for screen readers.
    - Errors show after the field is blurred (`"touched"`) or for every field once the host sets `showErrors="all"` (after a submit attempt). Error text = `t(error.messageKey, error.params)`.
    - Failed answers (`evaluation.failed`) show `StatusChip` with `t("forms.answer.failed")` next to the field and the field's `failMessageKey` when set; the chip has text, not colour only.
    - `ErrorSummary` (rendered when `showErrors="all"` and there are errors): a `role="alert"` list linking each error to its field; activating a link focuses the control.
    - `labels.ts`: a field or section label is `labelKey ? t(labelKey) : label`; option labels the same.
  - 4. Field components (`fields/registry.ts` maps registry type → component; an unknown type renders `t("forms.renderer.unsupported_field", {type})` in a read-only row):
    - `text` → `Input` (`maxLength` from validations); `number` → `Input inputMode="numeric"`, `decimal` → `inputMode="decimal"`; typed text is parsed with `Number`, an unparsable entry is kept as the raw string so the evaluator reports `WRONG_TYPE` (never silently dropped).
    - `date` → native `<input type="date">` (value `YYYY-MM-DD`, no time-zone shift).
    - `dropdown` → `Select`; `multi_select` → a group of `Checkbox`es in a nested `<fieldset>`.
    - `measurement` → `Input inputMode="decimal"` with the unit symbol `t("forms.unit.<unit>")` as a visible suffix (keys for the SI storage units `mm`, `bar`, `degC`, symbols as in `packages/contracts/unit-vectors/units-v1.json`); value `{value, unit: field.unit}`.
    - `boolean` → two radio buttons (`forms.renderer.yes` / `forms.renderer.no`) so "not answered" stays distinct from "no".
    - `photo` → "Add photo" button calling `media.pick`, a list of thumbnails with alt text = file name and a remove button each; `signature` → "Sign" button calling `media.pick(fieldKey, "signature")`, then the signed file name and a "Clear" button.
    - `asset_ref` / `user_ref` → `Combobox` over `references.search` (debounced 250 ms), showing `references.label` for the stored id.
    - In `readOnly` mode every component renders its value as text (dates as given, options by label, references by label, photos as thumbnails) with no controls.
  - 5. `config/terms/en-AU/forms.json`: `forms.renderer.required`, `.yes`, `.no`, `.add_photo`, `.remove_photo`, `.sign`, `.clear_signature`, `.search_placeholder`, `.unsupported_field`, `.adapter_missing`, `.error_summary_title`, `.not_answered`; `forms.unit.mm`, `forms.unit.bar`, `forms.unit.degC`.
  - 6. `apps/web`: add `@aip/form-renderer: workspace:*`; `routes/__fixtures/form.tsx` (dev only, registered in `router.ts` beside `/__fixtures/ui` and loaded only when `!import.meta.env.PROD`) renders `fixtures/coating-itr.json` with in-memory stub adapters, the app's `t`, a "Submit" button that sets `showErrors="all"`, and a "Read-only" toggle, under `data-testid="form-fixture"`.
- **acceptance**:
  - Every FORMS-02 field type renders, edits and shows read-only; the same answers give the same visibility, required markers, errors and fail flags as `evaluateAnswers` (the component never computes them itself).
  - Hidden fields are absent from the DOM and the accessibility tree; changing a controlling answer shows or hides dependent fields immediately.
  - The package has no network code: files and references go only through the adapters.
  - No hard-coded UI text: every renderer string is a `forms.renderer.*` or `forms.answer.*` key, with en-AU defaults.
  - 0 serious or critical axe violations in Vitest and in the Playwright fixture, in editable, read-only and all-errors states.
- **tests**:
  - **unit** (Vitest + Testing Library, `tKey` translator, `vitest-axe`):
    - Render `coating-itr.json` with `{}` → `surface_prepared` radios present, `remarks` absent; click "no" → `onChange` called with `{surface_prepared: false}` and `changedKey "surface_prepared"`; rerender with that answer → `remarks` textbox present.
    - Rerender with `{surface_prepared: true, remarks: "old"}` → `remarks` absent and `onChange` not called (the stale answer is untouched).
    - `showErrors="all"`, `mode="submit"`, `{}` → `ErrorSummary` lists `forms.answer.REQUIRED` for `blast_standard`; clicking that link focuses the blast-standard select.
    - `dft_avg` typed `0.18` → `onChange` with `{dft_avg: {value: 0.18, unit: "mm"}}`; rerendered → a chip with text `forms.answer.failed`. Typed `abc` → stored `{value: "abc", unit: "mm"}` and, after blur, `forms.answer.WRONG_TYPE`.
    - A field with `type: "gps"` → the text `forms.renderer.unsupported_field{type=gps}`, no throw.
    - `photo` with no media adapter → `forms.renderer.adapter_missing`; with a stub `pick` returning `{fileId: "f1", name: "blast.jpg"}` → one thumbnail with alt `blast.jpg`, and `onChange` gets `[{fileId: "f1"}]`.
    - `serverErrors=[{fieldKey:"blast_standard", code:"NOT_AN_OPTION", messageKey:"forms.answer.NOT_AN_OPTION", params:{}}]` → shown under that field without a blur.
    - `readOnly` with a full answer set → no `input`, `select` or `button` elements; `blast_standard` shows its option label.
    - Every required visible field has `aria-required="true"` and is reachable by `getByLabelText`.
    - axe: 0 violations for the editable, read-only and all-errors renders.
    - `exports.test.ts`: `index.ts` exports exactly `FormRenderer`, the adapter types, `evaluateAnswers`, `validateGuard`, `evaluateGuard`, `GuardError`, `ALLOWED_OPERATORS`, `EVALUATOR_VERSION` and the FORMS-02 types.
  - **integration**:
    - No API surface in this task. The renderer's agreement with the server is covered by FORMS-02's shared vectors (both evaluators) and by INSPECTIONS-02/04, which validate the same answers on the server.
  - **e2e**:
    - `e2e/web/form-renderer.spec.ts` on the `web-dev` project (`/__fixtures/form`, like `ui-fixture.spec.ts`): main journey — answer "Surface prepared: No" → the remarks field appears; choose blast standard `Sa 2½`; enter DFT `0.18` → a "Fail" chip; click Submit → the error summary lists the unanswered required fields; answer them → the summary is gone; toggle Read-only → values shown as text. axe (`@axe-core/playwright`) → 0 serious/critical violations in the editable, all-errors and read-only states, on desktop Chromium and mobile Chrome. The fixture is dev-only design scaffolding with no tenant data, so there is no cross-tenant case here; cross-tenant isolation of templates is checked by FORMS-01 and of answers by INSPECTIONS-04.

## Delivery notes (2026-10-30, branch `claudeK/forms-03-renderer`)

Judgement calls and deviations from the spec above:

- **Exports.** `index.ts` keeps FORMS-02's `truthy` export (removing it would break that published surface); otherwise it exports exactly the list in the tests block. The package also exports `./fixtures/coating-itr.json`, so the web fixture page imports the fixture without a deep relative path.
- **Group fields.** `@aip/ui` `FormField` labels one control by id, so `boolean`, `multi_select`, `photo` and `signature` render through `GroupFrame` in `fields/FieldFrame.tsx` (an extra file): a `<fieldset>` named by its legend, with the same hint/error wiring and classes. Only the boolean radiogroup carries `aria-required`; ARIA does not allow it on a plain group, so a required multi-select, photo or signature field shows the visible marker only.
- **Required marker.** The marker is visible text (`forms.renderer.required`) placed after the field, outside the label, so screen readers do not hear "required" twice (`aria-required` already says it).
- **Extra term keys.** `forms.renderer.error_summary_item` (`{field}: {message}`) builds each summary link without concatenating text in code; `forms.renderer.remove_photo` takes `{name}`, so each remove button has a unique name.
- **Combobox.** `@aip/ui` `Combobox` takes only `id`/`aria-label` and keeps its query to itself, so `ReferenceFields.tsx` reads the query from the input's bubbling change event and copies `aria-describedby`/`aria-invalid`/`aria-required` onto the input in an effect. `packages/ui` was not changed.
- **Photo names.** Answers store only `{fileId}` and `MediaAdapter` has no name lookup, so a thumbnail's alt text is the file name only for files picked in this session; otherwise it falls back to the field label. INSPECTIONS-04 may want a `name(fileId)` on its adapter.
- **Read-only.** Read-only mode shows values and fail chips, but no errors and no error summary (there are no controls to fix or focus).
- **Tests.** The package's Vitest environment is now jsdom (React components). FORMS-02's two vector suites read files via `import.meta.url`, so they are pinned to `// @vitest-environment node` and are otherwise unchanged (the runtime-exports list in `jsonlogic.test.ts` gains `FormRenderer`). `src/test/{setup,axe,translate}.ts` copy the small `packages/ui` test helpers, which that package does not export.
- **Fixture page.** `/__fixtures/form` evaluates in `draft` mode until Submit, then in `submit` mode with `showErrors="all"`.
