"""The dated-spec-field guard, CLI half — every ``dna sdlc … create`` verb.

Companion to ``packages/sdk-py/tests/test_dated_spec_fields.py``, which holds
the SDK's three pure builders to
:data:`dna.application.sdlc.DATED_SPEC_FIELDS`. This module holds the OTHER
write face to the same contract: the ``dna sdlc`` command tree, where most
Kinds hand-assemble their own spec dict.

Why both halves are needed — ``i-078`` shipped the hole twice. The MCP tool
went through ``build_issue_spec`` and the CLI's ``issue file`` hand-built an
identical dict; *neither* stamped ``created_at``, and the digest dates a filed
Issue by exactly that field. Fixing one builder would have left the other
writing invisible Issues.

Each case runs the REAL command against the in-memory fake session
(``conftest.sdlc_runner``), so the assertion is about what actually lands in
the store — not about what a builder returns in isolation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dna.application.sdlc import DATED_SPEC_FIELDS
from dna_cli._digest import build_digest
from dna_cli.sdlc_cmd import sdlc

_SCOPE = "dna-development"


#: ``Kind → (setup argvs, create argv)``. One entry per Kind in the registry;
#: ``test_every_declared_kind_is_exercised`` fails if that stops being true, so
#: declaring a Kind and forgetting to guard its create verb is itself caught.
_CREATE_VERBS: dict[str, tuple[list[list[str]], list[str]]] = {
    "Story": ([], [
        "story", "create", "s-guard", "--feature", "f-x", "--desc", "A story",
        "--ac", "Given/When/Then", "--dod", "code+tests",
    ]),
    "Issue": ([], ["issue", "file", "--slug", "guard", "--desc", "An issue"]),
    "Feature": ([], ["feature", "create", "f-guard", "--title", "T", "--desc", "D"]),
    "Epic": ([], ["epic", "create", "e-guard", "--title", "T", "--desc", "D"]),
    "Initiative": ([], [
        "initiative", "create", "in-guard", "--title", "T", "--desc", "D",
    ]),
    "Spike": ([], ["spike", "create", "sp-guard", "--question", "Redis or in-proc?"]),
    "Bug": ([], ["bug", "create", "b-guard", "--desc", "Login returns 500"]),
    "Task": ([], ["task", "create", "t-guard", "--desc", "Add DB index"]),
    "ADR": ([], [
        "adr", "create", "adr-guard", "--title", "T",
        "--context", "C", "--decision", "D",
    ]),
    "Spec": ([], ["spec", "create", "spec-guard", "--title", "T"]),
    "Plan": ([], ["plan", "create", "plan-guard", "--title", "T"]),
    # `kaizen flag` needs a work item to hang the observation on, and names the
    # Kaizen doc itself (kz-NNN-<slug>) — hence the setup step + lookup by Kind.
    "Kaizen": ([[
        "story", "create", "s-host", "--feature", "f-x", "--desc", "Host story",
        "--ac", "A", "--dod", "B",
    ]], ["kaizen", "flag", "s-host", "--body", "this could be simpler"]),
}


def _run(runner, argvs):
    for argv in argvs:
        result = runner.invoke(sdlc, argv)
        assert result.exit_code == 0, f"{argv}: exit {result.exit_code}\n{result.output}"


def _only_doc_of_kind(store: dict, kind: str) -> dict:
    docs = [raw for (_sc, kd, _nm), raw in store.items() if kd == kind]
    assert len(docs) == 1, f"expected exactly one {kind} in the store, got {len(docs)}"
    return docs[0]


# ── the guard ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", sorted(_CREATE_VERBS))
def test_create_verb_stamps_every_dated_field(sdlc_runner, store, kind):
    """A create verb that skips a declared field files a document its own read
    surfaces cannot date — silently, forever (i-078)."""
    setup, argv = _CREATE_VERBS[kind]
    _run(sdlc_runner, [*setup, argv])
    spec = _only_doc_of_kind(store, kind)["spec"]
    declared = DATED_SPEC_FIELDS[kind]
    missing = [field for field in declared if not spec.get(field)]
    assert not missing, (
        f"`dna sdlc {' '.join(argv[:2])}` omits {missing} — DATED_SPEC_FIELDS "
        f"declares {list(declared)} for {kind} because a read surface "
        f"dates/sorts/filters it by them (the digest's `found`/`decided` "
        f"buckets, the derived journey, the narrative recency sort). Stamp "
        f"them on the create path (`_stamp_create` does exactly this)."
    )


def test_every_declared_kind_is_exercised():
    """Adding a Kind to the registry without a create case here would leave the
    guard passing vacuously for it."""
    unexercised = sorted(set(DATED_SPEC_FIELDS) - set(_CREATE_VERBS))
    assert not unexercised, (
        f"declared in DATED_SPEC_FIELDS but no create verb is exercised: "
        f"{unexercised}"
    )


# ── i-078 proper: the CLI path + the payoff it buys ─────────────────────────


def test_issue_file_stamps_created_and_updated_at(sdlc_runner, store):
    result = sdlc_runner.invoke(
        sdlc, ["issue", "file", "--slug", "date-bug", "--desc", "Digest is blind"],
    )
    assert result.exit_code == 0, result.output
    spec = store[(_SCOPE, "Issue", "i-001-date-bug")]["spec"]
    assert spec["created_at"]
    assert spec["updated_at"]


def test_issue_file_accepts_a_title(sdlc_runner, store):
    result = sdlc_runner.invoke(sdlc, [
        "issue", "file", "--slug", "titled", "--desc", "long description here",
        "--title", "Digest never lists filed Issues",
    ])
    assert result.exit_code == 0, result.output
    spec = store[(_SCOPE, "Issue", "i-001-titled")]["spec"]
    assert spec["title"] == "Digest never lists filed Issues"


def test_a_filed_issue_reaches_the_digests_found_bucket(sdlc_runner, store):
    """The payoff, end to end: file an Issue through the CLI, aggregate a digest
    over a window containing it, and see it in ``found``. Before the fix the
    bucket came back empty for every window there has ever been."""
    result = sdlc_runner.invoke(
        sdlc, ["issue", "file", "--slug", "invisible", "--desc", "Digest is blind"],
    )
    assert result.exit_code == 0, result.output
    raw = store[(_SCOPE, "Issue", "i-001-invisible")]

    now = datetime.now(timezone.utc)
    digest = build_digest(
        docs=[{"kind": "Issue", "name": "i-001-invisible", "spec": raw["spec"]}],
        since=now - timedelta(hours=1), until=now + timedelta(hours=1),
    )
    assert [r["name"] for r in digest["found"]] == ["i-001-invisible"]
    assert digest["counts"]["found"] == 1
