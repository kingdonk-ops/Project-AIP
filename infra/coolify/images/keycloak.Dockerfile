# Keycloak for the Coolify demo (OPS-11): the stock image plus the realm imports, the AIP login
# theme and the password blocklist (built in because Coolify does not expose the repository to bind
# mounts). Build from the repository root:
#   docker build -f infra/coolify/images/keycloak.Dockerfile -t aip-keycloak-demo .
#
# SECURITY-11: the image imports the deployed realms (infra/keycloak/deployed_realms.py), not the
# dev ones: no user with a password (the mock-IdP users come from Coolify secrets at deploy time,
# mock-idp-users.sh) and no default for a client secret. The entrypoint refuses to start when a
# client secret is unset or a public dev value.
FROM python:3.12.15-slim-bookworm AS realms

COPY infra/keycloak/realm-aip.json infra/keycloak/realm-mock-idp.json \
     infra/keycloak/deployed_realms.py /src/
RUN python3 /src/deployed_realms.py /out

FROM quay.io/keycloak/keycloak:26.7.5

COPY --from=realms /out/realm-aip.json /out/realm-mock-idp.json /opt/keycloak/data/import/
COPY infra/keycloak/themes/aip /opt/keycloak/themes/aip
COPY infra/keycloak/password-blocklist.txt /opt/keycloak/data/password-blacklists/password-blocklist.txt
COPY --chmod=0755 infra/coolify/images/keycloak-entrypoint.sh /opt/keycloak/aip/keycloak-entrypoint.sh
COPY --chmod=0755 infra/coolify/images/mock-idp-users.sh /opt/keycloak/aip/mock-idp-users.sh

ENTRYPOINT ["/opt/keycloak/aip/keycloak-entrypoint.sh"]
