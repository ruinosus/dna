"""The revocation DOOR — i-085's third state, reachable and reversible.

The kernel mechanism is tested in ``test_kind_revocation.py``; this file is
about the act. Three things it has to get right, each of which is a way the
mechanism could be true and the feature still broken:

* **an EDIT must not un-revoke.** The authoring door rebuilds the spec from
  scratch and persists it, so anything it does not carry forward is dropped —
  and dropping the revocation would return the Kind to *never approved*, where
  documents are accepted with no validation at all. That is the same loosening
  the whole issue is about, arriving through a different door;
* **approving again must clear it**, or "reversible" is a claim with no
  mechanism;
* **the audit must report the state**, or a reviewer looking at the roster
  cannot tell a revoked Kind from one nobody ever approved — which are the two
  rows of the table with opposite behaviour.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.kind_authoring import (
    AuthoredKindNotFound,
    approve_kind_impl,
    author_kind_impl,
    get_authored_kind_impl,
    list_authored_kinds_impl,
    revoke_kind_impl,
)
from dna.application.live import LiveDna
from dna.kernel import Kernel
from dna.kernel.errors import StaleDocumentWrite
from dna.kernel.kinds.approval import APPROVED, REVOKED, UNAPPROVED, approval_state

_SCOPE = "board"
_TENANT = "ws-acme"
_SCHEMA = {"type": "object", "properties": {"titulo": {"type": "string"}}}


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    base = tmp_path / ".dna"
    _write_yaml(base / _SCOPE / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    _write_yaml(base / "_lib" / "manifest.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "_lib"}, "spec": {},
    })
    return base


def _replica(base: Path) -> LiveDna:
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None)


def _stored_spec(base: Path, doc_name: str) -> dict[str, Any]:
    """The spec as it sits ON DISK — read past every cache, because the whole
    question is what the STORE holds."""
    raw = yaml.safe_load(
        (base / _SCOPE / "kinds" / doc_name / "KIND.yaml").read_text()
    )
    return raw.get("spec") or {}


async def _authored(live: LiveDna, *, now: str = "2026-07-28T10:00:00Z") -> str:
    res = await author_kind_impl(
        live, kind="Deal", schema=_SCHEMA, tenant=_TENANT, now=now,
        actor="author@acme.example",
    )
    return res["name"]


# ── the act ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoking_stamps_the_revoker_and_keeps_the_approval(store: Path):
    """The audit must keep who conferred effect in the FIRST place.

    Revoking is a third act, not an erasure of the second: a record that says
    "revoked by X" and nothing else has lost the fact that somebody approved
    this Kind and it governed real documents for a while."""
    live = _replica(store)
    name = await _authored(live)
    await approve_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T11:00:00Z",
    )

    out = await revoke_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer2@acme.example",
        now="2026-07-28T12:00:00Z",
    )

    assert out["revoked"] is True
    assert out["revoked_by"] == "reviewer2@acme.example"
    spec = _stored_spec(store, name)
    assert spec["revoked_by"] == "reviewer2@acme.example"
    assert spec["revoked_at"] == "2026-07-28T12:00:00Z"
    assert spec["approved_by"] == "reviewer@acme.example", (
        "the approval must survive the revocation — it is the record of an act "
        "that really happened, and the audit is the point"
    )
    assert approval_state(spec) == REVOKED


@pytest.mark.asyncio
async def test_revoking_records_a_verified_identity_or_refuses(store: Path):
    """Same rule as approval: an act nobody signed is not the act."""
    live = _replica(store)
    await _authored(live)
    with pytest.raises(ValueError, match="revocation"):
        await revoke_kind_impl(
            live, kind="Deal", tenant=_TENANT, actor="   ",
            now="2026-07-28T12:00:00Z",
        )


@pytest.mark.asyncio
async def test_revoking_a_kind_the_caller_does_not_own_is_a_404(store: Path):
    """Inherited from the approval door, deliberately: "it exists but is not
    yours" is a probe for what the neighbours are authoring."""
    live = _replica(store)
    await _authored(live)
    with pytest.raises(AuthoredKindNotFound):
        await revoke_kind_impl(
            live, kind="Deal", tenant="ws-other", actor="x@other.example",
            now="2026-07-28T12:00:00Z",
        )


@pytest.mark.asyncio
async def test_revoking_a_kind_nobody_authored_is_a_404_and_creates_nothing(
    store: Path,
):
    """A revocation door that CREATED the document it was asked to revoke would
    be an authoring door with a revocation marker on it."""
    live = _replica(store)
    with pytest.raises(AuthoredKindNotFound):
        await revoke_kind_impl(
            live, kind="Ghost", tenant=_TENANT, actor="r@acme.example",
            now="2026-07-28T12:00:00Z",
        )
    assert not list((store / _SCOPE / "kinds").glob("*")) or not any(
        p.name.endswith("Ghost") for p in (store / _SCOPE / "kinds").glob("*")
    )


# ── the loosening trap, through the AUTHORING door ────────────────────────


@pytest.mark.asyncio
async def test_an_edit_cannot_un_revoke_a_kind(store: Path):
    """The trap this issue is about, arriving through a different door.

    The authoring door rebuilds the spec from scratch and PERSISTS it, and it
    deliberately drops ``approved_by`` — an edit changes the shape a human
    signed, so the approval no longer applies. Dropping ``revoked_by`` the same
    way looks symmetric and is the loosening all over again: the Kind would land
    in *never approved*, where documents are accepted with NO validation. So an
    edit withdraws the APPROVAL and carries the REVOCATION forward. Only the
    approval door can undo a revocation.
    """
    live = _replica(store)
    name = await _authored(live)
    await approve_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T11:00:00Z",
    )
    await revoke_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T12:00:00Z",
    )

    # The author edits the Kind — a brand new shape, a fresh spec.
    await author_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="author@acme.example",
        now="2026-07-28T13:00:00Z",
        schema={"type": "object", "properties": {"valor": {"type": "number"}}},
    )

    spec = _stored_spec(store, name)
    assert not spec.get("approved_by"), (
        "an edit still withdraws the approval — the shape a human signed is "
        "gone"
    )
    assert approval_state(spec) == REVOKED, (
        "an edit must NOT un-revoke: landing in 'never approved' would make "
        "the Kind accept documents with no validation at all, which is the "
        "exact loosening revocation exists to prevent"
    )
    assert spec["revoked_by"] == "reviewer@acme.example"


# ── reversible ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approving_again_clears_the_revocation(store: Path):
    """Decision 2, at the door. One act, no migration, no stale markers."""
    live = _replica(store)
    name = await _authored(live)
    await approve_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T11:00:00Z",
    )
    await revoke_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T12:00:00Z",
    )
    assert approval_state(_stored_spec(store, name)) == REVOKED

    await approve_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T14:00:00Z",
    )

    spec = _stored_spec(store, name)
    assert approval_state(spec) == APPROVED
    assert not spec.get("revoked_by") and not spec.get("revoked_at"), (
        "the revocation markers must be CLEARED, not merely out-ranked — a "
        "leftover revoked_by is a fact about the present that is no longer true"
    )


# ── the guarded write ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoking_a_document_that_changed_since_it_was_read_is_refused(
    store: Path,
):
    """The same lost-update guard the approval carries (i-083).

    Revocation is a read-modify-write too — it reads the document, merges two
    keys and persists ``{**raw, "spec": spec}`` — so everything it did not read,
    it overwrites. Unguarded, revoking on a replica holding a stale cache would
    resurrect the shape that replica last saw AND mark it revoked.
    """
    a, b = _replica(store), _replica(store)
    await _authored(a)
    # B warms its cache with v1.
    await get_authored_kind_impl(b, kind="Deal", tenant=_TENANT)
    # A edits to v2 — invalidating A's caches, not B's.
    await author_kind_impl(
        a, kind="Deal", tenant=_TENANT, actor="author@acme.example",
        now="2026-07-28T13:00:00Z",
        schema={"type": "object", "properties": {"valor": {"type": "number"}}},
    )
    with pytest.raises(StaleDocumentWrite):
        await revoke_kind_impl(
            b, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
            now="2026-07-28T14:00:00Z",
        )


# ── the audit reports the state ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_audit_tells_revoked_apart_from_never_approved(store: Path):
    """The two rows a reviewer must never confuse.

    ``approved: false`` is true of both, and they behave in opposite ways — one
    accepts documents unvalidated, the other refuses them. A roster that reports
    only the boolean is a roster that hides the difference."""
    live = _replica(store)
    await _authored(live)

    roster = await list_authored_kinds_impl(live, tenant=_TENANT)
    row = next(r for r in roster["kinds"] if r["kind"] == "Deal")
    assert row["state"] == UNAPPROVED and row["revoked_by"] is None

    await approve_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T11:00:00Z",
    )
    await revoke_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer2@acme.example",
        now="2026-07-28T12:00:00Z",
    )

    roster = await list_authored_kinds_impl(live, tenant=_TENANT)
    row = next(r for r in roster["kinds"] if r["kind"] == "Deal")
    assert row["state"] == REVOKED, (
        "the roster must name the third state — 'not approved' collapses it "
        "into the permissive row"
    )
    assert row["revoked_by"] == "reviewer2@acme.example"
    assert row["revoked_at"] == "2026-07-28T12:00:00Z"
    assert row["approved_by"] == "reviewer@acme.example"

    # The detail route is the SAME projection plus schema/traits — so it cannot
    # drift into a second vocabulary for the same document.
    detail = await get_authored_kind_impl(live, kind="Deal", tenant=_TENANT)
    assert detail["state"] == REVOKED
    assert detail["revoked_by"] == "reviewer2@acme.example"
