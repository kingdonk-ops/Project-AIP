# ADR 0034: Invites and step-up: how the IDENTITY-04 spec meets the code that exists

- **Status:** accepted
- **Date:** 2026-10-18
- **Affects:** identity, ops, approvals; IDENTITY-04, OPS-17, APPROVALS-02, ACCESS-05, PROJECTS-04

## Context

IDENTITY-04 (invites, MFA enforcement, step-up and the ADR 0010 sign-off decision) was written
before several things it touches existed or were tested against a real Keycloak. Building it found
six places where the spec and the platform disagree.

## Decision

1. **The invite job writes identity rows as `aip_jobs` with narrow grants.** Job handlers run as
   `aip_jobs` (ADR 0016), which has no grants on tenant tables, and OPS-17 has not chosen how
   handlers write. Revision `202610181000` grants only what `identity.send_invite` needs: SELECT
   and UPDATE on `user_invite`, SELECT and a column UPDATE (`keycloak_user_id`, `updated_at`,
   `sync_version`) on `app_user`, and INSERT on `auth_event`. RLS still binds the handler to the
   job's tenant. When OPS-17 lands, it either keeps these (option b) or revokes them once handlers
   run on the `aip_app` engine (option a).
2. **The invite email returns through the client's base URL, not `redirect_uri`.** Keycloak
   accepts an `execute-actions-email` `redirect_uri` only if it is one of the client's redirect
   URIs, and `aip-api` registers only the API callback (review 11 L6). The `aip-api` client's
   `baseUrl` is `${APP_ORIGIN}/login?invited=1`, which Keycloak uses for "back to the application"
   when no `redirect_uri` is passed.
3. **`aip-admin` gets its roles into its token.** The client has `fullScopeAllowed: false` and no
   scope mappings, so its tokens carried no `realm-management` roles and every admin call was 403
   (IDENTITY-03's Keycloak session revocation included). The realm now maps exactly
   `manage-users`, `view-users` and `query-users` to it (`clientScopeMappings`) and gives it the
   `roles` client scope.
4. **The user profile declares `aip_user_id` and `upstream_amr`** (admin view and edit only).
   Keycloak 26 drops undeclared attributes on admin writes. The IdP "Attribute Importer" (sync
   FORCE) fills `upstream_amr` from the customer IdP's `amr`; `aip-api` emits it as the
   `upstream_amr` ID-token claim. Against a real Keycloak a brokered sign-in has `acr=aal1` and
   an empty `amr`, so only `upstream_amr` can lift it to aal 2.
5. **`STEP_UP_REQUIRED` is 401 everywhere**, in the ADR 0015 body
   (`{"detail": {"code", "message", "stepUpUrl"}}`), including lowering a sign-off minimum (the
   spec's acceptance said 403 there). One status lets the web helper handle every critical action.
6. **`signoff_policy` uses the standard tenant template** (uuid key, soft delete) with
   `(tenant_id, action_code)` unique among live rows, not a composite primary key (AGENTS.md hard
   rules). `check_signoff_assurance(conn, ctx, action_code)` takes the caller's `with_tenant`
   connection like every other identity function. The ADR 0010 addendum's project settings
   (`holdpoint_client_pin_only`, `client_signing_photo`) belong to projects (PROJECTS-04); the
   caller passes their values in `SignoffContext`.

## Consequences

- OPS-17 must account for the `aip_jobs` grants above.
- APPROVALS-02 builds a `SignoffContext` (session facts, whether an aal2 method is available, the
  project setting, offline) and calls `check_signoff_assurance` inside its transaction.
- A deployed realm overlay (SECURITY-14) keeps `baseUrl`, the scope mapping and the user profile.
- The Playwright journeys (invite e2e, step-up with the fake clock) are carried forward to
  IDENTITY-08.
