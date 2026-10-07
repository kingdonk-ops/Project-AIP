# Hardened base image for the sandboxed workers (STACK-05, ADR 0003): IFC, OCR, PDF signing and
# image processing images build FROM this. It is never a long-running service: a Procrastinate job
# runs one container per file (ECS RunTask; `docker run` in dev):
#   docker run --rm --network none --read-only --tmpfs /tmp --user 10001 --cap-drop ALL \
#     --security-opt no-new-privileges aip-sandbox:dev <command>
# Build from the repository root:
#   docker compose -f infra/docker-compose.yml --profile sandbox build sandbox

FROM python:3.12.15-slim-bookworm

# No package manager caches, no setuid/setgid binaries, a fixed non-root user.
RUN rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && find / -xdev -perm /6000 -type f -exec chmod a-s {} + \
    && groupadd --system --gid 10001 sandbox \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin sandbox \
    && mkdir -p /work \
    && chown 10001:10001 /work

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /work

USER 10001:10001

# Worker images replace this. The base image only proves it starts unprivileged and offline.
CMD ["python", "-I", "-c", "import os; print('aip sandbox base, uid', os.getuid())"]
