# Equipment & fleet (`equipment`)

- **Group:** Field operations
- **Phase:** P1

Owned and hired equipment, vehicles and test instruments.

A register of plant, vehicles and instruments (UT gauges, DFT gauges, holiday detectors) with maintenance schedules, pre-start checks, calibration certificates and internal hire charging. Equipment out of calibration is blocked from use by the eligibility gate.

Features:
- Equipment and vehicle register (uses the Equipment/Vehicles content types)
- Calibration certificates with expiry tracking
- Maintenance schedules and service history
- Vehicle pre-start and plant inspections as form templates
- Hire/internal rental charging to projects
- Telemetry hooks (hours, location) later

Interacts with:
- Certificates, competency & calibration gate: calibration validity
- Form & template designer: pre-start templates
- Traceability graph: components, materials & certificates: which instrument measured what
- Service & maintenance: maintenance work orders

AIP repo status and plans:
- Equipment and Vehicles content types exist as registers in AIP; calibration certificates built (TASKS §40)

## Other files in this folder (read only if your task needs them)

- [`architecture.md`](architecture.md) — Architecture & code structure
- [`data-model.md`](data-model.md) — Data model & schema
- [`features-access.md`](features-access.md) — Feature filler
- [`ui-layout.md`](ui-layout.md) — Page & layout designer
- [`features-market.md`](features-market.md) — Feature scout
- [`routes.md`](routes.md) — Page specs: routes, sections, actions, access
