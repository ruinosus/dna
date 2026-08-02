"""turn telemetry — what a turn DID, durable, so a screen can show it

Revision ID: 0004_turn_telemetry
Revises: 0003_api_version
Create Date: 2026-08-02

Nothing records what happened in a turn. Three symptoms, observed on screen in
dna-cloud on 2026-08-02, are the same hole seen from three angles:

* a tool that DIED mid-run still read ``em curso`` twenty minutes later, in the
  live chat AND on reopening the conversation. Failure rendered as pending;
* the input/output of every tool call VANISHES on reload — it lives only in the
  LangGraph checkpoint, and the AG-UI conversion back to the browser drops it;
* token counts were never written anywhere at all.

These tables are the durable record that closes all three.

**Why not the trace backend.** Traces go to whatever APM the operator chose —
Grafana, Azure Monitor, or none. A PRODUCT screen cannot depend on that choice,
and nobody grants a customer access to the operator's APM to see what a tool
answered in their own conversation. So the span processor writes HERE, and OTLP
exports in parallel for whoever wants it. ``trace_id`` is kept precisely so a
reader can jump to the APM when one exists.

**Why not ``dna_run``.** It looks like the right table and is not: it is a work
QUEUE (``status``, ``attempts``, ``locked_at``, ``locked_by``) for delegated
background runs. Reusing it would put two meanings on one ``status`` column.

**Two tables, because a turn has parts.** ``dna_turn`` is the turn; one
``dna_turn_step`` row per tool call. The screen reads the second — it is the
"input/output of each tool" that was asked for.

**⚠️ Text columns are TRUNCATED by the writer, not by the database.** A tool
returning 200 KB of JSON would otherwise cost 200 KB per turn, forever — the
same defect as base64 in the checkpoint wearing different clothes. The writer
caps each text field and marks the cut explicitly; a silent truncation would let
a reader believe the tool answered that.

**Postgres only**, like ``0002_quota_counters``. A SQLite deployment is a
single-process self-host; ``build_metadata`` mirrors this with ``if is_pg`` so
the autogenerate guard expects the tables on pg and their absence on SQLite.

Raw DDL rather than ``op.create_table`` follows 0001_baseline: a revision is a
frozen historical fact and must not re-render from the model.
"""
from __future__ import annotations

from alembic import op

revision = "0004_turn_telemetry"
down_revision = "0003_api_version"
branch_labels = None
depends_on = None


# ``{schema}`` is interpolated from the migration context (see env.py); the
# identifier is validated at SqlAlchemySource construction (trusted config).
PG_DDL_TURN = """
CREATE TABLE IF NOT EXISTS {schema}.dna_turn (
    turn_id       TEXT        NOT NULL PRIMARY KEY,
    trace_id      TEXT        NOT NULL DEFAULT '',
    thread_id     TEXT        NOT NULL DEFAULT '',
    workspace     TEXT        NOT NULL DEFAULT '',
    oid           TEXT        NOT NULL DEFAULT '',
    agent         TEXT        NOT NULL DEFAULT '',
    model         TEXT        NOT NULL DEFAULT '',
    input_text    TEXT,
    output_text   TEXT,
    input_tokens  INTEGER     NOT NULL DEFAULT 0,
    output_tokens INTEGER     NOT NULL DEFAULT 0,
    status        TEXT        NOT NULL DEFAULT 'ok',
    error         TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at      TIMESTAMPTZ,
    duration_ms   INTEGER     NOT NULL DEFAULT 0
)
"""

# The read path is always "this thread, newest first" — the console opens ONE
# conversation and asks what happened in it. That is an equality predicate plus
# an ordering, which is exactly what this index serves.
PG_DDL_TURN_IDX = """
CREATE INDEX IF NOT EXISTS dna_turn_thread_started_idx
    ON {schema}.dna_turn (workspace, thread_id, started_at DESC)
"""

# ON DELETE CASCADE: the steps have no meaning without their turn, and the
# retention story is "goes away with the thread". Leaving orphans would make the
# table grow in a way nobody is watching — the failure mode this repo already
# paid for once, in the container registry.
PG_DDL_STEP = """
CREATE TABLE IF NOT EXISTS {schema}.dna_turn_step (
    turn_id     TEXT        NOT NULL
        REFERENCES {schema}.dna_turn (turn_id) ON DELETE CASCADE,
    step_index  INTEGER     NOT NULL,
    name        TEXT        NOT NULL,
    input       TEXT,
    output      TEXT,
    status      TEXT        NOT NULL DEFAULT 'ok',
    error       TEXT,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (turn_id, step_index)
)
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # [dialect] control-plane table is pg-only (see the docstring).
    schema = op.get_context().version_table_schema or "public"
    op.execute(PG_DDL_TURN.format(schema=schema))
    op.execute(PG_DDL_TURN_IDX.format(schema=schema))
    op.execute(PG_DDL_STEP.format(schema=schema))


def downgrade() -> None:
    # Forward-only, as the baseline is (docs/PORT-CONTRACT.md § "Schema
    # migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
