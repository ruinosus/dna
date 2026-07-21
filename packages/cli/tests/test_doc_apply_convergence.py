"""Regression tests for i-059 — `dna doc apply` must CONVERGE.

The bug: `_apply_one` compared the RESOLVED current doc (`current.spec` — the
Kind's schema defaults are injected at parse time) against the file's RAW spec.
For any Kind with defaults (Agent injects `creative_slots: []`,
`objective: ''`, …) the two can never be equal, so re-applying a byte-identical
file was reported UPDATED — and re-written, with a version bump — forever.
Seen live in the dna-cloud definitions seed: 7 docs UNCHANGED, the Agent
UPDATED on every container boot.

The fix compares raw-against-raw: `write_document` persists the RAW doc, so
the write is a true no-op exactly when the STORED raw spec equals the incoming
one. (Resolved-vs-resolved was rejected: a file that drops a key whose value
equalled the default resolves identically but DOES change the stored doc —
and would silently track future default changes — so it must stay UPDATED.)
"""
from __future__ import annotations

import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock

from dna_cli import doc_cmd
from dna_cli.doc_cmd import _apply_one

_AGENT_RAW = {
    "apiVersion": "github.com/ruinosus/dna/v1",
    "kind": "Agent",
    "metadata": {"name": "concierge"},
    "spec": {
        "model": "openai:gpt-5-mini",
        "instruction": "You are the concierge. Answer briefly.",
    },
}


def _stored_document(raw: dict):
    """The doc as `s.get_doc` returns it: parsed by a REAL kernel (so the
    live AgentKind schema injects its defaults into `.spec`) with the stored
    raw dict riding along in `.raw` — exactly the shape the compare sees."""
    from dna.kernel import Kernel

    doc = Kernel.auto()._parse_doc(copy.deepcopy(raw))
    # Sanity — the i-059 trigger must be REAL: this Kind's parsed spec is a
    # strict superset of the raw one (defaults injected). If this ever stops
    # holding, the test no longer exercises the resolved-vs-raw divergence.
    assert dict(doc.spec) != (raw.get("spec") or {}), (
        "Agent no longer injects defaults — pick another Kind with defaults "
        "for the i-059 regression to stay meaningful"
    )
    assert isinstance(doc.raw, dict) and doc.raw.get("spec") == raw.get("spec")
    return doc


def _mock_session(stored_doc):
    kernel = MagicMock()
    kernel.write_document = AsyncMock(return_value={"ok": True})
    kernel.write_bundle_entry_async = AsyncMock(return_value=None)
    kernel.with_tenant.return_value = kernel

    s = MagicMock()
    s.kernel = kernel
    s.scope = "demo"
    s.get_doc.return_value = stored_doc

    def _run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    s.run = _run
    return s, kernel


def test_reapply_of_identical_file_is_unchanged_for_a_kind_with_defaults(
    monkeypatch, capsys,
):
    """THE i-059 convergence property: same file in, same doc stored →
    UNCHANGED, and NOTHING is written (no version churn on container boot)."""
    monkeypatch.setattr(doc_cmd, "_tenant_write_note", lambda t: (None, None))
    s, kernel = _mock_session(_stored_document(_AGENT_RAW))

    _apply_one(s, copy.deepcopy(_AGENT_RAW), path="agent.yaml", doc_index=None,
               tenant=None, dry_run=False)

    assert "UNCHANGED" in capsys.readouterr().out
    assert kernel.write_document.await_count == 0, (
        "an identical re-apply must not re-write the doc"
    )


def test_genuinely_changed_file_is_still_updated(monkeypatch, capsys):
    """The other edge of the compare: a REAL content change must keep being
    UPDATED and reach write_document — convergence must not over-rotate into
    never writing."""
    monkeypatch.setattr(doc_cmd, "_tenant_write_note", lambda t: (None, None))
    s, kernel = _mock_session(_stored_document(_AGENT_RAW))

    changed = copy.deepcopy(_AGENT_RAW)
    changed["spec"]["instruction"] = "You are the concierge. Cite sources."

    _apply_one(s, changed, path="agent.yaml", doc_index=None,
               tenant=None, dry_run=False)

    assert "UNCHANGED" not in capsys.readouterr().out
    assert kernel.write_document.await_count == 1
    written = kernel.write_document.await_args.args[3]
    assert written["spec"]["instruction"] == "You are the concierge. Cite sources."


def test_dropping_a_key_that_equalled_the_default_is_updated(monkeypatch):
    """Why raw-vs-raw (not resolved-vs-resolved): a stored doc that carries an
    EXPLICIT value equal to the Kind default resolves identically to a file
    without the key — but the stored bytes differ, and the docs drift apart
    the day the default changes. That apply must be UPDATED."""
    monkeypatch.setattr(doc_cmd, "_tenant_write_note", lambda t: (None, None))
    stored_raw = copy.deepcopy(_AGENT_RAW)
    stored_doc = _stored_document(stored_raw)
    # Pick a defaulted key the parse injected and pin it EXPLICITLY into the
    # stored raw — the incoming file omits it.
    parsed_spec = dict(stored_doc.spec)
    defaulted = sorted(set(parsed_spec) - set(stored_raw["spec"]))
    assert defaulted, "no injected defaults to exercise"
    key = defaulted[0]
    stored_raw["spec"][key] = parsed_spec[key]
    stored_doc.raw["spec"] = stored_raw["spec"]

    s, kernel = _mock_session(stored_doc)
    _apply_one(s, copy.deepcopy(_AGENT_RAW), path="agent.yaml", doc_index=None,
               tenant=None, dry_run=False)

    assert kernel.write_document.await_count == 1, (
        "removing an explicit value (even one equal to the default) changes "
        "the stored doc and must be UPDATED"
    )
