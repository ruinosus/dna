"""The ``Sprint`` Kind, and the two references that now resolve to it.

``Story.sprint_ref`` and ``Feature.sprint_ref`` shipped as free-form strings
whose ``_ref`` suffix promised an instance that did not exist. This module pins
the three things that promise now costs:

1. the Kind exists and says only what it can back up (identity + an optional
   timebox — no goal, no capacity, no item list);
2. the two fields are DECLARED references, and the declaration is exercised
   THROUGH THE DOOR — a real kernel write against a real store, so a row in
   ``dna_edges`` is the proof, not an assertion about a schema dict;
3. the doc name and ``spec.sprint_id`` cannot disagree — enforced by a
   ``pre_save`` veto, tested through ``kernel.write_instance`` rather than by
   calling the guard, because a guard nothing calls is the defect this house
   has already shipped once.
"""
from __future__ import annotations

from typing import Any

import jsonschema
import pytest
import pytest_asyncio
import sqlalchemy as sa

from dna.kernel import Kernel
from dna.kernel.protocols import SpecValidationError
from dna.kernel.kinds.relations import relations_of
from tests import _graph_store

_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"
SCOPE = "sprint-kind"


def _sprint(name: str, **spec: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sprint_id": name, "starts_on": "2026-04-06", "ends_on": "2026-04-17",
    }
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": "Sprint",
        "metadata": {"name": name}, "spec": base,
    }


def _work_item(kind: str, name: str, **spec: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"description": "d", "status": "todo"}
    base.update(spec)
    return {
        "apiVersion": _SDLC_API, "kind": kind,
        "metadata": {"name": name}, "spec": base,
    }


# ---------------------------------------------------------------------------
# 1. The Kind — registered, and minimal on purpose
# ---------------------------------------------------------------------------


class TestTheKind:
    @pytest.fixture(scope="class")
    def port(self):
        return Kernel.auto().kind_port_for("Sprint")

    def test_it_is_registered_with_the_sdlc_identity(self, port):
        assert port is not None
        assert port.alias == "sdlc-sprint"
        assert port.api_version == _SDLC_API
        assert port.plane == "record"

    def test_identity_and_the_timebox_are_required(self, port):
        """A sprint IS a timebox — a Sprint that cannot say when it runs is a
        label with a Kind wrapped around it.

        This REVERSED mid-change. The dates were optional while backward
        compatibility was a constraint (backfilling a Sprint for an existing
        free-form label would have forced two invented dates). The constraint
        was lifted, and the measurement that made it safe is the same one that
        made it pointless: ZERO instances carry a `sprint_ref`, so there was
        never a label to backfill.
        """
        assert port.schema()["required"] == ["sprint_id", "starts_on", "ends_on"]

    def test_the_schema_is_closed(self, port):
        """`additionalProperties: false` is what makes the omissions REAL.

        An open schema would let anybody write `goal:` or `velocity:` anyway,
        and the "deliberately left out" note in the descriptor would be
        decoration. Closed, the omission is a decision the model enforces.
        """
        schema = port.schema()
        assert schema["additionalProperties"] is False
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"sprint_id": "s1", "goal": "ship it"}, schema)

    @pytest.mark.parametrize(
        "absent", ["goal", "capacity", "velocity", "stories", "features",
                   "committed_points", "board", "project"],
    )
    def test_the_deliberate_omissions_stay_omitted(self, port, absent):
        """A named list, so re-adding one is a decision somebody makes here.

        `stories`/`features` are the load-bearing pair: they are the INVERSE of
        `sprint_ref`, and storing them would be a second truth that can
        disagree with the declared reference. The edge table already answers
        "what is in this sprint".
        """
        assert absent not in port.schema()["properties"]

    def test_the_timebox_is_a_date_and_the_state_is_closed(self, port):
        props = port.schema()["properties"]
        for field in ("starts_on", "ends_on"):
            assert props[field]["type"] == "string"
            assert props[field]["format"] == "date"
        assert props["state"]["enum"] == ["planned", "active", "completed"]

    def test_a_sprint_without_its_timebox_is_refused(self, port):
        """Required means refused, not merely absent from the docs."""
        import jsonschema
        schema = port.schema()
        jsonschema.validate(
            {"sprint_id": "s1", "starts_on": "2026-04-06", "ends_on": "2026-04-17"},
            schema,
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"sprint_id": "s1"}, schema)


# ---------------------------------------------------------------------------
# 2. The declaration — on BOTH work items, and identical
# ---------------------------------------------------------------------------


class TestTheDeclaration:
    @pytest.fixture(scope="class")
    def kernel(self):
        return Kernel.auto()

    @pytest.mark.parametrize("kind", ["Story", "Feature"])
    def test_sprint_ref_declares_sprint(self, kernel, kind):
        rels = relations_of(kernel.kind_port_for(kind))
        assert "sprint_ref" in rels, (
            f"{kind}.sprint_ref declares no relation — it is reference-shaped "
            f"again and the model is back to guessing"
        )
        assert rels["sprint_ref"].to == ("Sprint",)
        assert rels["sprint_ref"].cardinality == "one"
        # The claim the Kind actually makes: this one the kernel FOLLOWS. A
        # Sprint's instance name IS its sprint_id, so `by: name` is the truth
        # here rather than a convenience.
        assert rels["sprint_ref"].resolved is True

    def test_story_and_feature_agree(self, kernel):
        """Two Kinds, two definition mechanisms (a descriptor and a Python
        schema dict), one contract. They drifted apart once already — Epic
        dropped `sprint_ref` and the two survivors were edited separately.
        """
        def declaration(kind: str):
            return relations_of(
                kernel.kind_port_for(kind),
            )["sprint_ref"].to_declaration()
        assert declaration("Story") == declaration("Feature")

    def test_epic_still_has_no_sprint_ref(self, kernel):
        """Epics deliberately drop the field — sprints don't span Epics."""
        assert "sprint_ref" not in kernel.kind_port_for("Epic").schema()["properties"]


# ---------------------------------------------------------------------------
# 3. Through the door — a real write, a real store, a real edge
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    src, cleanup = await _graph_store.build_store(request.param, "sprint")
    kernel = Kernel.auto()
    kernel.source(src)
    try:
        yield kernel, src
    finally:
        await cleanup()


@pytest.fixture(autouse=True)
def _modes(monkeypatch):
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")


async def _edges(src) -> list[dict[str, Any]]:
    async with src._engine.connect() as conn:
        result = (await conn.execute(
            sa.select(src.edges).order_by(
                src.edges.c.from_kind, src.edges.c.from_name,
            )
        )).all()
    return [dict(r._mapping) for r in result]


class TestTheEdgeIsBorn:
    @pytest.mark.anyio
    @pytest.mark.parametrize("kind", ["Story", "Feature"])
    async def test_writing_a_work_item_in_a_sprint_writes_the_edge(
        self, store, kind,
    ):
        kernel, src = store
        await kernel.write_instance(
            SCOPE, "Sprint", "2026-Q2-S2", _sprint("2026-Q2-S2"),
        )
        await kernel.write_instance(
            SCOPE, kind, "w-1", _work_item(kind, "w-1", sprint_ref="2026-Q2-S2"),
        )
        rows = [r for r in await _edges(src) if r["source_field"] == "sprint_ref"]
        assert len(rows) == 1, rows
        assert rows[0]["to_kind"] == "Sprint"
        assert rows[0]["to_name"] == "2026-Q2-S2"
        assert rows[0]["from_kind"] == kind

    @pytest.mark.anyio
    async def test_the_free_form_value_that_shipped_still_persists(self, store):
        """THE compatibility claim, and the reason it is safe.

        Every `sprint_ref` written before this change names a Sprint that does
        not exist yet. Under the DEFAULT mode (`warn`) that instance still
        persists — the reference is recorded as dangling, which is a fact worth
        having, not a write worth refusing. If this test ever goes red, the
        change stopped being backwards compatible.
        """
        kernel, src = store
        await kernel.write_instance(
            SCOPE, "Story", "s-legacy",
            _work_item("Story", "s-legacy", sprint_ref="2026-Q2-S2"),
        )
        assert await kernel.get_instance(SCOPE, "Story", "s-legacy") is not None
        rows = [r for r in await _edges(src) if r["source_field"] == "sprint_ref"]
        assert len(rows) == 1
        assert rows[0]["to_kind"] is None       # dangling, and honest about it
        assert rows[0]["to_name"] == "2026-Q2-S2"

    @pytest.mark.anyio
    async def test_creating_the_sprint_later_resolves_the_same_value(self, store):
        """The migration path, proven: name the Sprint doc after the label.

        No story is edited, no value is rewritten — the identifier the board
        already carries becomes resolvable the moment the instance exists.
        """
        kernel, src = store
        await kernel.write_instance(
            SCOPE, "Story", "s-legacy",
            _work_item("Story", "s-legacy", sprint_ref="2026-Q2-S2"),
        )
        await kernel.write_instance(
            SCOPE, "Sprint", "2026-Q2-S2", _sprint("2026-Q2-S2"),
        )
        # Re-asserting the story is what re-resolves it (edges are produced by
        # a write, never by a background sweep).
        await kernel.write_instance(
            SCOPE, "Story", "s-legacy",
            _work_item("Story", "s-legacy", sprint_ref="2026-Q2-S2"),
        )
        rows = [r for r in await _edges(src) if r["source_field"] == "sprint_ref"]
        assert [r["to_kind"] for r in rows] == ["Sprint"]

    @pytest.mark.anyio
    async def test_enforce_vetoes_a_sprint_that_does_not_exist(
        self, store, monkeypatch,
    ):
        """The other half of the compatibility statement, stated out loud.

        Under `DNA_REF_VALIDATION=enforce` — CI and operators who opted in —
        a work item naming an absent Sprint is now REFUSED where it used to
        pass. That is the cost of the declaration, and it is measured here
        rather than discovered.
        """
        kernel, _ = store
        monkeypatch.setenv("DNA_REF_VALIDATION", "enforce")
        with pytest.raises(SpecValidationError) as exc:
            await kernel.write_instance(
                SCOPE, "Story", "s-1",
                _work_item("Story", "s-1", sprint_ref="2026-Q2-S2"),
            )
        assert "Sprint" in str(exc.value)
        assert "2026-Q2-S2" in str(exc.value)


# ---------------------------------------------------------------------------
# 4. One key, one truth — the identity guard, at the door
# ---------------------------------------------------------------------------


class TestTheIdentityGuard:
    @pytest.mark.anyio
    async def test_a_mismatched_sprint_id_is_refused_by_the_kernel(self, store):
        """Through ``kernel.write_instance``, deliberately.

        Calling ``sprint_identity_guard`` directly would prove the function
        works and nothing about whether any door calls it — the exact shape of
        a guard this repo shipped green and unreachable before.
        """
        kernel, src = store
        with pytest.raises(ValueError) as exc:
            await kernel.write_instance(
                SCOPE, "Sprint", "2026-Q2-S2",
                _sprint("2026-Q2-S2", sprint_id="2026-Q2-S3"),
            )
        assert "2026-Q2-S3" in str(exc.value)
        assert "2026-Q2-S2" in str(exc.value)
        assert await kernel.get_instance(SCOPE, "Sprint", "2026-Q2-S2") is None

    @pytest.mark.anyio
    async def test_the_matching_write_goes_through(self, store):
        """The guard's other half — without this the mutant `raise always`
        passes the test above.
        """
        kernel, _ = store
        await kernel.write_instance(
            SCOPE, "Sprint", "2026-Q2-S2", _sprint("2026-Q2-S2"),
        )
        assert await kernel.get_instance(SCOPE, "Sprint", "2026-Q2-S2") is not None

    @pytest.mark.anyio
    async def test_the_guard_minds_its_own_Kind(self, store):
        """A Story carrying a stray `sprint_id` is not the guard's business —
        a veto hook that fires on the wrong Kind is worse than no hook.
        """
        kernel, _ = store
        await kernel.write_instance(
            SCOPE, "Story", "s-1",
            _work_item("Story", "s-1", sprint_ref="whatever"),
        )
        assert await kernel.get_instance(SCOPE, "Story", "s-1") is not None
