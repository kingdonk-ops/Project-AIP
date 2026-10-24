# Postgres for the Coolify demo (OPS-11): the stock pgvector image plus the cluster bootstrap.
# Coolify does not expose the repository to bind mounts (relative paths resolve under the app's own
# directory on the server), so every file the stack needs is built into an image instead.
# Build from the repository root:
#   docker build -f infra/coolify/images/postgres.Dockerfile -t aip-postgres-demo .
FROM pgvector/pgvector:0.8.7-pg16-bookworm

# SECURITY-11 Part C: the deploy Trivy-scans this image. Take the Debian security fixes the base
# image lags behind on, and drop gosu (an old Go build the entrypoint only uses to step down from
# root; every demo service runs this image as `user: postgres`, so it is never needed).
RUN apt-get update \
    && apt-get -y upgrade \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /usr/local/bin/gosu

COPY db/bootstrap/00_cluster.sql /aip/bootstrap/00_cluster.sql
COPY infra/coolify/images/db-bootstrap.sh /aip/db-bootstrap.sh
