"""Revoking a Kind is a THIRD state — not the absence of approval (i-085).

The discovery this whole suite is built around: **revoking is not the inverse of
approving.** Removing the approval returns the Kind to *unregistered*, and
unregistered means documents are accepted with NO validation at all. So the
naive fix LOOSENS instead of tightening — it switches the gate off rather than
closing it.

    state            existing documents      new documents
    ---------------- ---------------------- ---------------------------
    never approved   —                       accepted WITHOUT validation
    approved         valid, routed           validated against the schema
    revoked          INVALID                 REFUSED

``test_revoking_does_not_return_the_kind_to_accepting_anything`` is the one that
pins the trap: it was first run against a revocation implemented as a plain
un-approval, and watched to ACCEPT a schema-violating document.

Every "did this take effect?" probe here runs on a **fresh kernel** over the
same store. The registry is per-kernel and outlives an ``instance_async`` call,
so asking the writing kernel whether a registration changed can be true for the
wrong reason.
"""
from __future__ import annotations

from typing import Any

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.extensions.kinddef import KindDefinitionExtension
from dna.kernel import Kernel
from dna.kernel.errors import RevokedKindWrite
from dna.kernel.kinds import registry as registry_mod
from dna.kernel.kinds.approval import APPROVED, REVOKED, UNAPPROVED, approval_state
from dna.kernel.protocols import SpecValidationError
from dna.kernel.validity import STATUS_KEY, is_marked_invalid

_SCOPE = "test-scope"
_API = "example.com/v1"

#: A schema with something to violate — the control that tells "validated"
#: apart from "accepted because nobody was looking".
_SCHEMA = {
    "type": "object",
    "properties": {"size": {"type": "string"}},
    "required": ["size"],
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def _clear_process_wide_warn_caches():
    """Same fixture, same reason, as ``test_kind_approval_gate.py``: the funnel's
    refusals are warned once per (scope, apiVersion, kind) per PROCESS, and a
    pytest session is one process."""
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    yield
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()


def _kernel(root) -> Kernel:
    """A writable Kernel over ``root`` — call it again for a FRESH one."""
    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())
    k.source(FilesystemWritableSource(str(root), kernel=k))
    k.cache(FilesystemCache(str(root)))
    return k


@pytest.fixture
def store(tmp_path):
    """A filesystem scope, plus a factory for fresh kernels over it."""
    scope_dir = tmp_path / _SCOPE
    scope_dir.mkdir(parents=True)
    (scope_dir / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {_SCOPE}\n"
        "spec: {}\n"
    )
    return tmp_path


def _kinddef_raw(kind: str, *, approved: bool, revoked: bool = False) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "target_api_version": _API,
        "target_kind": kind,
        "alias": f"example-{kind.lower()}",
        "origin": "example.com",
        "schema": _SCHEMA,
        "storage": {"type": "yaml", "container": f"{kind.lower()}s"},
    }
    if approved:
        spec["approved_by"] = "reviewer@example.com"
        spec["approved_at"] = "2026-07-25T12:00:00Z"
    if revoked:
        spec["revoked_by"] = "reviewer@example.com"
        spec["revoked_at"] = "2026-07-28T12:00:00Z"
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": kind.lower()},
        "spec": spec,
    }


async def _write_kinddef(k: Kernel, kind: str, **state: bool) -> None:
    await k.write_document(
        _SCOPE, "KindDefinition", kind.lower(), _kinddef_raw(kind, **state),
    )


async def _revoke(k: Kernel, kind: str) -> None:
    """Revoke ``kind`` in the store — the THIRD state.

    ``approved_by`` deliberately STAYS: the audit must keep who conferred effect
    in the first place, and the state is decided by
    :func:`~dna.kernel.kinds.approval.approval_state`, not by absence.

    This helper was first written as the MUTANT — a plain un-approval, dropping
    ``approved_by`` and nothing else, which is what "revoking is the inverse of
    approving" means in code. Run that way, the loosening test below watched a
    schema-violating document be ACCEPTED.
    """
    await k.write_document(
        _SCOPE, "KindDefinition", kind.lower(),
        _kinddef_raw(kind, approved=True, revoked=True),
    )


async def _seed(root, kind: str = "Widget") -> Kernel:
    """A kernel with ``kind`` authored, APPROVED and REGISTERED — ready to write
    documents that route to the Kind's declared container.

    The ``instance_async`` is not ceremony: registration is what confers storage
    routing, so a document written before the Kind registers lands at the scope
    root instead of in its container, and a later delete would look in the wrong
    place. Seeding through the real load path keeps the fixture honest about
    what the approved state actually does."""
    k = _kernel(root)
    await _write_kinddef(k, kind, approved=True)
    await k.instance_async(_SCOPE)
    return k


async def _write_doc(k: Kernel, kind: str, name: str, spec: dict[str, Any]) -> None:
    await k.write_document(_SCOPE, kind, name, {
        "apiVersion": _API,
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    })


async def _on_fresh_kernel(root, fn):
    """Run ``fn(kernel)`` on a kernel booted FRESH over the same store, with the
    scope's manifest instance built — i.e. after the real 2-phase load has
    parsed every stored ``KindDefinition`` and applied the approval gate.

    The registry is per-kernel and outlives an ``instance_async`` call, so a
    probe on the WRITING kernel can be true for the wrong reason."""
    k = _kernel(root)
    await k.instance_async(_SCOPE)
    return await fn(k)


# ── the loosening trap ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoking_does_not_return_the_kind_to_accepting_anything(store):
    """Revoking must TIGHTEN, never loosen.

    Removing the approval returns the Kind to *unregistered*, and an
    unregistered Kind's documents are accepted with no validation at all. So a
    revocation implemented as a plain un-approval switches the gate OFF: the
    exact document the approved Kind refused becomes acceptable.
    """
    violating = {"size": 42, "unexpected": True}  # wrong type + extra key

    k = _kernel(store)
    await _write_kinddef(k, "Widget", approved=True)

    # Control — while APPROVED, the violating document is refused.
    async def refuses_while_approved(fresh):
        with pytest.raises(SpecValidationError):
            await _write_doc(fresh, "Widget", "w-bad", violating)
    await _on_fresh_kernel(store, refuses_while_approved)

    await _revoke(k, "Widget")

    async def still_refuses_after_revocation(fresh):
        assert fresh.kind_port_for("Widget", scope=_SCOPE) is not None, (
            "a REVOKED Kind must stay KNOWN to the registry — an unknown Kind "
            "is the permissive state, and forgetting the Kind is how "
            "revocation turns into 'accepts anything'"
        )
        # RefusedKindWrite, not SpecValidationError: the document's shape is no
        # longer the subject. Both are ValueError, so the assertion is on the
        # exact type — matching the base would pass on the mutant's behaviour
        # too if the schema happened to still bite.
        with pytest.raises(RevokedKindWrite):
            await _write_doc(fresh, "Widget", "w-bad-2", violating)
    await _on_fresh_kernel(store, still_refuses_after_revocation)


# ── the third state persists, and is read in one place ────────────────────


def test_approval_state_is_three_states_and_revocation_is_not_absence():
    """Clearing ``approved_by`` is indistinguishable from never having approved.

    That is the whole reason the revoked fact has to be STORED: the two rows of
    the table it would collapse into each other have opposite behaviour —
    never-approved accepts documents unvalidated, revoked refuses them."""
    never = {}
    approved = {"approved_by": "a@example.com"}
    un_approved = {}  # what a plain un-approval leaves behind
    revoked = {"approved_by": "a@example.com", "revoked_by": "a@example.com"}

    assert approval_state(never) == UNAPPROVED
    assert approval_state(approved) == APPROVED
    assert approval_state(un_approved) == approval_state(never), (
        "a plain un-approval is BYTE-IDENTICAL to never having approved — "
        "which is why it cannot mean 'revoked'"
    )
    assert approval_state(revoked) == REVOKED, (
        "revocation must survive as a fact of its own, beside the approval it "
        "withdraws — the audit keeps who conferred effect in the first place"
    )


def test_a_revoker_that_names_no_one_does_not_revoke():
    """Same rule the approval gate already applies to ``approved_by``: a truthy
    non-string names nobody. A gate that accepted ``revoked_by: true`` would let
    a malformed document silently invalidate a workspace's data."""
    for value in ({"name": "Jane"}, True, 7, "", "   "):
        assert approval_state({"approved_by": "a@example.com", "revoked_by": value}) == (
            APPROVED
        ), f"revoked_by={value!r} names no one and must not revoke"


# ── the three rows of the table ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_never_approved_kind_still_accepts_anything(store):
    """The PERMISSIVE row, pinned as a control.

    It is not a bug being preserved — it is the measured behaviour that makes
    revocation-as-un-approval a loosening, and the tests above are only
    meaningful while it stays true."""
    k = _kernel(store)
    await _write_kinddef(k, "Widget", approved=False)

    async def accepts_anything(fresh):
        assert fresh.kind_port_for("Widget", scope=_SCOPE) is None
        await _write_doc(fresh, "Widget", "w-anything", {"size": 42, "nope": True})
    await _on_fresh_kernel(store, accepts_anything)


@pytest.mark.asyncio
async def test_an_approved_kind_validates_and_a_revoked_one_refuses_even_conforming(
    store,
):
    """A revoked Kind is not a stricter schema — it is a withdrawn Kind.

    So the document that the APPROVED Kind happily accepted is refused too.
    Asserting only on a violating document would have let an implementation
    that merely tightened validation pass."""
    conforming = {"size": "large"}

    k = _kernel(store)
    await _write_kinddef(k, "Widget", approved=True)

    async def accepts_conforming(fresh):
        await _write_doc(fresh, "Widget", "w-ok", conforming)
    await _on_fresh_kernel(store, accepts_conforming)

    await _revoke(k, "Widget")

    async def refuses_conforming(fresh):
        with pytest.raises(RevokedKindWrite) as exc:
            await _write_doc(fresh, "Widget", "w-ok-2", conforming)
        assert "shape" in str(exc.value), (
            "the refusal must say the document's shape is not the subject — "
            "an author told 'validation failed' will go and edit a document "
            "that can never pass"
        )
    await _on_fresh_kernel(store, refuses_conforming)


@pytest.mark.asyncio
async def test_the_refusal_ignores_the_write_validation_knob(store, monkeypatch):
    """``DNA_WRITE_VALIDATION=off`` exists so an operator can bulk-load legacy
    data past a SHAPE check. A workspace's decision to withdraw its own Kind is
    not a shape check, and an environment variable must not overrule it."""
    k = _kernel(store)
    await _write_kinddef(k, "Widget", approved=True)
    await _revoke(k, "Widget")
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")

    async def still_refuses(fresh):
        with pytest.raises(RevokedKindWrite):
            await _write_doc(fresh, "Widget", "w", {"size": "large"})
    await _on_fresh_kernel(store, still_refuses)


# ── what a READ returns ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_existing_document_reads_back_marked_never_erased(store):
    """Decision 1: the read returns THE DOCUMENT, marked invalid.

    Never an error, never ``None``, never a deletion — erasing it or refusing
    the read would destroy the ability to audit what existed, and the data did
    nothing wrong: the workspace changed its mind."""
    k = await _seed(store)
    await _write_doc(k, "Widget", "w1", {"size": "large"})
    await _revoke(k, "Widget")

    async def reads_marked(fresh):
        raw = await fresh.get_document(_SCOPE, "Widget", "w1")
        assert raw is not None, "the document must still be readable"
        assert raw["spec"]["size"] == "large", (
            "the document's own content is untouched — revocation invalidates, "
            "it does not edit or delete"
        )
        assert is_marked_invalid(raw), "the read must MARK it invalid"
        assert raw[STATUS_KEY]["reason"] == "kind_revoked"
        return raw
    marked = await _on_fresh_kernel(store, reads_marked)
    assert "revoked" in marked[STATUS_KEY]["message"].lower()


@pytest.mark.asyncio
async def test_the_document_shape_carries_the_same_verdict(store):
    """The three read shapes must not disagree.

    ``get_document``/``query`` hand back raw dicts, the sync wrappers and an MI
    hand back ``Document``. A face reading one and a tool reading the other
    would otherwise reach opposite conclusions about the same document."""
    k = await _seed(store)
    await _write_doc(k, "Widget", "w1", {"size": "large"})
    await _revoke(k, "Widget")

    async def reads_marked(fresh):
        # Deliberately the ManifestInstance path, NOT ``kernel.query``: the MI
        # builder parses raw documents straight off the source, so this proves
        # the ``Document`` shape marks them ITSELF. Feeding it rows from
        # ``kernel.query`` would have re-asserted the raw-dict marking and
        # passed with the Document-side marking deleted.
        mi = await fresh.instance_async(_SCOPE)
        docs = [d for d in mi.documents if d.kind == "Widget"]
        assert docs, "the documents must still be there to be judged"
        assert all(not d.is_valid for d in docs)
        assert all(d.status["reason"] == "kind_revoked" for d in docs)
        assert all(d.spec["size"] == "large" for d in docs), (
            "marked, not edited"
        )
    await _on_fresh_kernel(store, reads_marked)


# ── what an invalid document does in a QUERY ──────────────────────────────


@pytest.mark.asyncio
async def test_invalid_documents_appear_in_a_query_marked_and_never_vanish(store):
    """The sharpest of the three questions, answered: they APPEAR, marked.

    If they vanished, revoking would become a way to hide data without deleting
    it. They do not: the same rows come back, in the same number, carrying the
    verdict. The consequence is real and accepted — every listing surface has
    to learn to render the mark — but a surface that does not learn simply shows
    what it showed yesterday, which is strictly better than a mechanism that can
    disappear documents."""
    k = await _seed(store)
    for i in range(3):
        await _write_doc(k, "Widget", f"w{i}", {"size": "large"})

    async def count_while_approved(fresh):
        return [r async for r in fresh.query(_SCOPE, "Widget")]
    before = await _on_fresh_kernel(store, count_while_approved)
    assert len(before) == 3
    assert not any(is_marked_invalid(r) for r in before)

    await _revoke(k, "Widget")

    async def count_after_revocation(fresh):
        rows = [r async for r in fresh.query(_SCOPE, "Widget")]
        total = await fresh.count(_SCOPE, "Widget")
        return rows, total
    after, total = await _on_fresh_kernel(store, count_after_revocation)

    assert len(after) == len(before), (
        "revocation must not remove rows from a query — hiding data without "
        "deleting it is the one outcome worse than no revocation at all"
    )
    assert all(is_marked_invalid(r) for r in after), (
        "every row must carry the verdict; an unmarked row is a listing that "
        "silently claims nothing happened"
    )
    assert total["total"] == len(after), (
        "count() is a separate push-down to the source and cannot see the "
        "registry — so a query that DROPPED rows would disagree with it, which "
        "is why 'vanish' is not honestly expressible on this path"
    )


# ── reversible, and never a stamp ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_re_approving_restores_validity(store):
    """Decision 2: reversible. Validity follows the Kind's CURRENT state."""
    k = await _seed(store)
    await _write_doc(k, "Widget", "w1", {"size": "large"})
    await _revoke(k, "Widget")

    async def is_invalid(fresh):
        return is_marked_invalid(await fresh.get_document(_SCOPE, "Widget", "w1"))
    assert await _on_fresh_kernel(store, is_invalid) is True

    # Re-approve: the revocation markers are cleared, nothing else changes.
    await _write_kinddef(k, "Widget", approved=True)

    async def is_valid_again(fresh):
        raw = await fresh.get_document(_SCOPE, "Widget", "w1")
        assert not is_marked_invalid(raw), (
            "re-approving restores validity for the documents that already "
            "existed — there is nothing to migrate, because the mark was never "
            "written down"
        )
        # And the Kind governs again: conforming accepted, violating refused.
        await _write_doc(fresh, "Widget", "w2", {"size": "small"})
        with pytest.raises(SpecValidationError):
            await _write_doc(fresh, "Widget", "w3", {"size": 42})
    await _on_fresh_kernel(store, is_valid_again)


@pytest.mark.asyncio
async def test_the_mark_is_derived_and_never_reaches_the_store(store):
    """The mark must not become a stamp on the document.

    The application layer read-modify-writes constantly (``{**raw, "spec":
    spec}``), so a marked read handed straight back to ``write_document`` is the
    ordinary case, not an abuse. If it persisted, re-approval would leave stale
    ``invalid`` stamps behind and Decision 2 would be false."""
    k = await _seed(store)
    await _write_doc(k, "Widget", "w1", {"size": "large"})
    await _revoke(k, "Widget")

    # A round trip through the ONE Kind that is still writable while Widget is
    # revoked: read the marked document, hand it back to a write of its own
    # KindDefinition-approved successor. Done on the Widget doc itself would be
    # refused (it is a revoked Kind), so the strip is proved on a Kind that is
    # not — the strip is generic and must not depend on the revocation.
    async def round_trip(fresh):
        marked = await fresh.get_document(_SCOPE, "Widget", "w1")
        assert is_marked_invalid(marked)
        kd = await fresh.get_document(_SCOPE, "KindDefinition", "widget")
        await fresh.write_document(
            _SCOPE, "KindDefinition", "widget", {**kd, STATUS_KEY: marked[STATUS_KEY]},
        )
    await _on_fresh_kernel(store, round_trip)

    on_disk = [
        p.read_text(encoding="utf-8")
        for p in store.rglob("*.yaml")
    ]
    assert not any(STATUS_KEY + ":" in text for text in on_disk), (
        "a derived status reached the STORE — a later read would replay it as "
        "fact even after the Kind was approved again"
    )

    # And behaviourally: approve again, and nothing stale survives.
    k2 = _kernel(store)
    await _write_kinddef(k2, "Widget", approved=True)

    async def nothing_stale(fresh):
        assert not is_marked_invalid(
            await fresh.get_document(_SCOPE, "Widget", "w1")
        )
    await _on_fresh_kernel(store, nothing_stale)


# ── reach: the same kernel, and the audit trail ───────────────────────────


@pytest.mark.asyncio
async def test_revocation_reaches_an_already_registered_kind_without_a_restart(store):
    """The issue's own trigger: the registry is per-kernel and outlives an
    ``instance_async`` call, so an approval cleared on a live process used to do
    nothing at all until a restart.

    It reaches it now, and by the mechanism that was already there rather than a
    new one: the revocation markers live in ``spec``, so they change the
    descriptor digest, and the "different digest → replace the port" branch
    swaps the approved port for the revoked one on the next load."""
    k = _kernel(store)
    await _write_kinddef(k, "Widget", approved=True)
    await k.instance_async(_SCOPE)
    assert k.kind_port_for("Widget", scope=_SCOPE) is not None

    await _revoke(k, "Widget")
    await k.instance_async(_SCOPE)

    port = k.kind_port_for("Widget", scope=_SCOPE)
    assert port is not None and getattr(port, "__revoked__", False) is True, (
        "the SAME kernel must see the revocation — a portal button that needs "
        "a process restart to take effect is not an undo"
    )
    with pytest.raises(RevokedKindWrite):
        await _write_doc(k, "Widget", "w-live", {"size": "large"})


@pytest.mark.asyncio
async def test_the_revocation_is_logged_loudly(store, caplog):
    """A scope whose documents have just been marked invalid is not a quiet
    resting state — it is the thing an operator reading logs needs to find."""
    k = _kernel(store)
    await _write_kinddef(k, "Widget", approved=True)
    await _revoke(k, "Widget")
    caplog.clear()

    async def probe(fresh):
        return None
    with caplog.at_level("WARNING"):
        await _on_fresh_kernel(store, probe)
    revoked_lines = [
        r.getMessage() for r in caplog.records
        if r.levelname == "WARNING" and "REVOKED" in r.getMessage()
    ]
    assert any("Widget" in line for line in revoked_lines), (
        "the revocation must name the Kind at WARNING — an operator reading "
        f"logs has to find out why a scope's documents went invalid; saw: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_a_revoked_kinds_documents_can_still_be_deleted(store):
    """Refusing deletes would trap exactly the documents a workspace may now
    want to clear out. Revocation refuses to destroy anything on its own; it
    does not also forbid the owner from doing so deliberately."""
    k = await _seed(store)
    await _write_doc(k, "Widget", "w1", {"size": "large"})
    await _revoke(k, "Widget")

    async def deletes(fresh):
        await fresh.delete_document(_SCOPE, "Widget", "w1")
        assert await fresh.get_document(_SCOPE, "Widget", "w1") is None
    await _on_fresh_kernel(store, deletes)
