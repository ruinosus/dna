"""Item 2 — the faces could create and update every Kind, and delete nothing.

``kernel.delete_instance`` has always existed; ``dna doc delete`` and four narrow
REST routes use it. The MCP face had NO delete at all, so the only way to undo a
mistaken generic write was a human with database access.

Adding it honestly means two things beyond the call: deciding what may never be
deleted (and being able to say why), and REPORTING that decision per Kind so a
refusal is visible before it is attempted — ``list_kinds`` already does exactly
that for writes with ``writable`` / ``write_refusal``.
"""
from __future__ import annotations

import pytest

from dna.application import instances as D
from dna.application.live import LiveDna
from dna.kernel import Kernel

_SCOPE = "probe"


# ── what may never be deleted, and why ──────────────────────────────────────


def test_bootstrap_kinds_are_never_deletable():
    k = Kernel.auto()
    for kind in ("Genome", "LayerPolicy", "KindDefinition"):
        port = k.kind_port_for(kind)
        assert port is not None, kind
        refusal = D.delete_refusal(port)
        assert refusal is not None, f"{kind} must not be generically deletable"
        assert "BOOTSTRAP" in refusal


def test_append_only_records_are_never_deletable():
    k = Kernel.auto()
    for kind in ("AuditLog", "Evidence", "WorkflowEvent"):
        port = k.kind_port_for(kind)
        assert port is not None, kind
        refusal = D.delete_refusal(port)
        assert refusal is not None, f"{kind} is the evidence; it must not vanish"
        assert "APPEND-ONLY" in refusal


def test_ordinary_kinds_are_deletable():
    """The default is deletable, and deliberately so: a delete the owner cannot
    perform is a delete they will perform by hand against the database."""
    k = Kernel.auto()
    for kind in ("Story", "Skill", "Engram", "Agent"):
        port = k.kind_port_for(kind)
        assert port is not None, kind
        assert D.delete_refusal(port) is None, kind


def test_the_refusals_are_derived_not_listed():
    """Both categories come from a declaration on the Kind (``is_overlayable``
    and the ``record.append-only`` trait), so a Kind that arrives later — a
    tenant-authored one included — is covered on arrival."""
    k = Kernel.auto()
    bootstrap = {p.kind for p in k.kind_ports() if D.is_bootstrap_kind(p)}
    append_only = k.kinds_with_trait(D.TRAIT_APPEND_ONLY)
    refused = {p.kind for p in k.kind_ports() if D.delete_refusal(p) is not None}
    assert refused == bootstrap | set(append_only)


# ── the catalog reports it BEFORE it is attempted ───────────────────────────


class _Kernel:
    """A fake store keyed the way every real one is — INCLUDING the tenant.

    It used to key on ``(scope, kind, name)`` and take no ``tenant`` kwarg at
    all, which is exactly the coordinate mismatch of i-088: the delete's
    existence check read at a tenant the row was never stored under, and nothing
    in this file could tell, because the fake had no tenant to disagree about. A
    fake blind to a coordinate cannot fail when the code confuses it. The
    end-to-end proof, against the real filesystem and SQL stores, is in
    ``test_delete_document_tenant_coordinates.py``."""

    def __init__(self, real, docs=None):
        self._real = real
        # {(scope, kind, name, tenant): raw}. The Kinds exercised here are
        # GLOBAL, so their tenant is None — which is what ``_write_tenant``
        # resolves for them, and therefore where the checks must read.
        self.docs = {
            (k if len(k) == 4 else (*k, None)): v
            for k, v in dict(docs or {}).items()
        }
        self.deleted: list[tuple] = []

    def kind_ports(self):
        return self._real.kind_ports()

    def kind_port_for(self, kind, **kw):
        return self._real.kind_port_for(kind, **kw)

    def kinds_with_trait(self, trait):
        return self._real.kinds_with_trait(trait)

    async def get_instance(self, scope, kind, name, *, tenant=None):
        return self.docs.get((scope, kind, name, tenant))

    async def delete_instance(self, scope, kind, name, **kw):
        self.deleted.append((scope, kind, name, kw))
        self.docs.pop((scope, kind, name, kw.get("tenant")), None)


def _live(kernel):
    return LiveDna(base_scope=_SCOPE, kernel=kernel, provider=None)


@pytest.mark.asyncio
async def test_list_kinds_reports_deletable_and_the_reason():
    out = await D.list_kinds_impl(_live(_Kernel(Kernel.auto())))
    by_kind = {e["kind"]: e for e in out["kinds"]}
    assert by_kind["Genome"]["deletable"] is False
    assert by_kind["Genome"]["delete_refusal"]
    assert by_kind["AuditLog"]["deletable"] is False
    assert by_kind["Story"]["deletable"] is True
    assert by_kind["Story"]["delete_refusal"] is None
    # ...and delete is REPORTED SEPARATELY from write, because the two do not
    # coincide: an AuditLog is writable and never deletable.
    assert by_kind["AuditLog"]["writable"] is True


@pytest.mark.asyncio
async def test_list_kinds_reports_the_traits_a_kind_declares():
    out = await D.list_kinds_impl(_live(_Kernel(Kernel.auto())))
    by_kind = {e["kind"]: e for e in out["kinds"]}
    assert "sdlc.work-item" in by_kind["Story"]["traits"]
    assert by_kind["AuditLog"]["traits"] == ["record.append-only"]


# ── the delete itself ───────────────────────────────────────────────────────


_STORY_AV = "github.com/ruinosus/dna/sdlc/v1"


def _story_doc():
    return {"apiVersion": _STORY_AV, "kind": "Story",
            "metadata": {"name": "s-x"}, "spec": {"title": "T", "status": "todo"}}


@pytest.mark.asyncio
async def test_delete_removes_and_pins_the_kind():
    k = _Kernel(Kernel.auto(), {(_SCOPE, "Story", "s-x"): _story_doc()})
    out = await D.delete_instance_impl(
        _live(k), kind="Story", name="s-x", api_version=_STORY_AV)
    assert out["deleted"] is True
    scope, kind, name, kwargs = k.deleted[0]
    assert (scope, kind, name) == (_SCOPE, "Story", "s-x")
    assert kwargs["api_version"] == _STORY_AV, (
        "the delete must PIN the Kind: a bare name can resolve to two ports "
        "once two workspaces each declare a Kind of the same name"
    )


@pytest.mark.asyncio
async def test_deleting_a_refused_kind_raises_and_writes_nothing():
    k = _Kernel(Kernel.auto(), {
        (_SCOPE, "AuditLog", "a-1"): {
            "apiVersion": "github.com/ruinosus/dna/audit/v1", "kind": "AuditLog",
            "metadata": {"name": "a-1"}, "spec": {},
        },
    })
    with pytest.raises(D.DeleteRefused, match="APPEND-ONLY"):
        await D.delete_instance_impl(
            _live(k), kind="AuditLog", name="a-1",
            api_version="github.com/ruinosus/dna/audit/v1")
    assert k.deleted == []


@pytest.mark.asyncio
async def test_deleting_an_absent_document_is_an_error_not_a_quiet_success():
    """Reporting success for a delete that did nothing is how a caller convinces
    itself something is gone."""
    k = _Kernel(Kernel.auto())
    with pytest.raises(D.UnknownInstanceError, match="nothing to delete"):
        await D.delete_instance_impl(
            _live(k), kind="Story", name="s-nope", api_version=_STORY_AV)
    assert k.deleted == []


@pytest.mark.asyncio
async def test_if_match_refuses_a_stale_delete_and_deletes_nothing():
    """A write that races loses one edit; a delete that races destroys a
    instance its author never saw."""
    k = _Kernel(Kernel.auto(), {(_SCOPE, "Story", "s-x"): _story_doc()})
    with pytest.raises(D.ConcurrentWriteError, match="changed since you read it"):
        await D.delete_instance_impl(
            _live(k), kind="Story", name="s-x", api_version=_STORY_AV,
            if_match="sha256:stale")
    assert k.deleted == []


@pytest.mark.asyncio
async def test_a_matching_if_match_goes_through():
    doc = _story_doc()
    k = _Kernel(Kernel.auto(), {(_SCOPE, "Story", "s-x"): doc})
    etag = D.spec_etag(doc["spec"])
    out = await D.delete_instance_impl(
        _live(k), kind="Story", name="s-x", api_version=_STORY_AV, if_match=etag)
    assert out["deleted"] is True
