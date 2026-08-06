"""``dna sdlc spec executed`` / ``shelve`` / ``deprecate --reason`` — the verbs.

Same harness as ``test_sdlc_workitem_cli``: REAL creates and transitions
against an in-memory store, with the fake session injected through the click
context. The write path (spec assembly, timeline stamping, ``_build_raw``) runs
for real — only the HTTP boundary is faked.

What the three verbs are FOR is written up in
``sdk-py/tests/test_spec_lifecycle_states.py``; this file is about the CLI's
half of the contract, which is one word: EVIDENCE. A terminal state whose
reason lives in someone's memory is worse than no state at all — the board goes
quiet AND nobody can reconstruct why. So ``--summary`` / ``--reason`` are
required on the two new verbs, and both land in the doc *and* the timeline.
"""
from __future__ import annotations

import pytest

from dna_cli.sdlc_cmd import sdlc


@pytest.fixture
def runner(sdlc_runner):
    return sdlc_runner


def _spec(runner, store, name="spec-x", status=None):
    """Create a Spec (optionally at a given status) and return its key."""
    args = ["spec", "create", name, "--title", "T"]
    if status:
        args += ["--status", status]
    result = runner.invoke(sdlc, args)
    assert result.exit_code == 0, result.output
    return ("dna-development", "Spec", name)


# ── executed ─────────────────────────────────────────────────────────────────

def test_spec_executed_records_status_stamp_and_proof(runner, store):
    key = _spec(runner, store, "spec-auth", status="accepted")
    result = runner.invoke(
        sdlc,
        ["spec", "executed", "spec-auth", "--summary", "PR #221, PR #224, release 0.60.0"],
    )
    assert result.exit_code == 0, result.output
    assert "UPDATED Spec/spec-auth → executed" in result.output

    spec = store[key]["spec"]
    assert spec["status"] == "executed"
    assert spec["executed_at"]
    assert spec["execution_summary"] == "PR #221, PR #224, release 0.60.0"
    # The proof is also on the timeline, where every other verb puts its
    # summary — a board reading the feed sees WHY without opening the doc.
    last = spec["timeline"][-1]
    assert last["type"] == "status_change"
    assert last["from"] == "accepted" and last["to"] == "executed"
    assert last["summary"] == "PR #221, PR #224, release 0.60.0"


def test_spec_executed_requires_the_proof(runner, store):
    """No ``--summary``, no transition. This is the whole point of the state:
    without evidence `executed` is a claim, and a board cannot audit a claim."""
    _spec(runner, store, "spec-noproof", status="accepted")
    result = runner.invoke(sdlc, ["spec", "executed", "spec-noproof"])
    assert result.exit_code != 0
    assert "summary" in result.output.lower()


@pytest.mark.parametrize("frm", ["draft", "proposed", "accepted"])
def test_spec_executed_from_any_live_state(runner, store, frm):
    """A design that shipped without a formal `accept` still shipped."""
    key = _spec(runner, store, f"spec-{frm}", status=frm)
    result = runner.invoke(
        sdlc, ["spec", "executed", f"spec-{frm}", "--summary", "PR #1"],
    )
    assert result.exit_code == 0, result.output
    assert store[key]["spec"]["status"] == "executed"


@pytest.mark.parametrize("frm", ["deprecated", "superseded"])
def test_spec_executed_refused_from_a_dead_spec(runner, store, frm):
    """The arc guard reaches the CLI: a design declared obsolete or replaced
    did not become code, and the refusal says so BEFORE the write."""
    key = _spec(runner, store, f"spec-dead-{frm}", status=frm)
    result = runner.invoke(
        sdlc, ["spec", "executed", f"spec-dead-{frm}", "--summary", "PR #1"],
    )
    assert result.exit_code != 0
    assert frm in result.output
    # And the instance was NOT touched — a refused transition that half-wrote
    # would be worse than one that never ran.
    assert store[key]["spec"]["status"] == frm
    assert "executed_at" not in store[key]["spec"]


# ── shelve ───────────────────────────────────────────────────────────────────

def test_spec_shelve_records_status_stamp_and_reason(runner, store):
    key = _spec(runner, store, "spec-delegada", status="accepted")
    reason = "opção D do founder: adiar até haver um segundo IdP delegado pedindo"
    result = runner.invoke(
        sdlc, ["spec", "shelve", "spec-delegada", "--reason", reason],
    )
    assert result.exit_code == 0, result.output
    assert "UPDATED Spec/spec-delegada → shelved" in result.output

    spec = store[key]["spec"]
    assert spec["status"] == "shelved"
    assert spec["shelved_at"]
    assert spec["shelve_reason"] == reason
    assert spec["timeline"][-1]["summary"] == reason
    # Shelving is NOT deprecation — the design is still valid, and nothing on
    # the doc may suggest otherwise.
    assert "deprecation_reason" not in spec


def test_spec_shelve_requires_the_reason(runner, store):
    """A shelving whose WHY lives outside the doc is a decision nobody can
    revisit — which defeats the point of a reversible state."""
    _spec(runner, store, "spec-why", status="accepted")
    result = runner.invoke(sdlc, ["spec", "shelve", "spec-why"])
    assert result.exit_code != 0
    assert "reason" in result.output.lower()


def test_spec_shelve_refused_once_executed(runner, store):
    key = _spec(runner, store, "spec-shipped", status="accepted")
    runner.invoke(sdlc, ["spec", "executed", "spec-shipped", "--summary", "PR #1"])
    result = runner.invoke(
        sdlc, ["spec", "shelve", "spec-shipped", "--reason", "not now"],
    )
    assert result.exit_code != 0
    assert store[key]["spec"]["status"] == "executed"


def test_a_shelved_spec_can_be_un_shelved(runner, store):
    """`shelved` is terminal on the board, not in the graph. When the direction
    changes, `accept` brings it back — and then it can be built."""
    key = _spec(runner, store, "spec-later", status="accepted")
    runner.invoke(sdlc, ["spec", "shelve", "spec-later", "--reason", "not now"])
    assert runner.invoke(sdlc, ["spec", "accept", "spec-later"]).exit_code == 0
    assert store[key]["spec"]["status"] == "accepted"
    result = runner.invoke(
        sdlc, ["spec", "executed", "spec-later", "--summary", "PR #9"],
    )
    assert result.exit_code == 0, result.output
    assert store[key]["spec"]["status"] == "executed"


# ── deprecate --reason ───────────────────────────────────────────────────────

def test_spec_deprecate_now_carries_its_reason(runner, store):
    key = _spec(runner, store, "spec-old", status="accepted")
    result = runner.invoke(
        sdlc, ["spec", "deprecate", "spec-old", "--reason", "the port it designed is gone"],
    )
    assert result.exit_code == 0, result.output
    spec = store[key]["spec"]
    assert spec["status"] == "deprecated"
    assert spec["deprecation_reason"] == "the port it designed is gone"
    assert spec["deprecated_at"]
    assert spec["timeline"][-1]["summary"] == "the port it designed is gone"


def test_spec_deprecate_without_reason_still_works(runner, store):
    """Back-compat: ``--reason`` is new, so it cannot be required — every
    existing caller passes none."""
    key = _spec(runner, store, "spec-bare", status="accepted")
    result = runner.invoke(sdlc, ["spec", "deprecate", "spec-bare"])
    assert result.exit_code == 0, result.output
    spec = store[key]["spec"]
    assert spec["status"] == "deprecated"
    assert "deprecation_reason" not in spec


# ── the arc as the CLI exposes it ────────────────────────────────────────────

def test_spec_create_accepts_the_new_statuses(runner, store):
    for status in ("executed", "shelved"):
        key = _spec(runner, store, f"spec-c-{status}", status=status)
        assert store[key]["spec"]["status"] == status


def test_plan_did_not_inherit_the_spec_verbs(runner):
    """Plan declares its own enum (plan.kind.yaml), so it must not grow verbs
    whose status its schema would reject at the write."""
    out = runner.invoke(sdlc, ["plan", "--help"]).output
    assert "executed" not in out
    assert "shelve" not in out
    rejected = runner.invoke(sdlc, ["plan", "create", "p-x", "--title", "T",
                                    "--status", "executed"])
    assert rejected.exit_code != 0


def test_spec_help_lists_the_two_new_verbs(runner):
    out = runner.invoke(sdlc, ["spec", "--help"]).output
    assert "executed" in out
    assert "shelve" in out


def test_pre_existing_spec_transitions_are_unchanged(runner, store):
    """The four verbs that existed before still do exactly what they did — the
    change is additive or it is a migration, and this was meant to be additive."""
    key = _spec(runner, store, "spec-legacy")
    assert store[key]["spec"]["status"] == "draft"
    assert runner.invoke(sdlc, ["spec", "propose", "spec-legacy"]).exit_code == 0
    assert store[key]["spec"]["status"] == "proposed"
    assert runner.invoke(sdlc, ["spec", "accept", "spec-legacy"]).exit_code == 0
    assert store[key]["spec"]["status"] == "accepted"
    assert store[key]["spec"]["accepted_at"]
    assert runner.invoke(
        sdlc, ["spec", "supersede", "spec-legacy", "--by", "spec-new"]
    ).exit_code == 0
    assert store[key]["spec"]["superseded_by"] == "spec-new"


def test_an_executed_spec_can_still_be_superseded(runner, store):
    """A design that shipped and was later replaced: both facts are true, and
    the guard must not stand in the way of recording the second."""
    key = _spec(runner, store, "spec-v1", status="accepted")
    runner.invoke(sdlc, ["spec", "executed", "spec-v1", "--summary", "PR #1"])
    result = runner.invoke(sdlc, ["spec", "supersede", "spec-v1", "--by", "spec-v2"])
    assert result.exit_code == 0, result.output
    assert store[key]["spec"]["status"] == "superseded"
