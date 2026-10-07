## Task

<!-- One task per PR, e.g. ARCH-01 -->
Task: `ID` (tracking/tasks/ID.md)

## What changed

-

## Definition of done (docs/blueprint/07-task-conventions.md)

- [ ] Tests written first; unit + integration (real Postgres) green
- [ ] Isolation / permission-matrix tests cover any new table or route
- [ ] New tables: `tenant_id`, uuid PK, timestamps, soft delete or append-only, `FORCE RLS`
- [ ] No hard-coded labels (terminology keys used)
- [ ] API client + permission catalogue regenerated, no drift
- [ ] Audit events emitted for state changes
- [ ] `tracking/BOARD.md` status updated and `tracking/PROGRESS.md` log line added
- [ ] ADR added for any decision not already covered
- [ ] No secrets, no real customer data

## Notes for reviewers
