# SECURITY-12 — API edge hardening: body size cap, security headers, HSTS in the web nginx

<!-- hand-written: tools/split_blueprint.py will not overwrite this file -->

| Field | Value |
|---|---|
| Module | [`security`](../../docs/blueprint/modules/security/README.md) |
| Phase | P0 |
| Size | S |
| Depends on | OPS-04 |
| Status | tracked in [BOARD.md](../BOARD.md) |

## Read before starting (and nothing else unless blocked)

1. [`docs/blueprint/07-task-conventions.md`](../../docs/blueprint/07-task-conventions.md)
2. [`docs/blueprint/modules/security/README.md`](../../docs/blueprint/modules/security/README.md)
3. ADRs: 0026
4. [review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md), the finding named below

## Background

[review 11](../../docs/reviews/11-codebase-gap-review-2026-10-16.md) finding **M2**. No body-size middleware exists, and ADR 0026 routes `/api/*` straight to the API.
The API sends no `nosniff`, `frame-ancestors`/`X-Frame-Options` or HSTS. ADR 0026:28 says nginx sends HSTS, but
`apps/web/nginx.conf` has none.

## Spec

The API caps request bodies and sends security headers on the ALB→API path, and the web nginx sends the HSTS that ADR 0026 promises.

- **files**:
  - apps/api/aip/ (ASGI middleware)
  - apps/web/nginx.conf
  - tools/tests/test_nginx_headers.py
  - docs/adr/0026-web-delivery-behind-the-alb.md (if wording changes)
- **steps**:
  - 1. Add an ASGI middleware that rejects bodies over about 1 MiB with 413 (uploads use presigned POST, so the API never needs more), including chunked bodies.
  - 2. Add a security-headers middleware: `X-Content-Type-Options: nosniff`, `frame-ancestors 'none'`/`X-Frame-Options: DENY`, HSTS.
  - 3. Add HSTS to `apps/web/nginx.conf` and extend `test_nginx_headers.py`.
- **acceptance**:
  - A 2 MiB JSON body gets 413 without being buffered whole.
  - Every API response carries the headers.
  - The web nginx sends HSTS.
- **tests**:
  - **unit**:
    - body of 1 MiB + 1 byte, with and without Content-Length → 413
    - any route → nosniff, frame-ancestors and HSTS headers present
  - **integration**:
    - `test_nginx_headers.py` → HSTS present
