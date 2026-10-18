"""SQLAlchemy Core table declarations for identity (ADR 0002).

``login_directory`` is the one global, pre-tenant table (ADR 0005): no ``tenant_id`` RLS, no soft
delete. Declared only so ``aip-db check-schema`` matches the migration; the application never
queries it directly (``aip_app`` has no privileges on it) and reads through
``identity_resolve_login`` / writes through ``identity_register_email`` instead.

IDENTITY-02 (revision ``202610091851_identity_users``): ``app_user`` and ``tenant_membership``
(tenant tables: FORCE RLS, soft delete) and the append-only ``auth_event`` (no ``updated_at`` or
``deleted_at``; ``aip_app`` may only INSERT and SELECT).

IDENTITY-03 (revision ``202610131500_identity_sessions``): ``user_session`` (tenant table, FORCE
RLS; revoked, never deleted) and ``tenant_auth_policy`` (one row per tenant, FORCE RLS).

IDENTITY-04 (revision ``202610181000_identity_invites``): ``user_invite`` and ``signoff_policy``
(tenant tables, FORCE RLS; revoked or soft-deleted, never deleted) and
``app_user.mfa_enrolled_at``.
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    LargeBinary,
    SmallInteger,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, JSONB

from aip.platform.db.metadata import metadata

login_directory = Table(
    "login_directory",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("key", CITEXT, nullable=False),
    Column("tenant_id", Uuid, nullable=False),
    Column("idp_alias", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

app_user = Table(
    "app_user",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("organisation_id", Uuid, nullable=True),
    Column("user_class", Text, nullable=False),
    Column("email", CITEXT, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("idp_alias", Text, nullable=True),
    Column("keycloak_user_id", Uuid, nullable=True),
    Column("external_id", Text, nullable=True),
    Column("sso_managed", Boolean, nullable=False, server_default=text("false")),
    Column("status", Text, nullable=False),
    Column("deactivated_at", DateTime(timezone=True), nullable=True),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("sync_version", Integer, nullable=False, server_default=text("1")),
    Column("mfa_enrolled_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

tenant_membership = Table(
    "tenant_membership",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("organisation_id", Uuid, nullable=True),
    Column("membership_type", Text, nullable=False),
    Column("valid_from", Date, nullable=False, server_default=text("current_date")),
    Column("valid_to", Date, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

auth_event = Table(
    "auth_event",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=True),
    Column("event_type", Text, nullable=False),
    Column("ip", INET, nullable=True),
    Column("user_agent", Text, nullable=True),
    Column("detail", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
)


user_session = Table(
    "user_session",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("sid_hash", LargeBinary, nullable=False),
    Column("audience", Text, nullable=False),
    Column("device_id", Uuid, nullable=True),
    Column("aal", SmallInteger, nullable=False),
    Column("amr", ARRAY(Text), nullable=False),
    Column("authenticated_at", DateTime(timezone=True), nullable=False),
    Column("kc_sid", Text, nullable=True),
    Column("ip", INET, nullable=True),
    Column("user_agent", Text, nullable=True),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("idle_seconds", Integer, nullable=False),
    Column("idle_expires_at", DateTime(timezone=True), nullable=False),
    Column("absolute_expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("revoke_reason", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

tenant_auth_policy = Table(
    "tenant_auth_policy",
    metadata,
    Column("tenant_id", Uuid, primary_key=True),
    Column("session_policy", JSONB, nullable=False),
    Column("sso_enforced", Boolean, nullable=False, server_default=text("false")),
    Column("step_up_max_age_min", Integer, nullable=False, server_default=text("10")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)


user_invite = Table(
    "user_invite",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("email", CITEXT, nullable=False),
    Column("user_class", Text, nullable=False),
    Column("organisation_id", Uuid, nullable=True),
    Column("invited_by", Uuid, nullable=True),
    Column("method", Text, nullable=False),
    Column("keycloak_user_id", Uuid, nullable=True),
    Column("status", Text, nullable=False),
    Column("last_error", Text, nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True), nullable=True),
    Column("accepted_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

signoff_policy = Table(
    "signoff_policy",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("action_code", Text, nullable=False),
    Column("min_aal", SmallInteger, nullable=False),
    Column("step_up_max_age_min", SmallInteger, nullable=False, server_default=text("10")),
    Column("updated_by", Uuid, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)
