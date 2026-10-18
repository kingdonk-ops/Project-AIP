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


FROM nginxinc/nginx-unprivileged:1.30.5-alpine AS runtime

# CVE-2026-4775 (HIGH): the base image's libtiff 4.7.1-r0, fixed in 4.7.2-r0, and CVE-2026-77214 (HIGH):
# its libexpat 2.8.5-r0, fixed in 2.9.0-r0. The newest nginx tag still ships the old ones, so upgrade
# just those packages. Remove each once the base image has the fix.
USER root
RUN apk upgrade --no-cache tiff libexpat

# OPS-11: the Coolify demo build passes `--build-arg NGINX_CONF=infra/coolify/nginx.conf` (adds /auth
# to Keycloak); Coolify cannot bind-mount it from the repository.
ARG NGINX_CONF=apps/web/nginx.conf
COPY ${NGINX_CONF} /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html

# Compose and ECS run it as 10001 with a read-only root; nginx writes only to /tmp.
USER 10001:10001

EXPOSE 8080
