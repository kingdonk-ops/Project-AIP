#!/bin/bash
# One-shot, every deploy (SECURITY-11 Part A, review 11 H1): create the demo's mock-IdP users
# alice@kaefer.test and bob@acme.test if they are missing, and set their passwords from the Coolify
# secrets MOCK_IDP_ALICE_PASSWORD and MOCK_IDP_BOB_PASSWORD. The deployed mock-idp realm has no users
# (infra/keycloak/deployed_realms.py), so no password of a demo user is in the repository or the
# image; setting the password on every deploy also replaces the committed dev passwords on a demo
# whose realm was imported before this change. Uses the bootstrap admin over the internal network.
set -euo pipefail

: "${KEYCLOAK_SERVER:=http://keycloak:8080/auth}"
: "${KEYCLOAK_ADMIN:=admin}"
: "${KEYCLOAK_ADMIN_PASSWORD:?}"
: "${MOCK_IDP_ALICE_PASSWORD:?}"
: "${MOCK_IDP_BOB_PASSWORD:?}"

for value in "$MOCK_IDP_ALICE_PASSWORD" "$MOCK_IDP_BOB_PASSWORD"; do
  case "$value" in
    alice_dev_only_password | bob_dev_only_password)
      echo "mock-idp-users: a password is the public dev value; refusing" >&2
      exit 1
      ;;
  esac
done

kcadm() { /opt/keycloak/bin/kcadm.sh "$@" --config /tmp/kcadm.config; }

# The admin password goes through the environment, not the command line.
KC_CLI_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" kcadm config credentials \
  --server "$KEYCLOAK_SERVER" --realm master --user "$KEYCLOAK_ADMIN"

ensure_user() {
  local email="$1" first="$2" last="$3" password="$4" id
  id="$(kcadm get users -r mock-idp -q "username=$email" -q exact=true --fields id \
    --format csv --noquotes)"
  if [ -z "$id" ]; then
    kcadm create users -r mock-idp -s "username=$email" -s "email=$email" -s emailVerified=true \
      -s "firstName=$first" -s "lastName=$last" -s enabled=true
    echo "mock-idp-users: created $email"
  fi
  kcadm set-password -r mock-idp --username "$email" --new-password "$password"
  echo "mock-idp-users: password set for $email"
}

ensure_user alice@kaefer.test Alice Kaefer "$MOCK_IDP_ALICE_PASSWORD"
ensure_user bob@acme.test Bob Acme "$MOCK_IDP_BOB_PASSWORD"
rm -f /tmp/kcadm.config
