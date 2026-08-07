"""Decision A — the methodology gates hold on EVERY write path, not just the CLI.

The gates lived in ``dna_cli.sdlc_cmd``: ``story create`` refused without AC+DoD,
``story done`` refused without a passing product TestRun. The MCP ``create_story``
and ``set_status`` tools called the same core and reached neither. As MCP becomes
the primary write path, that made the hosted door the documented way around the
project's own discipline.

These tests exercise the CORE — ``dna.application.sdlc``, which both faces call —
so a face that stops delegating is the only way to regress them.
"""
from __future__ import annotations

import pytest

from dna.application import sdlc as S
from dna.application.gates import (
    GATE_EXIT_CRITERIA,
    GATE_TEST_ON_CLOSE,
    MethodologyRefusal,
    has_passing_product_run,
    kind_is_gated,
    refuse_close_without_tests,
    refuse_without_exit_criteria,
)
from dna.kernel import Kernel


# ── the gates are DECLARED, not branched on a Kind name ─────────────────────


def test_story_declares_both_gates():
    k = Kernel.auto()
    assert kind_is_gated(k, "Story", GATE_EXIT_CRITERIA)
    assert kind_is_gated(k, "Story", GATE_TEST_ON_CLOSE)


def test_an_ungated_kind_is_not_gated():
    k = Kernel.auto()
    assert not kind_is_gated(k, "Feature", GATE_TEST_ON_CLOSE)
    assert not kind_is_gated(k, "NoSuchKind", GATE_EXIT_CRITERIA)


# ── gate 1: exit criteria (pure) ────────────────────────────────────────────


def test_exit_criteria_refuses_when_both_missing():
    with pytest.raises(MethodologyRefusal) as exc:
        refuse_without_exit_criteria(
            kind="Story", name="s-x",
            acceptance_criteria=None, definition_of_done=None,
        )
    assert "acceptance_criteria" in str(exc.value)
    assert "definition_of_done" in str(exc.value)


def test_exit_criteria_refuses_when_only_one_is_missing():
    with pytest.raises(MethodologyRefusal) as exc:
        refuse_without_exit_criteria(
            kind="Story", name="s-x",
            acceptance_criteria=["Given X, when Y, then Z"],
            definition_of_done=[],
        )
    assert "definition_of_done" in str(exc.value)
    assert "acceptance_criteria" not in str(exc.value).split("Examples")[0]


def test_exit_criteria_passes_when_both_present():
    refuse_without_exit_criteria(
        kind="Story", name="s-x",
        acceptance_criteria=["Given X"], definition_of_done=["Code + tests"],
    )


def test_exit_criteria_backfill_escape():
    refuse_without_exit_criteria(
        kind="Story", name="s-x", acceptance_criteria=None,
        definition_of_done=None, allow_no_ac_dod=True,
    )


# ── gate 2: a passing product TestRun before a close (pure half) ────────────


def test_close_gate_passes_with_a_passing_run():
    assert refuse_close_without_tests(
        kind="Story", name="s-x", status="done", has_passing_run=True,
    ) is None


def test_close_gate_refuses_without_one():
    with pytest.raises(MethodologyRefusal, match="PRODUCT smoke"):
        refuse_close_without_tests(
            kind="Story", name="s-x", status="done", has_passing_run=False,
        )


def test_close_gate_escape_requires_a_reason():
    """The CLI's --allow-no-tests said 'registered exception' and recorded
    nothing. Here the record is the price of the escape."""
    with pytest.raises(MethodologyRefusal, match="needs a REASON"):
        refuse_close_without_tests(
            kind="Story", name="s-x", status="done", has_passing_run=False,
            allow_no_tests=True,
        )
    assert refuse_close_without_tests(
        kind="Story", name="s-x", status="done", has_passing_run=False,
        allow_no_tests=True, reason="verification deferred to i-099",
    ) == "verification deferred to i-099"


def test_close_gate_no_code_escape_also_requires_a_reason():
    with pytest.raises(MethodologyRefusal, match="needs a REASON"):
        refuse_close_without_tests(
            kind="Story", name="s-x", status="done", has_passing_run=False,
            no_code=True,
        )


# ── the async half, against a real in-memory board ──────────────────────────


class _FakeKernel:
    """The narrow kernel surface the SDLC write core touches."""

    def __init__(self, kernel: Kernel, docs=None):
        self._real = kernel
        self.docs: dict[tuple[str, str, str], dict] = dict(docs or {})
        self.writes: list[tuple] = []

    # -- delegated to a real kernel so traits/schemas are the REAL ones ----
    def traits_of(self, kind, **kw):
        return self._real.traits_of(kind, **kw)

    def kind_port_for(self, kind, **kw):
        return self._real.kind_port_for(kind, **kw)

    def kinds_with_trait(self, trait):
        return self._real.kinds_with_trait(trait)

    def kind_ports(self):
        return self._real.kind_ports()

    # -- the storage half ---------------------------------------------------
    async def get_instance(self, scope, kind, name):
        return self.docs.get((scope, kind, name))

    async def query(self, scope, kind, **kw):
        for (sc, kd, _nm), doc in self.docs.items():
            if sc == scope and kd == kind:
                yield doc

    async def write_instance(self, scope, kind, name, raw, **kw):
        self.writes.append((scope, kind, name, raw))
        self.docs[(scope, kind, name)] = raw


def _story(name="s-x", status="review", **spec_extra):
    return {
        "apiVersion": S.SDLC_API_VERSION,
        "kind": "Story",
        "metadata": {"name": name, "labels": {"team": "core"}},
        "spec": {"title": "T", "status": status, "feature": "f-x", **spec_extra},
    }


@pytest.mark.asyncio
async def test_mcp_path_refuses_closing_a_story_without_a_passing_testrun():
    """THE proof: the exact call the MCP ``set_status`` tool makes."""
    k = _FakeKernel(Kernel.auto(), {("sc", "Story", "s-x"): _story()})
    with pytest.raises(MethodologyRefusal, match="PRODUCT smoke"):
        await S.set_status(k, "sc", "Story", "s-x", "done")
    assert k.writes == [], "the refused close must not have written anything"


@pytest.mark.asyncio
async def test_mcp_path_allows_the_close_once_a_passing_product_run_exists():
    real = Kernel.auto()
    docs = {
        ("sc", "Story", "s-x"): _story(),
        ("sc", "TestGuide", "tg-x"): {
            "kind": "TestGuide", "metadata": {"name": "tg-x"},
            "spec": {"kind_of_test": "smoke"},
        },
        ("sc", "TestRun", "tr-1"): {
            "kind": "TestRun", "metadata": {"name": "tr-1"},
            "spec": {"outcome": "pass", "guide_ref": "tg-x",
                     "verifies": ["Story/s-x"]},
        },
    }
    k = _FakeKernel(real, docs)
    assert await has_passing_product_run(k, "sc", "Story", "s-x") is True
    out = await S.set_status(k, "sc", "Story", "s-x", "done")
    assert out["to"] == "done"
    assert k.docs[("sc", "Story", "s-x")]["spec"]["status"] == "done"


@pytest.mark.asyncio
async def test_an_automated_lane_run_does_not_satisfy_the_gate():
    """integration/e2e/regression are proven by CI on the PR, not by a
    hand-recorded run — same restriction the CLI applies."""
    docs = {
        ("sc", "Story", "s-x"): _story(),
        ("sc", "TestGuide", "tg-x"): {
            "kind": "TestGuide", "metadata": {"name": "tg-x"},
            "spec": {"kind_of_test": "integration"},
        },
        ("sc", "TestRun", "tr-1"): {
            "kind": "TestRun", "metadata": {"name": "tr-1"},
            "spec": {"outcome": "pass", "guide_ref": "tg-x",
                     "verifies": ["Story/s-x"]},
        },
    }
    k = _FakeKernel(Kernel.auto(), docs)
    assert await has_passing_product_run(k, "sc", "Story", "s-x") is False
    with pytest.raises(MethodologyRefusal):
        await S.set_status(k, "sc", "Story", "s-x", "done")


@pytest.mark.asyncio
async def test_the_escape_is_recorded_on_the_timeline():
    k = _FakeKernel(Kernel.auto(), {("sc", "Story", "s-x"): _story()})
    out = await S.set_status(
        k, "sc", "Story", "s-x", "done",
        allow_no_tests=True, gate_reason="doc-only change, no product surface",
    )
    assert out["gate_exception"]["gate"] == GATE_TEST_ON_CLOSE
    timeline = k.docs[("sc", "Story", "s-x")]["spec"]["timeline"]
    exceptions = [e for e in timeline if e["type"] == "exception"]
    assert len(exceptions) == 1
    assert exceptions[0]["summary"] == "doc-only change, no product surface"
    assert exceptions[0]["gate"] == GATE_TEST_ON_CLOSE


@pytest.mark.asyncio
async def test_a_non_closing_transition_is_not_gated():
    k = _FakeKernel(Kernel.auto(), {("sc", "Story", "s-x"): _story(status="todo")})
    out = await S.set_status(k, "sc", "Story", "s-x", "in-progress")
    assert out["to"] == "in-progress"


@pytest.mark.asyncio
async def test_create_story_refuses_without_exit_criteria():
    k = _FakeKernel(Kernel.auto())
    with pytest.raises(MethodologyRefusal, match="missing exit criteria"):
        await S.create_story(k, "sc", "s-new", feature="f-x", description="d")
    assert k.writes == []


@pytest.mark.asyncio
async def test_create_story_succeeds_with_exit_criteria():
    k = _FakeKernel(Kernel.auto())
    out = await S.create_story(
        k, "sc", "s-new", feature="f-x", description="d",
        acceptance_criteria=["Given X"], definition_of_done=["Code + tests"],
    )
    assert out["name"] == "s-new"


# ── the warnings travel (they have no stderr to go to over MCP) ─────────────


@pytest.mark.asyncio
async def test_closing_warnings_are_returned_not_printed():
    docs = {
        ("sc", "Story", "s-x"): _story(status="todo"),
        ("sc", "TestGuide", "tg-x"): {
            "kind": "TestGuide", "metadata": {"name": "tg-x"},
            "spec": {"kind_of_test": "smoke"},
        },
        ("sc", "TestRun", "tr-1"): {
            "kind": "TestRun", "metadata": {"name": "tr-1"},
            "spec": {"outcome": "pass", "guide_ref": "tg-x", "verifies": ["s-x"]},
        },
    }
    k = _FakeKernel(Kernel.auto(), docs)
    out = await S.set_status(k, "sc", "Story", "s-x", "done")
    joined = " ".join(out["warnings"])
    assert "no shipping commit" in joined
    assert "without passing through review" in joined
    assert "no linked outputs" in joined
