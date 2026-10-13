# Keycloak for the Coolify demo (OPS-11): the stock image plus the realm imports, the AIP login
# theme and the password blocklist (built in because Coolify does not expose the repository to bind
# mounts). Build from the repository root:
#   docker build -f infra/coolify/images/keycloak.Dockerfile -t aip-keycloak-demo .
FROM quay.io/keycloak/keycloak:26.7.5

COPY infra/keycloak/realm-aip.json infra/keycloak/realm-mock-idp.json /opt/keycloak/data/import/
COPY infra/keycloak/themes/aip /opt/keycloak/themes/aip
COPY infra/keycloak/password-blocklist.txt /opt/keycloak/data/password-blacklists/password-blocklist.txt
