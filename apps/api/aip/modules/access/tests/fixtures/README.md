Module packages for the ACCESS-01 startup tests (`create_app(modules_package=...)`). Each holds
one test-only module, `fixture`:

- `guarded`: declares `fixture.item.read` and `fixture.item.create`; `GET /api/v1/fixture/items`
  requires `fixture.item.read`.
- `shrunk`: the same module after `fixture.item.create` was removed from its manifest.
- `unguarded`: `GET /api/v1/fixture/unguarded` declares no access (startup must fail).
- `duplicate`: declares `fixture.item.read` twice (startup must fail).
