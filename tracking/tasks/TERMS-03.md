# TERMS-03 — ICU formatting and unit conversion

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
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Format server-side messages and convert units for display while storing SI.

- **depends on**:
  - TERMS-02
- **files**:
  - backend/app/modules/terms/icu.py
  - backend/app/modules/terms/units.py
  - backend/tests/terms/test_icu_units.py
- **steps**:
  - 1. Implement format_message(key, args, locale) using the resolver and an ICU library.
  - 2. Support plural.
  - 3. Implement the unit table (mm/in, bar/psi, °C/°F) with to_display(value_si, unit, system) and to_si.
  - 4. Add round-trip tolerance rules.
  - 5. Read display units from project and tenant locale settings.
  - 6. Use them in the PDF and email template helpers.
- **acceptance**:
  - Plurals format correctly.
  - 25.4 mm displays as 1.00 in.
  - Round trip stays within 1e-9 relative.
- **tests**:
  - **e2e**:
    - PDF report for an imperial project shows psi and inches.
  - **integration**:
    - Project set to imperial: the thickness reading API returns display 'in' and the DB value remains in mm.
  - **unit**:
    - format '{n, plural, one {# defect} other {# defects}}' gives '1 defect' and '3 defects'.
    - to_display(25.4,'mm','imperial') is 1.0 in.
    - to_display(100,'degC','imperial') is 212 °F; 10 bar to 145.04 psi.
    - Hypothesis: to_si(to_display(x)) equals x within tolerance.
