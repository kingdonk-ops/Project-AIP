# ADR 0020: Editable roles, project-scoped overrides and role-change guardrails

- **Status:** accepted (owner specification, 2026-10-10); points 2, 3 and 6 contain adjustments to that specification that the owner has not yet confirmed
- **Date:** 2026-10-10
- **Affects:** access (ACCESS-01, ACCESS-02, ACCESS-05), identity (IDENTITY-03), audit, offline; supersedes the "system roles are immutable" rule in ACCESS-02

## Context

Roles must fit each customer's organisation, contractors and auditors, so built-in roles are starting templates, not
fixed definitions. The owner specified who may change roles, how custom roles are made, and the guardrails. Reviewing
that specification against earlier decisions found three points that need adjusting (below).

## Decision

1. **Built-in roles are editable templates.** Company admins can change the permissions of any built-in role, and every
   built-in role has a "Reset to default" action that restores its shipped definition without touching custom roles.
   Built-in roles cannot be deleted. A permission added to the catalogue later is never granted automatically to a
   role an admin has customised (fail closed).
2. **Authority.** The company owner and company admins create, clone, edit and delete custom roles, edit the built-in
   roles and manage assignments for the whole tenant. A **project owner or project admin** can override permissions only
   inside their project (for example, grant punchlist sign-off for one turnaround) and **cannot edit tenant-wide role
   definitions**; the specification said project owners could edit the built-in roles, which would change every
   project. A project override can never grant more than the grantor holds, and can never grant role management.
3. **Platform operators have no standing right to change tenant roles** (ADR 0017). They set tenant defaults at
   provisioning, and may change a tenant's roles or run diagnostic audits only inside a customer-approved, time-boxed
   support-access grant (TENANCY-06), fully audited. The specification described this as a standing Super Admin power.
4. **Custom roles** are created by cloning an existing role or from a blank role, and can be assigned tenant-wide or
   limited to a project, an organisation (business unit) or an asset subtree.
5. **Permissions are atomic flags** declared by modules in their manifests and grouped by domain (inspections, issues
   and punchlists, assets and drawings, reports and analytics, administration). Examples: create an inspection draft,
   submit offline data, sign and seal, re-open; raise a defect, assign responsibility, verify and close; view drawings,
   pin a markup, edit asset metadata; export raw data, generate the branded PDF, view in-app dashboards; invite users,
   manage templates, change role definitions. The "embedded Power BI" flag in the specification becomes "view in-app
   dashboards" and "use the reporting feed" (ADR 0008 C).
6. **Guardrails.**
   - **No lockout:** the last user holding role management at tenant scope cannot lose it, be deleted or be deactivated;
     the check runs in the same transaction under a per-tenant lock so two admins cannot remove each other at once.
   - **Immutable audit:** every role edit, creation, deletion, reset and project override writes an append-only audit
     entry with timestamp, acting user, target role, the permission set before and the set after.
   - **Immediate effect:** sessions never carry permission lists. Each request is checked against current grants, with
     any cache keyed by a per-tenant access version that every role or assignment change increments, so changes apply on
     the next request without logging out.
   - **Offline grace** is limited as set out in the ADR 0010 addendum (permission edits only, within the maximum
     offline period, never for deactivation or revoked sessions).

## Consequences

ACCESS-01 adds the access-version counter and the flag naming rules; ACCESS-02 gets the amended requirement,
project overrides, reset, the lockout rule and the audit fields; ACCESS-05 shows the project override and reset
actions; IDENTITY-03 must not store permissions in the session; the offline module records the synced access version;
TENANCY-06 defines what an operator may do inside a support-access grant.
