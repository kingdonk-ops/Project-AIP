# Postgres for the Coolify demo (OPS-11): the stock pgvector image plus the cluster bootstrap.
# Coolify does not expose the repository to bind mounts (relative paths resolve under the app's own
# directory on the server), so every file the stack needs is built into an image instead.
# Build from the repository root:
#   docker build -f infra/coolify/images/postgres.Dockerfile -t aip-postgres-demo .
FROM pgvector/pgvector:0.8.7-pg16-bookworm

COPY db/bootstrap/00_cluster.sql /aip/bootstrap/00_cluster.sql
COPY infra/coolify/images/db-bootstrap.sh /aip/db-bootstrap.sh
