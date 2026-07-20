"""quota counters — the durable MCP metering counter (DNA Cloud billing)

Revision ID: 0002_quota_counters
Revises: 0001_baseline
Create Date: 2026-07-20

The DNA Cloud overage job bills Pro tenants on calls-per-day, but until
this revision there was no durable place for that count to live: the MCP
quota meter's only ``QuotaStore`` was ``InProcQuotaStore``, two dicts in
the server process. A restart reset the day's usage to zero, and every
replica kept its OWN dicts, so the effective cap was N x calls_per_day.
The counter this table backs (``dna_cli._mcp_quota.PostgresQuotaStore``)
is the fix.

**Shape.** One row per ``(day, tenant, tier)``, which is the primary key.
Tier is part of the key because the meter's key has always been
``tenant::tier`` -- a tenant that changes plan mid-day keeps both buckets
rather than silently merging them, and the billing rollup just sums
across tiers for the tenant+day.

``calls`` is BIGINT, advanced only by ``INSERT ... ON CONFLICT (day,
tenant, tier) DO UPDATE SET calls = dna_quota_counters.calls + 1``. That
statement is atomic under concurrency -- the conflicting writer blocks on
the row lock and re-reads the committed value -- which is the entire
point. A read-modify-write from the application would lose increments
between replicas, which is exactly the bug being closed.

**Postgres only.** ``upgrade`` is a no-op on SQLite, like the Phase 15.1
eventbus tables. A SQLite deployment is a single-process self-host: it has
neither the replica-fan-out nor the metered-billing problem, and keeps the
in-process counter. ``build_metadata`` mirrors this (``if is_pg``), so the
autogenerate guard compares the table on pg and expects its absence on
SQLite.

Raw DDL rather than ``op.create_table`` follows 0001_baseline: a revision
is a frozen historical fact and must not re-render from the model. The
model is compared against the database separately, by
``tests/test_schema_autogenerate_guard.py``.
"""
from __future__ import annotations

from alembic import op

revision = "0002_quota_counters"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


# ``{schema}`` is interpolated from the migration context (see env.py); the
# identifier is validated at SqlAlchemySource construction (trusted config).
PG_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.dna_quota_counters (
    day    DATE   NOT NULL,
    tenant TEXT   NOT NULL,
    tier   TEXT   NOT NULL,
    calls  BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (day, tenant, tier)
)
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # [dialect] control-plane table is pg-only (see the docstring).
    schema = op.get_context().version_table_schema or "public"
    op.execute(PG_DDL.format(schema=schema))


def downgrade() -> None:
    # Forward-only, as the baseline is (docs/PORT-CONTRACT.md § "Schema
    # migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
