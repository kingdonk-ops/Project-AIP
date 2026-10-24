#!/bin/bash
# Entrypoint of the deployed Keycloak image (SECURITY-11 Part D, review 11 M4): refuse to start, and
# so to import a realm, when a client secret is unset, empty or a public dev value. The deployed
# realms have no defaults for these (infra/keycloak/deployed_realms.py), and Keycloak would import an
# unset placeholder as the literal text "${NAME}", which is just as public.
set -euo pipefail

declare -A dev_values=(
  [AIP_API_CLIENT_SECRET]=aip_api_dev_only_secret
  [AIP_ADMIN_CLIENT_SECRET]=aip_admin_dev_only_secret
  [MOCK_IDP_CLIENT_SECRET]=mock_idp_dev_only_secret
)

failed=0
for name in "${!dev_values[@]}"; do
  value="${!name:-}"
  if [ -z "$value" ]; then
    echo "keycloak-entrypoint: $name is not set; refusing to start" >&2
    failed=1
  elif [ "$value" = "${dev_values[$name]}" ]; then
    echo "keycloak-entrypoint: $name is the public dev value; refusing to start" >&2
    failed=1
  fi
done
if [ "$failed" -ne 0 ]; then
  exit 1
fi

exec /opt/keycloak/bin/kc.sh "$@"
