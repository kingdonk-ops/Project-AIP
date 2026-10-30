# Web app image (STACK-05): the Vite build served by unprivileged nginx, /api proxied to the API.
# Build from the repository root:
#   docker build -f apps/web/Dockerfile -t aip-web .

FROM node:22.23.3-bookworm-slim AS build

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    CI=true

# pnpm comes from the root package.json `packageManager` field.
RUN corepack enable pnpm

WORKDIR /repo

# OPS-11: `--build-arg VITE_AIP_DEMO=1` builds the Coolify demo (the synthetic-data banner).
ARG VITE_AIP_DEMO=""
ENV VITE_AIP_DEMO=${VITE_AIP_DEMO}

COPY . .
RUN pnpm install --frozen-lockfile --filter "@aip/web..." \
    && pnpm --filter "@aip/web..." build


FROM nginxinc/nginx-unprivileged:1.31.7-alpine AS runtime

# The base tag carries the vendor's nginx (apk upgrade cannot move nginx within a tag), so bump the
# tag itself for nginx CVEs: 1.30.6 fixes CVE-2026-15176, CVE-2026-93479, CVE-2026-97205. On top of
# that, apply all available Alpine security updates (the same way the Postgres demo image applies
# Debian updates) to clear base OS-package findings such as brotli-libs CVE-2026-111497 and libx11
# CVE-2026-88806 without re-listing each package as new CVEs land.
USER root
RUN apk upgrade --no-cache

# OPS-11: the Coolify demo build passes `--build-arg NGINX_CONF=infra/coolify/nginx.conf` (adds /auth
# to Keycloak); Coolify cannot bind-mount it from the repository.
ARG NGINX_CONF=apps/web/nginx.conf
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html

# Compose and ECS run it as 10001 with a read-only root; nginx writes only to /tmp.
USER 10001:10001

EXPOSE 8080
