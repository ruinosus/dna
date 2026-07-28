"""i-081 — a store-loaded Kind applies ONLY to the scope whose store declared it.

The hole this locks shut: ``load_bootstrap_docs`` decides which
``KindDefinition`` documents are LOADED (by scope), and NOTHING decided which
scope a loaded Kind APPLIES to. The registry key was ``(api_version, kind)``,
with no scope in it, so the first scope to be composed in a process registered
its Kind for the WHOLE process. One long-lived kernel serves every scope
(``with_tenant`` shares the registry by design), so the leak was per-replica and
nondeterministic: scope A's Kind existed in a replica once that replica had
served A.

It was never cosmetic. Registration is what confers **schema enforcement** and
**storage routing**, so a Kind leaking into scope B changed B's behaviour:

* a document of A's Kind, written into B, was validated against A's schema;
* and stored in the container A declared;
* while a genuinely unknown Kind written into B was accepted and stored at the
  scope root — the control that proves the difference is registration.

The second defect had the same root: two scopes each declaring a Kind of the
same name made every BARE-name lookup ambiguous for both, because the registry
compared every port against every other regardless of scope.

Builtin and extension Kinds are registered from code at boot and stay GLOBAL —
they apply everywhere, and ``test_builtin_kinds_stay_global.py`` proves the
whole catalogue still resolves identically.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod
from dna.kernel.protocols import SpecValidationError

_A = "scope-a"
_B = "scope-b"


@pytest.fixture(autouse=True)
def _clear_process_wide_warn_caches():
    # All THREE process-wide warn caches, not two. _GLOBAL_UNAPPROVED_KIND_WARNED
    # arrived later (i-084) and only test_kind_approval_gate.py's copy of this
    # fixture was updated for it, which left every other file here able to burn
    # an approval-warning key that nothing in the file clears. No assertion
    # depends on that today, but it is precisely the shape of coupling that
    # makes a suite order-dependent — and under xdist "which file ran first"
    # stops being a property of the file listing (perf/testes-em-paralelo).
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    yield
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()


def _kinddef(*, namespace: str, kind: str, alias: str, container: str) -> dict:
    """A per-scope ``KindDefinition``, with a schema that REQUIRES ``title`` —
    so "was this document validated against somebody else's Kind?" has a
    yes/no answer.

    APPROVED: an unapproved store-loaded Kind never registers at all, so every
    isolation assertion below would hold for the wrong reason."""
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": alias},
        "spec": {
            "target_api_version": f"{namespace}/v1",
            "target_kind": kind,
            "alias": alias,
            "origin": namespace,
            "storage": {"type": "yaml", "container": container},
            "schema": {
                "type": "object",
                "required": ["title"],
                "properties": {"title": {"type": "string"}},
                "additionalProperties": False,
            },
            "approved_by": "approver@example.com",
        },
    }


def _genome(scope: str) -> dict:
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": {"description": f"fixture scope {scope}"},
    }


def _doc(namespace: str, kind: str, name: str, spec: dict) -> dict:
    return {
        "apiVersion": f"{namespace}/v1",
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


def _write_yaml(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


@pytest.fixture()
def two_scopes(tmp_path: Path):
    """``scope-a`` declares ``Widget``; ``scope-b`` declares nothing."""
    base = tmp_path / ".dna"
    _write_yaml(base / _A / "Genome.yaml", _genome(_A))
    _write_yaml(base / _B / "Genome.yaml", _genome(_B))
    _write_yaml(
        base / _A / "kinds" / "widget.yaml",
        _kinddef(namespace="acme.example", kind="Widget",
                 alias="acme-widget", container="widgets"),
    )
    k = Kernel.auto(FilesystemWritableSource(str(base)))
    return k, base


# ── the leak, end to end ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_scopes_kind_is_invisible_to_another_scope(two_scopes):
    """[2] + [3] of the measurement: composing A registers ``Widget``; the same
    process then composing B must NOT see it."""
    k, _base = two_scopes
    await k.instance_async(_A)
    assert k.kind_port_for("Widget", scope=_A) is not None

    await k.instance_async(_B)
    assert k.kind_port_for("Widget", scope=_B) is None
    # …and A did not lose it by being isolated.
    assert k.kind_port_for("Widget", scope=_A) is not None


@pytest.mark.asyncio
async def test_another_scopes_schema_does_not_validate_this_scopes_write(
    two_scopes,
):
    """[5] against [6]: in B, ``Widget`` is an UNKNOWN Kind — so a spec that
    A's schema would refuse is accepted, exactly like any unregistered Kind."""
    k, _base = two_scopes
    await k.instance_async(_A)
    await k.instance_async(_B)

    invalid_for_a = _doc("acme.example", "Widget", "w1", {"nope": 1})
    # In A this is a violation (title required, additionalProperties false).
    with pytest.raises(SpecValidationError):
        await k.write_document(_A, "Widget", "w1", dict(invalid_for_a))
    # In B it is just an unknown Kind — no foreign schema governs it.
    await k.write_document(_B, "Widget", "w1", dict(invalid_for_a))


@pytest.mark.asyncio
async def test_another_scopes_container_does_not_route_this_scopes_write(
    two_scopes,
):
    """[7]: the document must not land in the container A declared."""
    k, base = two_scopes
    await k.instance_async(_A)
    await k.instance_async(_B)

    await k.write_document(
        _B, "Widget", "w1", _doc("acme.example", "Widget", "w1", {"nope": 1}),
    )
    assert not (base / _B / "widgets" / "w1.yaml").exists()

    await k.write_document(
        _A, "Widget", "wa", _doc("acme.example", "Widget", "wa", {"title": "ok"}),
    )
    assert (base / _A / "widgets" / "wa.yaml").exists()


@pytest.mark.asyncio
async def test_the_owning_scope_keeps_full_behaviour(two_scopes):
    """The isolation must not be achieved by breaking the owner."""
    k, base = two_scopes
    await k.instance_async(_B)  # B first — the leak direction is symmetric
    await k.instance_async(_A)

    await k.write_document(
        _A, "Widget", "wa", _doc("acme.example", "Widget", "wa", {"title": "ok"}),
    )
    assert (base / _A / "widgets" / "wa.yaml").exists()
    with pytest.raises(SpecValidationError):
        await k.write_document(
            _A, "Widget", "bad", _doc("acme.example", "Widget", "bad", {"nope": 1}),
        )


@pytest.mark.asyncio
async def test_the_manifest_instance_of_a_scope_carries_only_its_own_kinds(
    two_scopes,
):
    """The MI is handed a kinds map; a foreign Kind in it is the same leak one
    layer down (plane routing, parse, prompt composition all read it)."""
    k, _base = two_scopes
    await k.instance_async(_A)
    mi_b = await k.instance_async(_B)
    assert ("acme.example/v1", "Widget") not in mi_b._kinds

    mi_a = await k.instance_async(_A)
    assert ("acme.example/v1", "Widget") in mi_a._kinds


# ── the bare-name path between two scopes ───────────────────────────────────


@pytest.fixture()
def two_scopes_same_kind_name(tmp_path: Path):
    """Both scopes declare a Kind called ``Widget``, each in its OWN namespace
    (which is what #244 forces). Today that makes every bare-name lookup
    ambiguous for BOTH."""
    base = tmp_path / ".dna"
    for scope, ns, alias in ((_A, "acme.example", "acme-widget"),
                             (_B, "globex.example", "globex-widget")):
        _write_yaml(base / scope / "Genome.yaml", _genome(scope))
        _write_yaml(
            base / scope / "kinds" / "widget.yaml",
            _kinddef(namespace=ns, kind="Widget", alias=alias,
                     container="widgets"),
        )
    k = Kernel.auto(FilesystemWritableSource(str(base)))
    return k, base


@pytest.mark.asyncio
async def test_a_bare_name_resolves_within_the_callers_own_scope(
    two_scopes_same_kind_name, caplog,
):
    k, _base = two_scopes_same_kind_name
    await k.instance_async(_A)
    await k.instance_async(_B)

    with caplog.at_level(logging.WARNING):
        port_a = k.kind_port_for("Widget", scope=_A)
        port_b = k.kind_port_for("Widget", scope=_B)
    assert port_a is not None and port_a.api_version == "acme.example/v1"
    assert port_b is not None and port_b.api_version == "globex.example/v1"
    # Neither caller is told their own Kind is ambiguous — it is not.
    assert "Ambiguous bare kind-name lookup" not in caplog.text


@pytest.mark.asyncio
async def test_the_generic_document_surface_resolves_within_the_scope(
    two_scopes_same_kind_name,
):
    """``resolve_kind_port`` is the ONE resolution the generic document
    use-cases go through, and it refuses an ambiguous bare name rather than
    guessing. Two workspaces each declaring ``Widget`` used to make it refuse
    BOTH of them — for a name neither shares."""
    from dna.application.documents import AmbiguousKindError, resolve_kind_port

    k, _base = two_scopes_same_kind_name
    await k.instance_async(_A)
    await k.instance_async(_B)

    assert resolve_kind_port(
        k, "Widget", scope=_A,
    ).api_version == "acme.example/v1"
    assert resolve_kind_port(
        k, "Widget", scope=_B,
    ).api_version == "globex.example/v1"
    # Unscoped, it is still honestly ambiguous — the caller named no scope.
    with pytest.raises(AmbiguousKindError):
        resolve_kind_port(k, "Widget")


@pytest.mark.asyncio
async def test_the_kind_catalog_of_a_scope_lists_only_its_own_kinds(two_scopes):
    """``list_kinds`` answers "what can I act on HERE" — another workspace's
    Kind is not actionable here and must not be advertised."""
    from dna.application.documents import list_kinds_impl
    from dna.application.live import LiveDna

    k, _base = two_scopes
    await k.instance_async(_A)
    await k.instance_async(_B)

    live = LiveDna(base_scope=_A, kernel=k, provider=None)
    kinds_a = {e["kind"] for e in (await list_kinds_impl(live, scope=_A))["kinds"]}
    kinds_b = {e["kind"] for e in (await list_kinds_impl(live, scope=_B))["kinds"]}
    assert "Widget" in kinds_a
    assert "Widget" not in kinds_b
    # Everything else is global and appears in both.
    assert kinds_a - {"Widget"} == kinds_b


@pytest.mark.asyncio
async def test_two_scopes_same_container_route_to_their_own_kind(
    two_scopes_same_kind_name, caplog,
):
    """Both declare ``widgets/``. Within a scope there is exactly one owner."""
    k, _base = two_scopes_same_kind_name
    await k.instance_async(_A)
    await k.instance_async(_B)

    with caplog.at_level(logging.WARNING):
        assert k.kind_by_container("widgets", scope=_A) == "Widget"
        assert k.kind_by_container("widgets", scope=_B) == "Widget"
    assert "Ambiguous storage container" not in caplog.text
    assert (
        k.storage_for_kind("Widget", scope=_A).container
        == k.storage_for_kind("Widget", scope=_B).container
        == "widgets"
    )
