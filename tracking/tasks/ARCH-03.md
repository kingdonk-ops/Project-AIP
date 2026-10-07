# ARCH-03 — Import-boundary lint and manifest CI check

| Field | Value |
|---|---|
| Module | [`arch`](../../docs/blueprint/modules/arch/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | ARCH-01 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/arch/README.md`](../../docs/blueprint/modules/arch/README.md)
3. Any ADR in [`docs/adr/`](../../docs/adr/) that names this task or module
4. Only if the step needs it: `architecture.md` / `data-model.md` in the module folder

## Spec

Make module isolation a CI gate.

- **depends on**:
  - ARCH-01
- **files**:
  - .dependency-cruiser.cjs
  - tools/ci/check-manifests.ts
  - .github/workflows/ci.yml
- **steps**:
  - 1. Configure dependency-cruiser rules: a module may import another module only via modules/<x>/api.ts, and nothing in platform/ may import modules/*.
  - 2. Add a rule that apps/web may import only packages/* and generated client code, never apps/api.
  - 3. check-manifests verifies that every permission, event and term key used in a module's code appears in its manifest.
  - 4. Wire both checks into the CI workflow and mark them as required.
  - 5. Add fixture modules that violate each rule, used only by the lint tests.
- **acceptance**:
  - Importing modules/b/service.ts from module a fails lint with a rule name.
  - Importing modules/b/api.ts passes.
  - A permission string used in code but absent from the manifest fails check-manifests.
- **tests**:
  - **e2e**:
    - Open a throwaway PR that adds a deep import. Expected: the CI lint job fails and the merge is blocked.
  - **integration**:
    - Run depcruise on the violating fixture. Expected: exit code 1 and exactly 1 violation of the 'no-deep-module-import' rule.
    - Run depcruise on the real repo. Expected: exit code 0.
  - **unit**:
    - check-manifests on a fixture with an undeclared event 'x.y.z' returns one error naming that event.
    - check-manifests on a clean fixture returns an empty list.
