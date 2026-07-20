"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Remember: DNA schema migrations are FORWARD-ONLY (docs/PORT-CONTRACT.md
§ "Schema migrations"). Recovery is backup/re-seed, not downgrade.

[dialect] The two dialects' schemas are disjoint. If this revision only
concerns one of them, branch on ``op.get_bind().dialect.name`` and make
the other a no-op -- do NOT create a second head.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    raise NotImplementedError("DNA schema migrations are forward-only")
