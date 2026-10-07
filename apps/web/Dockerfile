# Web app image (STACK-05): the Vite build served by unprivileged nginx, /api proxied to the API.
# Build from the repository root:
#   docker build -f apps/web/Dockerfile -t aip-web .

FROM node:22.23.3-bookworm-slim AS build

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
    CI=true

# pnpm comes from the root package.json `packageManager` field.
RUN corepack enable pnpm

WORKDIR /repo

COPY . .
RUN pnpm install --frozen-lockfile --filter "@aip/web..." \
    && pnpm --filter @aip/web build


FROM nginxinc/nginx-unprivileged:1.30.5-alpine AS runtime

COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html

# Compose and ECS run it as 10001 with a read-only root; nginx writes only to /tmp.
USER 10001:10001

EXPOSE 8080
