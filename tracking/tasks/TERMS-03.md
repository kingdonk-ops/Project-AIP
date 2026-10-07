# TERMS-03 — ICU formatting and unit conversion
<!-- hand-edited: converted to Python backend per ADR 0001 (2026-10-07) -->

| Field | Value |
|---|---|
| Module | [`terms`](../../docs/blueprint/modules/terms/README.md) |
| Phase | P0 |
| Size | M |
| Depends on | TERMS-02 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/terms/README.md`](../../docs/blueprint/modules/terms/README.md)
3. ADRs: [0001](../../docs/adr/0001-greenfield-python-backend.md) (shared golden vectors for Python and TS), [0004](../../docs/adr/0004-repository-layout.md) (`packages/contracts`, `aip/platform/terms`)
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Format server-side messages and convert units for display while storing SI, with golden vectors that the TS client (TERMS-08) must also pass.

- **depends on**:
  - TERMS-02
- **files**:
  - apps/api/aip/modules/terms/icu.py
  - apps/api/aip/modules/terms/units.py
  - apps/api/aip/modules/terms/templating.py (Jinja filters for email and PDF templates)
  - apps/api/aip/modules/terms/api.py
  - apps/api/aip/modules/terms/tests/test_icu_units.py
  - packages/contracts/icu-vectors/icu-v1.json
  - packages/contracts/unit-vectors/units-v1.json
- **steps**:
  - 1. Implement `async format_message(conn, key, args, locale, **scope)` using the TERMS-02 resolver: parse with `pyicumessageformat` and render the AST in Python, using Babel (`babel.Locale(...).plural_form`, `babel.numbers.format_decimal`) for plural rules and numbers.
  - 2. Support `plural` (including `#` and `=0` exact matches) and `select`. Commit the cases as golden vectors in `packages/contracts/icu-vectors/icu-v1.json` (`{message, locale, args, expected}`), so the i18next-icu client in TERMS-08 runs the same file.
  - 3. Implement the unit table in `units.py` (mm/in, bar/psi, degC/degF; SI canonical: mm, bar, degC as stored by measurement fields) with `to_display(value_si, unit, system) -> Quantity(value, unit, decimals)` and `to_si(value, display_unit) -> float`. Use exact factors (1 in = 25.4 mm, 1 psi = 0.0689475729 bar, °F = °C × 9/5 + 32). Commit the conversions as `packages/contracts/unit-vectors/units-v1.json`.
  - 4. Add round-trip tolerance rules: `to_si(to_display(x))` equals `x` within 1e-9 relative (absolute 1e-12 near zero); display rounding (decimals per unit) happens only in formatting, never in conversion.
  - 5. Read the display unit system from `locale_settings`: project row first, then tenant row, then `metric`. Expose `display_system(conn, tenant_id, project_id=None)` from `api.py`.
  - 6. Register Jinja filters in `templating.py` (`t`, `fmt_measure`) that the email and PDF template environments load, so templates never hard-code labels or units.
- **acceptance**:
  - Plurals format correctly.
  - 25.4 mm displays as 1.00 in.
  - Round trip stays within 1e-9 relative.
  - The ICU and unit golden vectors pass in pytest.
- **tests** (pytest + Hypothesis; integration uses testcontainers-python Postgres):
  - **e2e**:
    - None here; the report engine tasks cover "PDF report for an imperial project shows psi and inches".
  - **integration**:
    - Project `locale_settings.unit_system = 'imperial'`: rendering a Jinja template `{{ 6.35 | fmt_measure('mm') }}` for that project gives `0.25 in`; for a metric project in the same tenant it gives `6.35 mm`. The stored value passed in stays in mm.
    - `format_message(conn, 'inspection.status.completed', {}, 'en-AU')` returns a tenant override when one exists, otherwise "Completed".
  - **unit**:
    - Format `'{n, plural, one {# defect} other {# defects}}'` gives `'1 defect'` for n=1 and `'3 defects'` for n=3.
    - `to_display(25.4, 'mm', 'imperial')` is `1.0 in` and formats as `1.00 in`.
    - `to_display(100, 'degC', 'imperial')` is `212 °F`; `to_display(10, 'bar', 'imperial')` is `145.04 psi` (2 dp).
    - Hypothesis: for finite x in [-1e9, 1e9] and every unit, `to_si(to_display(x))` equals x within tolerance.
    - Every case in `icu-v1.json` and `units-v1.json` passes.
