"""The Alembic recovery instruction must name a version that EXISTS (i-040).

When 0.21.0 rolled out, every API route 500'd and the migration code told
operators:

    Bring the database to version 10 using dna-sdk <= 0.20.0

Postgres ladder version 10 (i-039, ``DROP TABLE dna_edges``) merged AFTER the
v0.20.0 tag, and the ladder was retired before the next release shipped — so
NO published wheel has ever contained it. Every database built by the last
published SDK sits at version 9, one step short of the baseline, and the
message sent operators after a release that cannot close the gap.

These tests are deliberately DB-free: they guard the arithmetic that made the
message a lie, so no future ladder edit can reintroduce it.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from dna.adapters.sqlalchemy_.migrate import LEGACY_HEAD

def test_every_unpublished_ladder_step_has_a_bridge():
    """A gap no release can close MUST be closable by this code.

    This is the invariant the original bug violated. If someone adds a ladder
    version after the last published release without a bridge, the recovery
    message becomes impossible to follow again — so fail here instead.
    """
    from dna.adapters.sqlalchemy_.migrate import (
        _LEGACY_BRIDGES, LEGACY_LAST_PUBLISHED,
    )

    for dialect, head in LEGACY_HEAD.items():
        reachable = LEGACY_LAST_PUBLISHED[dialect]
        assert reachable <= head, (
            f"{dialect}: a published release cannot be ahead of the ladder head"
        )
        # Walk the bridges from the last publishable version to the head.
        at = reachable
        while at != head:
            bridge = _LEGACY_BRIDGES.get((dialect, at))
            assert bridge is not None, (
                f"{dialect}: ladder version {at + 1} exists in no published "
                f"release (the last one reaches {reachable}) and has no bridge "
                "in _LEGACY_BRIDGES. An operator at version "
                f"{at} would be told to install a release that cannot help them."
            )
            at = bridge.to_version


def test_recovery_message_only_names_a_release_that_can_help():
    """The behind-baseline message must not cite an unreachable version."""
    from dna.adapters.sqlalchemy_.migrate import (
        LEGACY_LAST_PUBLISHED, LEGACY_LAST_RELEASE, _stranded_message,
    )

    msg = _stranded_message("public.dna_schema_migrations", "postgresql", 5, 10)
    reachable = LEGACY_LAST_PUBLISHED["postgresql"]

    assert f"dna-sdk=={LEGACY_LAST_RELEASE}" in msg
    assert f"It reaches version {reachable}." in msg
    # The exact lie the bug shipped: telling the operator that the last
    # release can bring the database to the ladder head.
    assert f"version {LEGACY_HEAD['postgresql']} using dna-sdk" not in msg
    # And it must say the remaining step is handled here, not by the operator.
    assert "never published" in msg


def test_ahead_of_baseline_message_does_not_ask_for_a_downgrade():
    """A database ahead of the head is refused, and told something true."""
    from dna.adapters.sqlalchemy_.migrate import _ahead_message

    msg = _ahead_message("public.dna_schema_migrations", "postgresql", 12, 10)
    assert "AHEAD" in msg
    assert "no downgrade path" in msg
    # Must not tell the operator to "bring the database to version 10" with an
    # old SDK — the retired runner is forward-only and cannot go back.
    assert "using dna-sdk" not in msg
    assert "DELETE FROM public.dna_schema_migrations WHERE version > 10;" in msg


def test_sqlite_ladder_head_was_fully_published():
    """SQLite needs no bridge — v0.20.0 already reaches its head.

    Documents that the i-040 defect was Postgres-only, so the SQLite paths
    below are unaffected by the bridge.
    """
    from dna.adapters.sqlalchemy_.migrate import (
        _LEGACY_BRIDGES, LEGACY_LAST_PUBLISHED,
    )

    assert LEGACY_LAST_PUBLISHED["sqlite"] == LEGACY_HEAD["sqlite"] == 8
    assert not [k for k in _LEGACY_BRIDGES if k[0] == "sqlite"]

