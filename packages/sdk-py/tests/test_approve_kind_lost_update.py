"""i-083 — approval must not silently overwrite an edit it never read.

``approve_kind_impl`` reads the authored ``KindDefinition``, merges two keys
(``approved_by``/``approved_at``) into its spec and writes ``{**raw, "spec":
spec}``. Read-modify-write with nothing asserting that the document it read is
still the document it is about to replace.

**The measured scenario**, and the reason a plain read-then-write is not enough:

1. a reviewer opens the Kind on replica **B** — which warms B's 60-second
   granular document cache (``Kernel._GRANULAR_DOC_TTL``) with **v1**;
2. the author edits the Kind to **v2** on replica **A**. The write invalidates
   A's caches. It does not invalidate B's;
3. the reviewer approves on **B**. The approval reads **v1 from B's cache**,
   stamps the approver onto it and writes it back.

The edit is gone, and v1 is stamped approved — the shape a human signed is not
the shape that is now in effect.

Note what that rules out: a guard implemented in the application layer as
"re-read, compare, write" would re-read through the SAME stale cache, find v1
matching v1, and let the clobber through. The guarantee has to be evaluated
where the truth is — the adapter — which is why ``if_match`` had to be threaded
onto ``kernel.write_document`` rather than bolted onto the approval function.

Both replicas share one filesystem store, each with its OWN ``Kernel`` (and so
its own cache) — which is exactly what two container replicas over one Postgres
are.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.kind_authoring import approve_kind_impl, author_kind_impl
from dna.application.live import LiveDna
from dna.kernel import Kernel
from dna.kernel.errors import StaleDocumentWrite

_SCOPE = "board"
_TENANT = "ws-acme"
_KIND_DOC = "KindDefinition"

_V1 = {"type": "object", "properties": {"titulo": {"type": "string"}}}
_V2 = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}, "valor": {"type": "number"}},
    "required": ["valor"],
}


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def store(tmp_path: Path) -> Path:
    """One store on disk — the shared Postgres/filesystem both replicas see."""
    base = tmp_path / ".dna"
    _write_yaml(base / _SCOPE / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    # The ``_lib`` registry scope — authoring READS the KindNamespace registry
    # before it mints, and a filesystem source raises for a missing directory.
    _write_yaml(base / "_lib" / "manifest.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": "_lib"}, "spec": {},
    })
    return base


def _replica(base: Path) -> LiveDna:
    """A replica: its own Kernel, hence its OWN granular document cache, over
    the shared store. Two of these is the whole fixture."""
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None)


async def _author(live: LiveDna, schema: dict, *, now: str) -> dict[str, Any]:
    return await author_kind_impl(
        live, kind="Deal", schema=schema, tenant=_TENANT, now=now,
        actor="author@acme.example",
    )


def _stored(base: Path, doc_name: str) -> dict[str, Any]:
    """The document as it sits ON DISK — read past every cache, because the
    whole question is what the STORE holds. A KindDefinition is a bundle: a
    directory holding ``KIND.yaml``."""
    return yaml.safe_load(
        (base / _SCOPE / "kinds" / doc_name / "KIND.yaml").read_text()
    )


@pytest.mark.asyncio
async def test_approving_a_document_that_changed_since_it_was_read_is_refused(
    store: Path,
) -> None:
    """THE regression, replica for replica.

    What must go red without the guard: ``approve_kind_impl`` returns happily,
    ``pytest.raises`` reports DID NOT RAISE — and the stored schema is v1 with
    an ``approved_by`` on it, i.e. the edit is measurably gone.
    """
    replica_a = _replica(store)
    replica_b = _replica(store)

    authored = await _author(replica_a, _V1, now="2026-07-28T00:00:00+00:00")
    doc_name = authored["name"]

    # 1. the reviewer OPENS the Kind on B — warming B's 60s document cache.
    warmed = await replica_b.kernel.get_document(_SCOPE, _KIND_DOC, doc_name)
    assert warmed["spec"]["schema"] == _V1, (
        "fixture broken: B did not read the authored v1"
    )

    # 2. the author EDITS to v2 on A. This invalidates A's caches, never B's.
    await _author(replica_a, _V2, now="2026-07-28T00:01:00+00:00")

    # The store now holds v2 …
    on_disk = _stored(store, doc_name)
    assert on_disk["spec"]["schema"] == _V2, "fixture broken: the edit did not land"
    # … while B still answers v1 from its cache. This is the stale read the
    # approval is about to build its write on; if this ever stops being true the
    # test below would pass for the wrong reason.
    stale = await replica_b.kernel.get_document(_SCOPE, _KIND_DOC, doc_name)
    assert stale["spec"]["schema"] == _V1, (
        "fixture broken: B's cache no longer serves the stale read this "
        "scenario is built on — the refusal below would prove nothing"
    )

    # 3. the reviewer APPROVES on B, off the stale read.
    with pytest.raises(StaleDocumentWrite) as excinfo:
        await approve_kind_impl(
            replica_b, kind="Deal", tenant=_TENANT,
            actor="reviewer@acme.example", now="2026-07-28T00:02:00+00:00",
        )

    # The refusal has to be actionable: it names the document and says the
    # document moved, so the caller knows to re-read rather than to retry.
    assert doc_name in str(excinfo.value)

    # And it wrote NOTHING: the edit survives, and no approval was stamped onto
    # a shape nobody approved.
    after = _stored(store, doc_name)
    assert after["spec"]["schema"] == _V2, "the refused approval clobbered the edit"
    assert not after["spec"].get("approved_by"), (
        "the refused approval stamped an approver anyway"
    )


@pytest.mark.asyncio
async def test_approving_the_document_you_actually_read_still_works(
    store: Path,
) -> None:
    """The guard must not turn approval into a coin flip. Same replica, no
    intervening edit: the approval goes through and stamps the approver.

    Without this, a guard that refused unconditionally would pass the test
    above."""
    live = _replica(store)
    authored = await _author(live, _V1, now="2026-07-28T00:00:00+00:00")

    out = await approve_kind_impl(
        live, kind="Deal", tenant=_TENANT, actor="reviewer@acme.example",
        now="2026-07-28T00:02:00+00:00",
    )
    assert out["approved"] is True
    assert out["approved_by"] == "reviewer@acme.example"

    stored = _stored(store, authored["name"])
    assert stored["spec"]["approved_by"] == "reviewer@acme.example"
    assert stored["spec"]["approved_at"] == "2026-07-28T00:02:00+00:00"
    # The proposal half of the audit is preserved — approval MERGES.
    assert stored["spec"]["proposed_by"] == "author@acme.example"
    assert stored["spec"]["schema"] == _V1


@pytest.mark.asyncio
async def test_re_approving_after_an_edit_works_once_the_reviewer_re_reads(
    store: Path,
) -> None:
    """The refusal is recoverable, not a dead end — the documented remedy is
    "re-read and retry", so it has to actually work.

    A replica that re-reads FRESH (cache dropped, as a new request on a cold
    replica would) sees v2 and its approval lands on v2."""
    replica_a = _replica(store)
    replica_b = _replica(store)

    authored = await _author(replica_a, _V1, now="2026-07-28T00:00:00+00:00")
    await replica_b.kernel.get_document(_SCOPE, _KIND_DOC, authored["name"])
    await _author(replica_a, _V2, now="2026-07-28T00:01:00+00:00")

    with pytest.raises(StaleDocumentWrite):
        await approve_kind_impl(
            replica_b, kind="Deal", tenant=_TENANT, actor="rev@acme.example",
            now="2026-07-28T00:02:00+00:00",
        )

    # The reviewer re-reads on a replica that never cached v1, and approves.
    replica_c = _replica(store)
    out = await approve_kind_impl(
        replica_c, kind="Deal", tenant=_TENANT, actor="rev@acme.example",
        now="2026-07-28T00:03:00+00:00",
    )
    assert out["approved"] is True

    stored = _stored(store, authored["name"])
    assert stored["spec"]["schema"] == _V2, (
        "the retry approved the stale shape — the whole point is that the "
        "approval lands on the shape the reviewer saw"
    )
    assert stored["spec"]["approved_by"] == "rev@acme.example"
