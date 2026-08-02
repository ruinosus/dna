"""approval trail — who authorised what, and when

Revision ID: 0005_approval_trail
Revises: 0004_turn_telemetry
Create Date: 2026-08-02

Nothing recorded HITL decisions. The middleware interrupts, the console renders
the card, the user clicks, the graph resumes with ``{decisions: [...]}`` — and
the decision DISAPPEARS. The checkpoint records that the tool ran, never that
somebody consented, nor who.

**⚠️ Why not ``dna_turn_step``.** That table is telemetry, and its guarantees
are the OPPOSITE of an audit trail's: it drops under pressure and truncates
text, both correct there and both fatal here. Reusing it would produce a trail
with silent holes — and a trail with holes is WORSE than none, because it looks
like coverage.

**Append-only.** A decision is not edited, it is superseded. There is no
``updated_at`` and no unique constraint that would tempt an upsert; a second
decision on the same request is a second row, and the reader sees both.

**``arguments`` is NOT truncated.** It is what was authorised. A cut would make
the trail unable to answer the one question it exists for. Large arguments make
large rows — that is the price of integrity, deliberately paid.

**Postgres only**, like 0002 and 0004: a single-process self-host does not have
the multi-user question this answers, and ``build_metadata`` mirrors it.

Raw DDL rather than ``op.create_table`` follows 0001_baseline: a revision is a
frozen historical fact and must not re-render from the model.
"""
from __future__ import annotations

from alembic import op

revision = "0005_approval_trail"
down_revision = "0004_turn_telemetry"
branch_labels = None
depends_on = None


PG_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.dna_approval (
    approval_id  TEXT        NOT NULL PRIMARY KEY,
    turn_id      TEXT        NOT NULL DEFAULT '',
    thread_id    TEXT        NOT NULL DEFAULT '',
    workspace    TEXT        NOT NULL DEFAULT '',
    oid          TEXT        NOT NULL DEFAULT '',
    actor_email  TEXT        NOT NULL DEFAULT '',
    tool         TEXT        NOT NULL,
    arguments    TEXT        NOT NULL DEFAULT '',
    decision     TEXT        NOT NULL DEFAULT '',
    edited_args  TEXT        NOT NULL DEFAULT '',
    reason       TEXT        NOT NULL DEFAULT '',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at   TIMESTAMPTZ
)
"""

# As duas leituras que a tela faz: "o que aconteceu nesta conversa" (contexto) e
# "o que foi autorizado neste workspace, no periodo" (varredura). Sao consultas
# diferentes o bastante para justificar dois indices — a segunda e a de um
# auditor de verdade, e sem ela ele varreria a tabela inteira.
PG_DDL_IDX_THREAD = """
CREATE INDEX IF NOT EXISTS dna_approval_thread_idx
    ON {schema}.dna_approval (thread_id, requested_at DESC)
"""

PG_DDL_IDX_AUDIT = """
CREATE INDEX IF NOT EXISTS dna_approval_workspace_idx
    ON {schema}.dna_approval (workspace, requested_at DESC)
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # [dialect] control-plane table is pg-only (see the docstring).
    schema = op.get_context().version_table_schema or "public"
    op.execute(PG_DDL.format(schema=schema))
    op.execute(PG_DDL_IDX_THREAD.format(schema=schema))
    op.execute(PG_DDL_IDX_AUDIT.format(schema=schema))


def downgrade() -> None:
    # Forward-only, as the baseline is (docs/PORT-CONTRACT.md § "Schema
    # migrations"): recovery is backup/re-seed, not downgrade.
    raise NotImplementedError("DNA schema migrations are forward-only")
