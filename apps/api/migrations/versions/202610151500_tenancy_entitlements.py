"""tenancy_entitlements

ENT-01 (ADR 0008, 0017, 0023): the three entitlement tables, each from
``db/templates/tenant_table.sql.tpl`` (uuid PK, tenant_id, timestamps, soft delete, FORCE RLS with
the fail-closed NULLIF policy). Deletes are soft, so ``aip_app`` loses the template's DELETE grant.

- ``tenant_subscription``: one live row per tenant (plan code and version, term, dates, contracted
  seats and storage, add-ons, the opaque ``contract_ref``, status). ``entitlement_version`` goes up
  in the same transaction as every plan, add-on or override change, so caches keyed by it apply a
  change at once (ADR 0023 point 3). No price, invoice or payment column, ever.
- ``tenant_entitlement_override``: an operator's per-tenant value for one ``feature.*`` or
  ``limit.*`` key, with a mandatory reason and an optional expiry.
- ``tenant_usage``: one row per tenant and month (``period`` is the first day), upserted by the
  usage snapshot. ``db_bytes_est``, ``db_estimate_method`` and ``db_estimated_at`` hold the
  database-size estimate (ADR 0008 adjustment A; taken weekly and at month end);
  ``over_limit`` records WARN and OVERAGE limits that were exceeded.

Revision ID: 202610151500
Revises: 202610151200
Create Date: 2026-10-15 15:00:00+00:00
"""

from alembic import op

from aip.platform.db.templates import render_template

revision: str = "202610151500"
down_revision: str | None = "202610151200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        render_template(
            "tenant_table",
            table="tenant_subscription",
            columns=(
                "plan_code text NOT NULL, plan_version integer NOT NULL, term text NOT NULL, "
                "starts_on date NOT NULL, ends_on date NULL, renewal_date date NULL, "
                "seat_limits jsonb NOT NULL, storage_gb integer NULL, "
                "add_ons text[] NOT NULL, contract_ref text NULL, "
                "status text NOT NULL, entitlement_version bigint NOT NULL DEFAULT 1, "
                "updated_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE tenant_subscription
      ALTER COLUMN seat_limits SET DEFAULT '{}'::jsonb,
      ALTER COLUMN add_ons SET DEFAULT '{}'::text[];
    ALTER TABLE tenant_subscription
      ADD CONSTRAINT uq_tenant_subscription_tenant_id UNIQUE (tenant_id),
      ADD CONSTRAINT fk_tenant_subscription_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_tenant_subscription_plan_code CHECK (plan_code <> ''),
      ADD CONSTRAINT ck_tenant_subscription_plan_version CHECK (plan_version >= 1),
      ADD CONSTRAINT ck_tenant_subscription_term
        CHECK (term IN ('annual', 'multi_year', 'trial', 'sandbox')),
      ADD CONSTRAINT ck_tenant_subscription_status
        CHECK (status IN ('active', 'expired', 'suspended')),
      ADD CONSTRAINT ck_tenant_subscription_dates
        CHECK (ends_on IS NULL OR ends_on >= starts_on),
      ADD CONSTRAINT ck_tenant_subscription_seat_limits
        CHECK (jsonb_typeof(seat_limits) = 'object'),
      ADD CONSTRAINT ck_tenant_subscription_storage_gb CHECK (storage_gb >= 0),
      -- ADR 0017: a production term always carries the contract reference.
      ADD CONSTRAINT ck_tenant_subscription_contract_ref
        CHECK (term NOT IN ('annual', 'multi_year') OR coalesce(btrim(contract_ref), '') <> ''),
      ADD CONSTRAINT ck_tenant_subscription_entitlement_version CHECK (entitlement_version >= 1);

    REVOKE DELETE ON tenant_subscription FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="tenant_entitlement_override",
            columns=(
                "key text NOT NULL, value jsonb NULL, reason text NOT NULL, "
                "expires_at timestamptz NULL, created_by uuid NULL"
            ),
        )
    )
    op.execute("""
    ALTER TABLE tenant_entitlement_override
      ADD CONSTRAINT fk_tenant_entitlement_override_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_tenant_entitlement_override_key
        CHECK (key ~ '^(feature|limit)\\.[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$'),
      ADD CONSTRAINT ck_tenant_entitlement_override_reason CHECK (btrim(reason) <> '');

    CREATE INDEX ix_tenant_entitlement_override_tenant_id_key
      ON tenant_entitlement_override (tenant_id, key) WHERE deleted_at IS NULL;

    REVOKE DELETE ON tenant_entitlement_override FROM aip_app;
    """)

    op.execute(
        render_template(
            "tenant_table",
            table="tenant_usage",
            columns=(
                "period date NOT NULL, active_users jsonb NOT NULL, "
                "storage_bytes bigint NOT NULL DEFAULT 0, jobs_count bigint NOT NULL DEFAULT 0, "
                "ai_spend_cents bigint NOT NULL DEFAULT 0, db_bytes_est bigint NULL, "
                "db_estimate_method text NULL, db_estimated_at timestamptz NULL, "
                "over_limit jsonb NOT NULL, "
                "captured_at timestamptz NOT NULL DEFAULT now()"
            ),
        )
    )
    op.execute("""
    ALTER TABLE tenant_usage
      ALTER COLUMN active_users SET DEFAULT '{}'::jsonb,
      ALTER COLUMN over_limit SET DEFAULT '{}'::jsonb;
    ALTER TABLE tenant_usage
      ADD CONSTRAINT uq_tenant_usage_tenant_id_period UNIQUE (tenant_id, period),
      ADD CONSTRAINT fk_tenant_usage_tenant_id_tenants
        FOREIGN KEY (tenant_id) REFERENCES tenants (id),
      ADD CONSTRAINT ck_tenant_usage_period CHECK (extract(day FROM period) = 1),
      ADD CONSTRAINT ck_tenant_usage_active_users CHECK (jsonb_typeof(active_users) = 'object'),
      ADD CONSTRAINT ck_tenant_usage_over_limit CHECK (jsonb_typeof(over_limit) = 'object'),
      ADD CONSTRAINT ck_tenant_usage_counts CHECK (
        storage_bytes >= 0 AND jobs_count >= 0 AND ai_spend_cents >= 0
        AND (db_bytes_est IS NULL OR db_bytes_est >= 0));

    REVOKE DELETE ON tenant_usage FROM aip_app;
    """)


def downgrade() -> None:
    raise NotImplementedError("forward-only")
