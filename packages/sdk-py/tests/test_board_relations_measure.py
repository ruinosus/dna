"""The migration's number, measured against the repo's OWN board.

``f-modelagem-das-relacoes`` says migrating our own data is part of the work,
and that "no users" is not "no data". This module reads the repo's SDLC scope —
hundreds of git-tracked instances — and resolves every declared relation
against the values actually stored there.

The number it exists to produce is the one nobody would believe without it:
**zero instances changed.** A relation's NAME is the spec field holding its
value, so moving the declaration out of the JSON Schema and into
``spec.relations`` left every stored value exactly where it was. This module is
what turns that from an argument into a count — and, more usefully, it is what
would catch the day somebody "tidies" a relation's name away from its field and
silently orphans several hundred values.

Deliberately a MEASUREMENT of the mapping and not an audit of the board's
health: dangling references exist on a live board (a Story naming a Feature
that was later renamed), and failing here for that would make this guard about
tidiness rather than about the migration.
"""
from __future__ import annotations

import pathlib

import pytest

from dna.kernel.kinds.relations import relation_values, relations_of

_BOARD = pathlib.Path(__file__).resolve().parents[3] / ".dna"

#: Named pairs that MUST resolve to values, so the count below cannot go
#: vacuously green. Each is a relation whose declaration moved in this change:
#: both halves of the Feature⇄Story pair, one array, one composite pointer.
_EXPECTED_PAIRS = ("Story.feature", "Feature.stories", "Story.spec_refs",
                   "TestGuide.verifies")

#: A floor, not the measurement. On 06/08/2026 this board answered 642 values
#: across 12 pairs; asserting the exact number would make every board edit a
#: test failure, and asserting nothing would let the mapping break in silence.
_MIN_VALUES = 300


pytestmark = pytest.mark.skipif(
    not _BOARD.is_dir(), reason="the repo's own .dna board is not present"
)


@pytest.fixture(scope="module")
def kernel():
    from dna.adapters.filesystem import FilesystemWritableSource
    from dna.kernel import Kernel

    return Kernel.auto(FilesystemWritableSource(str(_BOARD)))


def _spec(doc) -> dict:
    """The instance's spec, whichever shape the query handed back."""
    raw = doc.get("spec") if isinstance(doc, dict) else getattr(doc, "spec", None)
    return raw if isinstance(raw, dict) else {}


@pytest.mark.anyio
async def test_every_relation_value_is_still_where_the_declaration_says(kernel):
    """Resolve every declared relation against the board, and count.

    ``spec.<relation name>`` is the ONLY place this looks. If the migration had
    needed to move a value, this would come back empty — the count IS the proof
    that the declaration moved and the data did not.
    """
    scopes = await kernel.list_scopes_async()
    assert scopes, "no scope resolved from the repo board"

    values = 0
    per_relation: dict[str, int] = {}

    for scope in scopes:
        for port in kernel.kind_ports(scope=scope):
            kind = getattr(port, "kind", None)
            rels = relations_of(port)
            if not kind or not rels:
                continue
            async for doc in kernel.query(scope, kind):
                spec = _spec(doc)
                for name, rel in rels.items():
                    n = len(relation_values(rel, spec))
                    if n:
                        key = f"{kind}.{name}"
                        per_relation[key] = per_relation.get(key, 0) + n
                        values += n

    missing = [p for p in _EXPECTED_PAIRS if p not in per_relation]
    assert not missing, (
        f"these relations resolved to NOTHING on a board that carries them: "
        f"{missing}. Either the board lost the instances, or a relation's name "
        f"stopped being the field that holds its value — which is the one "
        f"thing this migration promised not to change. Measured: {per_relation}"
    )
    assert values >= _MIN_VALUES, (
        f"only {values} relation values resolved (floor {_MIN_VALUES}); "
        f"measured per relation: {per_relation}"
    )
