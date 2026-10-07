Fixtures for the ARCH-03 boundary checks. Each one breaks (or keeps) exactly one rule. They are used
only by `apps/api/tests/arch/` and are outside the real contracts (whose root package is `aip`) and
outside pyright.

- `deep_import/`: `deep_app.modules.a` imports `deep_app.modules.b.service` (breaks `no-deep-module-import`);
  `a/allowed.py` shows the imports that stay allowed.
- `platform_imports_module/`: `plat_app.platform` imports `plat_app.modules` (breaks `platform-never-imports-modules`).
- `undeclared_event/`: a module that emits `x.y.z` without declaring it in `manifest.toml`.
- `clean/`: a module whose permissions, events and term keys all appear in its manifest.
