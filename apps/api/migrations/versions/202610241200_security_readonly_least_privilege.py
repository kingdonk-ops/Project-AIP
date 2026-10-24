"""security_readonly_least_privilege

SECURITY-13 (review 11 M3). ``current_setting('app.tenant_id', true)`` can be set with
``set_config`` by any role, so RLS is only advisory for a role that runs arbitrary SQL. The
reporting login ``aip_readonly`` held SELECT on the session, auth and PII tables (``user_session``,
``app_user``, ``auth_event``, ``audit_log``, ``security_audit_events``, ``breach_incidents``), so it
could read any tenant's raw PII by setting the id. This revision:

- Revokes those SELECT grants.
- Serves reporting through the ``reporting`` schema: one security-barrier view per table exposing
  only non-PII columns (no ip, user_agent, device, session id/kc_sid, email, display name, free-text
  description, or event payload/detail). The views are owned by ``aip_owner`` and are not
  ``security_invoker``, so the base-table SELECT runs with the owner's privileges while the owner's
  FORCE row-level security still filters by ``app.tenant_id`` — the reader sees only the tenant it
  set, and never a PII column. ``aip_readonly`` gets USAGE on the schema and SELECT on the views.

ADR 0012 is amended (RLS is advisory for roles that run arbitrary SQL); the ``00_cluster.sql``
comment that claimed "RLS limits what it reads" is corrected.

Revision ID: 202610241200
Revises: 202610191000
Create Date: 2026-10-24 12:00:00+00:00
"""

from alembic import op

revision: str = "202610241200"
down_revision: str | None = "202610191000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "REVOKE SELECT ON user_session, app_user, auth_event, audit_log, "
        "security_audit_events, breach_incidents FROM aip_readonly;"
    )

    op.execute("""
    CREATE SCHEMA reporting AUTHORIZATION aip_owner;
    REVOKE ALL ON SCHEMA reporting FROM PUBLIC;
    GRANT USAGE ON SCHEMA reporting TO aip_readonly;
    """)

    # One non-PII, security-barrier view per revoked table. Column lists are explicit so adding a
    # sensitive column to a base table never silently widens the reporting surface.
    op.execute("""
    CREATE VIEW reporting.user_session WITH (security_barrier = true) AS
      SELECT id, tenant_id, user_id, audience, aal, amr, authenticated_at,
             last_seen_at, idle_seconds, idle_expires_at, absolute_expires_at,
             revoked_at, revoke_reason, created_at, updated_at, deleted_at
      FROM public.user_session;

    CREATE VIEW reporting.app_user WITH (security_barrier = true) AS
      SELECT id, tenant_id, organisation_id, user_class, status, sso_managed,
             deactivated_at, last_login_at, mfa_enrolled_at, sync_version,
             created_at, updated_at, deleted_at
      FROM public.app_user;

    CREATE VIEW reporting.auth_event WITH (security_barrier = true) AS
      SELECT id, tenant_id, user_id, event_type, occurred_at
      FROM public.auth_event;

    CREATE VIEW reporting.audit_log WITH (security_barrier = true) AS
      SELECT id, tenant_id, stream, seq, project_id, asset_id, actor_id, on_behalf_of_id,
             auth_strength, source_module, record_table, record_id, event_type, summary_key,
             flags, source_event_id, supersedes_id, occurred_at, created_at
      FROM public.audit_log;

    CREATE VIEW reporting.security_audit_events WITH (security_barrier = true) AS
      SELECT id, tenant_id, seq, actor_id, event_type, auth_strength,
             source_event_id, occurred_at, created_at
      FROM public.security_audit_events;

    CREATE VIEW reporting.breach_incidents WITH (security_barrier = true) AS
      SELECT id, tenant_id, detected_at, data_categories, individuals_affected,
             serious_harm_likely, assessment_due_at, oaic_notified_at,
             individuals_notified_at, status, created_at, updated_at, deleted_at
      FROM public.breach_incidents;

    GRANT SELECT ON
      reporting.user_session, reporting.app_user, reporting.auth_event,
      reporting.audit_log, reporting.security_audit_events, reporting.breach_incidents
      TO aip_readonly;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
