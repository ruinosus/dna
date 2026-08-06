"""i-096 — a Kind declared in the BASE scope governs the scopes that DECLARE it
as parent, and only those.

The asymmetry this file closes. i-058 made DOCUMENTS flow down the declared
``Genome.spec.parent_scope`` chain (``compute_resolution_chain``); the KINDS did
not follow. ``KindDefinition`` is a BOOTSTRAP Kind, so a descriptor seeded in
the host-curated base registered a port bound (i-081 ``__scopes__``) to the base
scope alone. In a child workspace scope the Kind then did not exist:

* ``GET /v1/kinds/<K>/documents`` answered 200 without a tenant and
  ``Kind '<K>' is not registered on this source`` with one;
* the Kind was absent from the tenant's registry ENUMERATION;
* and a write of that Kind into the workspace was refused —

while documents of that same Kind, written in the base, listed fine through the
child. Measured live on 06/08/2026 (``McpServer``, ``CopilotBlueprint``): every
PRODUCT Kind had to become an extension (code + release) instead of a document,
which is the declarative-Kind promise inverted.

The two halves this file must prove together, because either alone is a wrong
fix:

1. **down the declared chain** — a Kind declared ONLY in the base is readable,
   enumerable and WRITABLE from a scope that declares that base as parent,
   transitively, with a local declaration winning over the inherited one;
2. **never sideways** — a Kind declared by a SIBLING scope (one that shares the
   same parent, or merely lives in the same store) stays invisible: not
   resolvable, not enumerated, not schema-enforcing, not storage-routing. That
   is i-081, and a fix that reopened it would be a tenant leak wearing an
   inheritance costume.

Half 2 also holds for the direction that has no chain at all: the PARENT does
not inherit from its children.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.documents import (
    UnknownKindError,
    list_kinds_impl,
    resolve_kind_port,
)
from dna.application.live import LiveDna
from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod
from dna.kernel.kinds.registry import applies_to
from dna.kernel.protocols import SpecValidationError

#: the host-curated base (dna-cloud points DNA_WORKSPACE_DEFINITIONS_BASE here)
_BASE = "base-defs"
#: a workspace scope that DECLARES the base as parent
_WS = "tenant-ws-child"
#: a second workspace, sibling of the first, with its OWN declared Kind
_SIBLING = "tenant-ws-sibling"
#: a grandchild — declares _WS as parent (transitivity)
_GRANDCHILD = "tenant-ws-grandchild"
#: a workspace that declares NO parent (anti-vacuity control)
_ORPHAN = "tenant-ws-orphan"

_SCHEMA = {
    "type": "object",
    "required": ["title"],
    "properties": {"title": {"type": "string"}},
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def _clear_process_wide_warn_caches():
    for cache in (
        registry_mod._AMBIGUOUS_LOOKUP_WARNED,
        registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED,
        registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED,
    ):
        cache.clear()
    yield
    for cache in (
        registry_mod._AMBIGUOUS_LOOKUP_WARNED,
        registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED,
        registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED,
    ):
        cache.clear()


def _kinddef(
    *, namespace: str, kind: str, alias: str, container: str,
    schema: dict | None = None,
) -> dict:
    """An APPROVED per-scope ``KindDefinition`` whose schema REQUIRES ``title``
    — so "was this document validated against a Kind at all?" has a yes/no
    answer, and "against WHOSE Kind?" has one too (the container differs)."""
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
            "schema": schema or _SCHEMA,
            "approved_by": "approver@example.com",
        },
    }


def _genome(scope: str, parent: str | None = None) -> dict:
    spec: dict = {"description": f"fixture scope {scope}"}
    if parent:
        spec["parent_scope"] = parent
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": spec,
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
def scopes(tmp_path: Path):
    """The shape of the live defect:

    ``base-defs`` declares ``McpServer``; ``tenant-ws-child`` declares the base
    as parent and nothing of its own; ``tenant-ws-grandchild`` declares the
    child as parent; ``tenant-ws-sibling`` shares the base as parent and
    declares a Kind of its OWN (``SiblingSecret``); ``tenant-ws-orphan``
    declares no parent at all.
    """
    base = tmp_path / ".dna"
    _write_yaml(base / _BASE / "Genome.yaml", _genome(_BASE))
    _write_yaml(
        base / _BASE / "kinds" / "mcp-server.yaml",
        _kinddef(namespace="dna.cloud", kind="McpServer",
                 alias="dna-cloud-mcp-server", container="mcp-servers"),
    )

    _write_yaml(base / _WS / "Genome.yaml", _genome(_WS, parent=_BASE))
    _write_yaml(
        base / _GRANDCHILD / "Genome.yaml", _genome(_GRANDCHILD, parent=_WS),
    )
    _write_yaml(base / _ORPHAN / "Genome.yaml", _genome(_ORPHAN))

    _write_yaml(base / _SIBLING / "Genome.yaml", _genome(_SIBLING, parent=_BASE))
    _write_yaml(
        base / _SIBLING / "kinds" / "sibling-secret.yaml",
        _kinddef(namespace="sibling.example", kind="SiblingSecret",
                 alias="sibling-secret", container="secrets"),
    )

    k = Kernel.auto(FilesystemWritableSource(str(base)))
    return k, base


def _live(k: Kernel) -> LiveDna:
    return LiveDna(base_scope=_BASE, kernel=k, provider=None)


# ══ half 1 — the Kind descends the DECLARED chain ═══════════════════════════


@pytest.mark.asyncio
async def test_base_kind_is_registered_for_the_child_scope(scopes):
    """The registry answer the whole issue reduces to: composing the child
    scope makes the base's Kind exist THERE."""
    k, _base = scopes
    await k.instance_async(_WS)

    port = k.kind_port_for("McpServer", scope=_WS)
    assert port is not None
    assert port.api_version == "dna.cloud/v1"
    # …and the port genuinely applies to the child, not merely resolves.
    assert applies_to(port, _WS)


@pytest.mark.asyncio
async def test_base_kind_is_registered_on_a_lazy_boot_too(scopes):
    """``LiveDna.ensure_kinds`` — the seam every REST/MCP document route goes
    through — drives ``instance_async(lazy=True)``. Inheritance that existed
    only on the eager path would leave the workspace seeing the base's Kinds or
    not depending on which surface it arrived through."""
    k, _base = scopes
    await k.instance_async(_WS, lazy=True)
    assert k.kind_port_for("McpServer", scope=_WS) is not None


@pytest.mark.asyncio
async def test_the_child_enumerates_the_inherited_kind(scopes):
    """The founder's third probe: the Kind was missing from
    ``GET /v1/kinds/registry?tenant=<ws>``. ``list_kinds`` is that surface."""
    k, _base = scopes
    await k.instance_async(_WS)

    live = _live(k)
    kinds = {e["kind"] for e in (await list_kinds_impl(live, scope=_WS))["kinds"]}
    assert "McpServer" in kinds


@pytest.mark.asyncio
async def test_the_generic_document_surface_resolves_the_inherited_kind(scopes):
    """``resolve_kind_port`` is the ONE resolution every generic document
    use-case goes through — it is what raised ``Kind 'McpServer' is not
    registered on this source`` for a tenant and 200'd without one."""
    k, _base = scopes
    await k.instance_async(_WS)
    assert resolve_kind_port(
        k, "McpServer", scope=_WS,
    ).api_version == "dna.cloud/v1"


@pytest.mark.asyncio
async def test_the_inherited_kind_is_writable_from_the_child(scopes):
    """READABLE is half the "pronto quando"; WRITABLE is the half that makes
    ``CopilotBlueprint`` persist instead of living in a render fallback.

    Three properties in one write: it is accepted, it is VALIDATED against the
    base's schema, and it is ROUTED into the base's declared container — inside
    the CHILD's own scope directory, never the base's."""
    k, base = scopes
    await k.instance_async(_WS)

    await k.write_document(
        _WS, "McpServer", "gh",
        _doc("dna.cloud", "McpServer", "gh", {"title": "GitHub"}),
    )
    assert (base / _WS / "mcp-servers" / "gh.yaml").exists()
    # the child's document did NOT land in the base scope
    assert not (base / _BASE / "mcp-servers" / "gh.yaml").exists()

    # schema enforcement travelled with the Kind
    with pytest.raises(SpecValidationError):
        await k.write_document(
            _WS, "McpServer", "bad",
            _doc("dna.cloud", "McpServer", "bad", {"nope": 1}),
        )


@pytest.mark.asyncio
async def test_inheritance_is_transitive(scopes):
    """ws → base is one hop; grandchild → ws → base is the chain. The Kinds
    walk the same transitive chain the documents do, or "declare a parent" would
    mean two different things one level down."""
    k, _base = scopes
    await k.instance_async(_GRANDCHILD)
    assert k.kind_port_for("McpServer", scope=_GRANDCHILD) is not None


@pytest.mark.asyncio
async def test_no_declared_parent_means_no_inherited_kind(scopes):
    """Anti-vacuity: inheritance is a DECLARATION. A workspace that declares no
    ``parent_scope`` does not acquire the base's Kind — otherwise the test above
    would pass for a fix that simply made every Kind global again."""
    k, _base = scopes
    await k.instance_async(_ORPHAN)
    assert k.kind_port_for("McpServer", scope=_ORPHAN) is None


@pytest.fixture()
def divergent_scopes(tmp_path: Path):
    """Base and child both declare ``McpServer`` — different schema, different
    container. The two descriptors disagree, which is what makes precedence
    observable at all."""
    base = tmp_path / ".dna"
    _write_yaml(base / _BASE / "Genome.yaml", _genome(_BASE))
    _write_yaml(
        base / _BASE / "kinds" / "mcp-server.yaml",
        _kinddef(namespace="dna.cloud", kind="McpServer",
                 alias="dna-cloud-mcp-server", container="base-mcp-servers"),
    )
    _write_yaml(base / _WS / "Genome.yaml", _genome(_WS, parent=_BASE))
    _write_yaml(
        base / _WS / "kinds" / "mcp-server.yaml",
        _kinddef(
            namespace="dna.cloud", kind="McpServer",
            alias="dna-cloud-mcp-server", container="ws-mcp-servers",
            schema={
                "type": "object",
                "required": ["headline"],
                "properties": {"headline": {"type": "string"}},
                "additionalProperties": False,
            },
        ),
    )
    k = Kernel.auto(FilesystemWritableSource(str(base)))
    return k, base


@pytest.mark.asyncio
@pytest.mark.parametrize("lazy", [False, True])
async def test_a_local_declaration_wins_over_the_inherited_one(
    divergent_scopes, lazy: bool,
):
    """Local-wins, the precedence the DOCUMENTS already have
    (``compute_resolution_chain``). A child that declares its own descriptor for
    the same Kind is governed by ITS descriptor: its schema validates, its
    container routes.

    Parametrized over the boot mode ON PURPOSE. On the eager path the local
    descriptor is re-registered once more inside ``build``, so local-wins would
    survive there even if the ancestor pass replaced the port; the LAZY path has
    no such second pass, and it is the path ``LiveDna.ensure_kinds`` — and
    therefore every REST/MCP document route — actually takes. Only the lazy
    parameter kills the mutant of dropping the funnel's never-replace guard.

    Scope of the claim: the registry holds ONE port per ``(apiVersion, kind)``,
    so two scopes that declare *divergent* descriptors under the same key are
    already an i-080 refusal ("one apiVersion namespace has one owner") — that
    predates i-096 and is not what this asserts. What this asserts is the
    narrower, load-bearing thing: the ancestor pass never unregisters and
    replaces a port the child scope is already governed by."""
    k, base = divergent_scopes
    await k.instance_async(_WS, lazy=lazy)

    # the CHILD's storage routing, and the CHILD's schema
    assert k.storage_for_kind("McpServer", scope=_WS).container == "ws-mcp-servers"
    await k.write_document(
        _WS, "McpServer", "own",
        _doc("dna.cloud", "McpServer", "own", {"headline": "mine"}),
    )
    assert (base / _WS / "ws-mcp-servers" / "own.yaml").exists()
    assert not (base / _WS / "base-mcp-servers" / "own.yaml").exists()
    with pytest.raises(SpecValidationError):
        await k.write_document(
            _WS, "McpServer", "nope",
            _doc("dna.cloud", "McpServer", "nope", {"title": "base shape"}),
        )


# ══ half 2 — the guard-rail: i-096 must NOT reopen i-081 ════════════════════


@pytest.mark.asyncio
async def test_a_sibling_scopes_kind_stays_invisible(scopes):
    """THE guard-rail. ``tenant-ws-sibling`` declares ``SiblingSecret`` and
    shares the base as parent — it is not on any chain of ``tenant-ws-child``,
    so its Kind must not be resolvable there, in a process that has composed
    both. Inheritance descends; it never goes sideways."""
    k, _base = scopes
    await k.instance_async(_SIBLING)          # sibling composed FIRST — the
    assert k.kind_port_for("SiblingSecret", scope=_SIBLING) is not None
    await k.instance_async(_WS)               # leak direction i-081 measured

    assert k.kind_port_for("SiblingSecret", scope=_WS) is None
    assert k.kind_port_for("SiblingSecret", scope=_GRANDCHILD) is None
    with pytest.raises(UnknownKindError):
        resolve_kind_port(k, "SiblingSecret", scope=_WS)


@pytest.mark.asyncio
async def test_a_sibling_kind_is_neither_enumerated_nor_effective(scopes):
    """The same guard-rail measured where it BITES rather than where it reads:
    a sibling's Kind must not appear in the child's catalogue, must not validate
    the child's documents, and must not route the child's storage.

    Without these, "invisible" could be true only of the lookup surface while
    the behaviour-conferring paths leaked — which is exactly the shape of the
    bug i-081 was filed for."""
    k, base = scopes
    await k.instance_async(_SIBLING)
    await k.instance_async(_WS)

    live = _live(k)
    kinds_ws = {e["kind"] for e in (await list_kinds_impl(live, scope=_WS))["kinds"]}
    kinds_sib = {
        e["kind"] for e in (await list_kinds_impl(live, scope=_SIBLING))["kinds"]
    }
    assert "SiblingSecret" not in kinds_ws
    assert "SiblingSecret" in kinds_sib
    # the inherited Kind is in BOTH — both declare the base as parent, which is
    # the control proving the exclusion above is about the CHAIN, not about the
    # child being blind to every declarative Kind.
    assert "McpServer" in kinds_ws and "McpServer" in kinds_sib

    # not schema-enforcing in the child: an unknown Kind is accepted unvalidated
    await k.write_document(
        _WS, "SiblingSecret", "s1",
        _doc("sibling.example", "SiblingSecret", "s1", {"nope": 1}),
    )
    # …and not storage-routing: it never lands in the sibling's container
    assert not (base / _WS / "secrets" / "s1.yaml").exists()
    # while in its OWNER the same spec is refused
    with pytest.raises(SpecValidationError):
        await k.write_document(
            _SIBLING, "SiblingSecret", "s2",
            _doc("sibling.example", "SiblingSecret", "s2", {"nope": 1}),
        )


@pytest.mark.asyncio
async def test_inheritance_does_not_run_upwards(scopes):
    """A chain has a direction. The base declares the child's parent, not the
    reverse, so the child's own Kind never reaches the base — otherwise a
    workspace could inject a Kind into the host-curated scope every other
    workspace inherits from."""
    k, _base = scopes
    await k.instance_async(_SIBLING)
    await k.instance_async(_BASE)
    assert k.kind_port_for("SiblingSecret", scope=_BASE) is None
