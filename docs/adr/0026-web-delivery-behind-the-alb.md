# ADR 0026: Web apps served as containers behind the ALB, not from S3 + CloudFront

- **Status:** accepted (owner, 2026-10-13)
- **Date:** 2026-10-13
- **Affects:** ADR 0004 (the Delivery bullet), OPS-07, OPS-09, OPS-10, OPS-12, OPS-16, apps/web, apps/field, apps/portal

## Context

ADR 0004 serves each SPA from S3 + CloudFront, with `/api/*` path-routed to the ALB. The owner's production
service list (2026-10-13) puts the web apps on ECS Fargate behind the ALB instead. Coolify, the test target,
already runs `apps/web` as an nginx container ([`apps/web/nginx.conf`](../../apps/web/nginx.conf)), and more
sites will run on the same platform: the field PWA, the client portal, the operator console (ADR 0017) and
the marketing site.

## Decision

1. **Each web app ships as a container image** (nginx serving the built Vite bundle, non-root, read-only, as
   `apps/web/Dockerfile` does today) and runs as its own ECS Fargate service. The same image runs on Coolify.
2. **One shared ALB in `ap-southeast-2` routes by host name.** Each site has its own host rule and ACM
   certificate (SNI). For the staff app, `/api/*` goes to the `api` service and everything else to `web` on
   the same host, so the session cookie stays a first-party `__Host-` cookie.
3. **Other sites get their own host name, never a path on the app's host.** The portal and the operator
   console keep their own origins (ADR 0004, ADR 0017). The marketing site and any other public site are
   separate services (or a separate hosting tool) on their own host names, so their pages can never read or
   set the app's cookies.
4. **Security headers live in nginx.** `apps/web/security-headers.json` stays the single source; nginx sends
   the CSP, `frame-ancestors 'none'`, `Referrer-Policy`, `X-Content-Type-Options` and `Permissions-Policy`.
   HSTS is sent by nginx in AWS (TLS ends at the ALB) and by Coolify's proxy there.
5. **WAF attaches to the ALB.** CloudFront is not used now. It can be added later in front of the ALB, for
   edge caching or an edge WAF, with no change to the apps.

## Consequences

- Production serves exactly what is tested on Coolify, headers included, and the e2e suite checks it.
- One build output per app (an image digest), so build, sign, promote and roll back work the same way for
  the API and the web apps; there is no separate S3 bundle or CloudFront origin switch.
- Costs a few small always-on Fargate tasks per site (two per site for availability), and static files are
  served from Sydney rather than edge locations; the field PWA caches its files after the first visit.
- ADR 0004's Delivery bullet is superseded by this ADR. OPS-07 drops S3 + CloudFront for the SPAs and adds
  the web service and host rules; OPS-09 and OPS-10 deploy and roll back web image digests instead of bundles.
