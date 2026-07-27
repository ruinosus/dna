"""i-080 item 1 — a Kind's ``apiVersion`` namespace is OWNED, and the write path
enforces it.

The identity of a Kind is ``(api_version, kind)``. Namespacing the
``api_version`` per workspace makes two workspaces' ``Deal`` two different
Kinds by construction — but only if nobody can declare inside a namespace that
is not theirs. Without the ownership check, a workspace declares
``github.com/ruinosus/dna/helix/v1 + Agent`` and hijacks a system Kind.

The end-to-end scenario at the bottom is the one that motivated the whole issue:
two workspaces, the same Kind NAME, their own namespaces — both resolve, both
validate against their OWN schema, neither discards the other, and a hijack is
refused with a message that names the reason.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel import Kernel
from dna.kernel.kinds.namespaces import (
    NamespaceOwnershipError,
    is_reserved,
    namespace_chain,
    namespace_of,
    owner_of,
    reserved_namespaces,
)
from dna.kernel.protocols import SpecValidationError


# ── the pure algebra ────────────────────────────────────────────────────────


@pytest.mark.parametrize("api_version,expected", [
    ("acme.example/v1", "acme.example"),
    ("github.com/ruinosus/dna/helix/v1", "github.com/ruinosus/dna/helix"),
    ("agents.md/v1", "agents.md"),
    ("v1", ""),
    ("", ""),
    (None, ""),
])
def test_namespace_of(api_version, expected):
    assert namespace_of(api_version) == expected


def test_namespace_chain_is_most_specific_first():
    assert namespace_chain("a/b/c") == ["a/b/c", "a/b", "a"]
    assert namespace_chain("a") == ["a"]
    assert namespace_chain("") == []


def test_reserved_is_derived_from_the_live_registry_not_a_list():
    """Every namespace holding a Kind registered FROM CODE is reserved — the
    platform's own AND every standard DNA consumes under its owner's name."""
    reserved = reserved_namespaces(Kernel.auto().kind_ports())
    for ns in (
        "github.com/ruinosus/dna",
        "github.com/ruinosus/dna/sdlc",
        "github.com/ruinosus/dna/tenant",
        "agents.md",
        "agentskills.io",
        "soulspec.org",
        "presidio",
        "mif-spec.dev",
    ):
        assert ns in reserved, ns
    assert "acme.example" not in reserved


def test_a_per_scope_kind_does_not_reserve_its_own_namespace():
    """Otherwise the FIRST Kind a workspace declared would lock its own owner
    out of declaring a second one."""
    k = Kernel()
    k._register_kind_definitions([_kinddef_raw(
        "acme.example/v1", "Deal", "acme-deal", {"type": "object"},
    )])
    assert "acme.example" not in reserved_namespaces(k.kind_ports())


def test_descendants_of_a_reserved_namespace_are_reserved():
    reserved = frozenset({"github.com/ruinosus/dna/helix"})
    assert is_reserved("github.com/ruinosus/dna/helix", reserved)
    assert is_reserved("github.com/ruinosus/dna/helix/extra", reserved)
    assert is_reserved("github.com/ruinosus/dnax", reserved) is None


def _claim(namespace: str, owner: str) -> dict:
    return {"spec": {"namespace": namespace, "owner": owner,
                     "claimed_at": "2026-07-26T00:00:00+00:00"}}


def test_a_claim_is_a_prefix():
    claims = [_claim("acme.example", "ws-acme")]
    assert owner_of("acme.example", claims).owner == "ws-acme"
    assert owner_of("acme.example/crm", claims).owner == "ws-acme"
    assert owner_of("globex.example", claims).owner is None


def test_the_most_specific_claim_wins():
    claims = [_claim("acme.example", "ws-acme"),
              _claim("acme.example/crm", "ws-crm")]
    v = owner_of("acme.example/crm/deals", claims)
    assert (v.owner, v.claimed_namespace) == ("ws-crm", "acme.example/crm")
    assert owner_of("acme.example/hr", claims).owner == "ws-acme"


def test_one_workspace_may_own_several_namespaces():
    claims = [_claim("acme.example", "ws-acme"), _claim("acme.dev", "ws-acme")]
    assert owner_of("acme.example", claims).owner == "ws-acme"
    assert owner_of("acme.dev", claims).owner == "ws-acme"


def test_two_workspaces_claiming_one_namespace_is_a_refusal_not_a_tie():
    claims = [_claim("acme.example", "ws-acme"), _claim("acme.example", "ws-evil")]
    with pytest.raises(NamespaceOwnershipError) as e:
        owner_of("acme.example", claims)
    assert "ws-acme" in str(e.value) and "ws-evil" in str(e.value)


def test_a_duplicate_claim_by_the_same_owner_is_not_ambiguous():
    claims = [_claim("acme.example", "ws-acme"), _claim("acme.example", "ws-acme")]
    assert owner_of("acme.example", claims).owner == "ws-acme"


# ── the Kind that records a claim ───────────────────────────────────────────


def test_kind_namespace_is_registered_global_and_not_self_servable():
    k = Kernel.auto()
    port = k.kind_port_for("KindNamespace")
    assert port is not None
    assert port.alias == "tenant-kind-namespace"
    assert str(getattr(port.scope, "value", port.scope)) == "global"
    # is_overlayable=False → BOOTSTRAP: the generic write-any-document path
    # refuses it and no layer may fork it. Claiming a namespace is an
    # operator act, not something a workspace grants itself.
    assert port.is_overlayable is False
    assert "KindNamespace" in k._NON_OVERLAYABLE_KINDS
    from dna.application.documents import is_bootstrap_kind
    assert is_bootstrap_kind(port)


# ── the write gate, in isolation ────────────────────────────────────────────


def _kinddef_raw(api_version, kind, alias, schema, *, container=None):
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": alias},
        "spec": {
            "target_api_version": api_version,
            "target_kind": kind,
            "alias": alias,
            "origin": namespace_of(api_version),
            "storage": {"type": "yaml", "container": container or alias + "s"},
            "schema": schema,
            # A registration gate this suite is not about: an unapproved
            # store-loaded Kind never registers at all, so these namespace
            # assertions would pass vacuously without it.
            "approved_by": "approver@example.com",
        },
    }


class _GateHost:
    """Only the NamespaceGateHost surface — reach past it and SimpleNamespace
    semantics would raise."""

    def __init__(self, *, claims, owner=None, ports=None, raises=False):
        self._claims = claims
        self._owner = owner
        self._ports = ports if ports is not None else Kernel.auto().kind_ports()
        self._raises = raises

    def kind_ports(self):
        return self._ports

    async def kind_namespaces(self):
        if self._raises:
            raise RuntimeError("registry unavailable")
        return self._claims

    async def _base_instance_cached_async(self, scope):
        return type("MI", (), {"root": type(
            "G", (), {"spec": {"owner_tenant": self._owner}})()})()


def _gate(**kw):
    from dna.kernel.write.namespace_gate import NamespaceOwnershipGate
    return NamespaceOwnershipGate(_GateHost(**kw))


async def _check(gate, api_version, *, tenant=None, kind="KindDefinition",
                 name="deal"):
    await gate.check(
        "some-scope", kind, name,
        _kinddef_raw(api_version, "Deal", "x-deal", {"type": "object"}),
        tenant=tenant,
    )


@pytest.mark.asyncio
async def test_a_hijack_of_a_system_namespace_is_refused():
    gate = _gate(claims=[_claim("acme.example", "ws-acme")])
    with pytest.raises(NamespaceOwnershipError) as e:
        await _check(gate, "github.com/ruinosus/dna/helix/v1", tenant="ws-acme")
    assert "RESERVED" in str(e.value)
    assert "github.com/ruinosus/dna" in str(e.value)


@pytest.mark.asyncio
async def test_a_reserved_namespace_is_refused_even_when_claimed():
    """A claim cannot grant what the registry already occupies."""
    gate = _gate(claims=[_claim("github.com/ruinosus/dna/helix", "ws-acme")])
    with pytest.raises(NamespaceOwnershipError) as e:
        await _check(gate, "github.com/ruinosus/dna/helix/v1", tenant="ws-acme")
    assert "RESERVED" in str(e.value)


@pytest.mark.asyncio
async def test_declaring_in_another_workspaces_namespace_is_refused():
    gate = _gate(claims=[_claim("globex.example", "ws-globex")])
    with pytest.raises(NamespaceOwnershipError) as e:
        await _check(gate, "globex.example/v1", tenant="ws-acme")
    assert "ws-globex" in str(e.value)


@pytest.mark.asyncio
async def test_an_unclaimed_namespace_is_refused():
    gate = _gate(claims=[])
    with pytest.raises(NamespaceOwnershipError) as e:
        await _check(gate, "nobody.example/v1", tenant="ws-acme")
    assert "nothing claims" in str(e.value)


@pytest.mark.asyncio
async def test_a_bare_version_has_no_namespace_and_is_refused():
    gate = _gate(claims=[_claim("acme.example", "ws-acme")])
    with pytest.raises(NamespaceOwnershipError):
        await _check(gate, "v1", tenant="ws-acme")


@pytest.mark.asyncio
async def test_an_unreadable_claim_registry_refuses_rather_than_assumes():
    gate = _gate(claims=[], raises=True)
    with pytest.raises(NamespaceOwnershipError) as e:
        await _check(gate, "acme.example/v1", tenant="ws-acme")
    assert "unreadable" in str(e.value)


@pytest.mark.asyncio
async def test_the_owner_may_declare_in_its_own_namespace():
    gate = _gate(claims=[_claim("acme.example", "ws-acme")])
    await _check(gate, "acme.example/v1", tenant="ws-acme")
    await _check(gate, "acme.example/crm/v1", tenant="ws-acme")  # prefix claim


@pytest.mark.asyncio
async def test_the_scope_owner_attributes_a_write_that_carries_no_tenant():
    """KindDefinition is structurally non-overlayable, so a workspace's Kind is
    authored at the BASE of a scope the workspace owns — no tenant argument.
    ``Genome.spec.owner_tenant`` is what makes that write attributable."""
    gate = _gate(claims=[_claim("globex.example", "ws-globex")], owner="ws-acme")
    with pytest.raises(NamespaceOwnershipError) as e:
        await _check(gate, "globex.example/v1")
    assert "ws-acme" in str(e.value)


@pytest.mark.asyncio
async def test_an_unattributed_write_is_not_gated():
    """No tenant and no declared scope owner = the operator's own write (the
    self-host shape). This is the back-compat hinge — every existing write path
    in this repo is unattributed."""
    gate = _gate(claims=[], owner=None)
    await _check(gate, "github.com/ruinosus/dna/helix/v1")
    await _check(gate, "anything.example/v1")


@pytest.mark.asyncio
async def test_the_gate_only_looks_at_kind_definition_writes():
    """Declaring a Kind claims a namespace; USING one does not. A workspace
    writing a Story under the sdlc namespace is ordinary traffic."""
    gate = _gate(claims=[], owner="ws-acme")
    await gate.check(
        "s", "Story", "s-1",
        {"apiVersion": "github.com/ruinosus/dna/sdlc/v1", "kind": "Story",
         "metadata": {"name": "s-1"}, "spec": {}},
        tenant="ws-acme",
    )


# ── the scenario that motivated the issue, end to end ───────────────────────


_ACME_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "amount"],
    "properties": {"title": {"type": "string"}, "amount": {"type": "number"}},
}
_GLOBEX_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "stage"],
    "properties": {"title": {"type": "string"}, "stage": {"type": "string"}},
}


def _yaml(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _genome(base: Path, scope: str, owner: str) -> None:
    _yaml(base / scope / "Genome.yaml",
          "apiVersion: github.com/ruinosus/dna/v1\n"
          "kind: Genome\n"
          f"metadata:\n  name: {scope}\n"
          f"spec:\n  owner_tenant: {owner}\n  visibility: private\n")


def _claim_doc(base: Path, namespace: str, owner: str) -> None:
    _yaml(base / "_lib" / "kind-namespaces" / f"{owner}.yaml",
          "apiVersion: github.com/ruinosus/dna/tenant/v1\n"
          "kind: KindNamespace\n"
          f"metadata:\n  name: {owner}\n"
          f"spec:\n  namespace: {namespace}\n  owner: {owner}\n"
          "  claimed_at: '2026-07-26T00:00:00+00:00'\n")


def _kind_doc(base: Path, scope: str, alias: str, raw_spec: dict) -> None:
    import yaml as _y
    _yaml(base / scope / "kinds" / alias / "KIND.yaml",
          _y.safe_dump({
              "apiVersion": "github.com/ruinosus/dna/core/v1",
              "kind": "KindDefinition",
              "metadata": {"name": alias},
              "spec": raw_spec,
          }, sort_keys=False))


@pytest.fixture
def two_workspaces(tmp_path: Path) -> Kernel:
    """Two workspaces, each with its own scope, its own claimed namespace and
    its own ``Deal`` Kind."""
    _claim_doc(tmp_path, "acme.example", "ws-acme")
    _claim_doc(tmp_path, "globex.example", "ws-globex")
    _genome(tmp_path, "acme-scope", "ws-acme")
    _genome(tmp_path, "globex-scope", "ws-globex")
    _kind_doc(tmp_path, "acme-scope", "acme-deal",
              _kinddef_raw("acme.example/v1", "Deal", "acme-deal",
                           _ACME_SCHEMA, container="acme-deals")["spec"])
    _kind_doc(tmp_path, "globex-scope", "globex-deal",
              _kinddef_raw("globex.example/v1", "Deal", "globex-deal",
                           _GLOBEX_SCHEMA, container="globex-deals")["spec"])
    return Kernel.auto(FilesystemWritableSource(base_dir=tmp_path))


@pytest.mark.asyncio
async def test_two_workspaces_declare_the_same_kind_name_and_both_survive(
    two_workspaces: Kernel,
):
    k = two_workspaces
    await k.instance_async("acme-scope")
    await k.instance_async("globex-scope")

    acme = k.kind_port_for("Deal", api_version="acme.example/v1")
    globex = k.kind_port_for("Deal", api_version="globex.example/v1")
    assert acme is not None and globex is not None
    assert acme is not globex
    # neither silently discarded the other, and each kept its OWN schema
    assert acme.schema()["required"] == ["title", "amount"]
    assert globex.schema()["required"] == ["title", "stage"]
    # the alias namespaced itself with the api_version, so the wire key of
    # dep_filters / LayerPolicy is distinct too
    assert {acme.alias, globex.alias} == {"acme-deal", "globex-deal"}


@pytest.mark.asyncio
async def test_each_workspaces_documents_validate_against_its_own_schema(
    two_workspaces: Kernel,
):
    k = two_workspaces
    await k.instance_async("acme-scope")
    await k.instance_async("globex-scope")

    await k.write_document("acme-scope", "Deal", "d-1", {
        "apiVersion": "acme.example/v1", "kind": "Deal",
        "metadata": {"name": "d-1"}, "spec": {"title": "T", "amount": 10},
    })
    await k.write_document("globex-scope", "Deal", "d-1", {
        "apiVersion": "globex.example/v1", "kind": "Deal",
        "metadata": {"name": "d-1"}, "spec": {"title": "T", "stage": "won"},
    })
    # acme's document shape is INVALID for globex's Kind and vice versa —
    # which is the proof the two are not one Kind wearing two names.
    with pytest.raises(SpecValidationError):
        await k.write_document("globex-scope", "Deal", "d-2", {
            "apiVersion": "globex.example/v1", "kind": "Deal",
            "metadata": {"name": "d-2"}, "spec": {"title": "T", "amount": 10},
        })
    with pytest.raises(SpecValidationError):
        await k.write_document("acme-scope", "Deal", "d-2", {
            "apiVersion": "acme.example/v1", "kind": "Deal",
            "metadata": {"name": "d-2"}, "spec": {"title": "T", "stage": "won"},
        })


@pytest.mark.asyncio
async def test_a_workspace_may_add_a_kind_in_its_own_namespace(
    two_workspaces: Kernel,
):
    k = two_workspaces
    await k.instance_async("acme-scope")
    await k.write_document(
        "acme-scope", "KindDefinition", "acme-lead",
        _kinddef_raw("acme.example/v1", "Lead", "acme-lead",
                     {"type": "object"}, container="acme-leads"),
    )


@pytest.mark.asyncio
async def test_a_workspace_may_not_hijack_a_system_kind(two_workspaces: Kernel):
    k = two_workspaces
    await k.instance_async("acme-scope")
    with pytest.raises(NamespaceOwnershipError) as e:
        await k.write_document(
            "acme-scope", "KindDefinition", "evil",
            _kinddef_raw("github.com/ruinosus/dna/helix/v1", "Agent",
                         "acme-agent", {"type": "object"}),
        )
    msg = str(e.value)
    assert "RESERVED" in msg and "ws-acme" in msg


@pytest.mark.asyncio
async def test_a_workspace_may_not_declare_in_the_other_workspaces_namespace(
    two_workspaces: Kernel,
):
    k = two_workspaces
    await k.instance_async("acme-scope")
    with pytest.raises(NamespaceOwnershipError) as e:
        await k.write_document(
            "acme-scope", "KindDefinition", "poach",
            _kinddef_raw("globex.example/v1", "Lead", "globex-lead",
                         {"type": "object"}, container="globex-leads"),
        )
    msg = str(e.value)
    assert "ws-globex" in msg and "ws-acme" in msg


@pytest.mark.asyncio
async def test_a_workspace_may_not_declare_in_an_unclaimed_namespace(
    two_workspaces: Kernel,
):
    k = two_workspaces
    await k.instance_async("acme-scope")
    with pytest.raises(NamespaceOwnershipError) as e:
        await k.write_document(
            "acme-scope", "KindDefinition", "squat",
            _kinddef_raw("unclaimed.example/v1", "Lead", "unclaimed-lead",
                         {"type": "object"}, container="unclaimed-leads"),
        )
    assert "nothing claims" in str(e.value)


@pytest.mark.asyncio
async def test_each_workspaces_documents_land_in_their_own_container(
    two_workspaces: Kernel, tmp_path: Path,
):
    """Namespacing the apiVersion is worth nothing if the STORAGE path is
    resolved by the bare Kind name.

    Found while proving the scenario above: both workspaces' ``Deal``
    documents were written into ``<scope>/acme-deals/``, because the write path
    asked for the container by name (``storage_for_kind("Deal")``) and the bare
    lookup resolves ONE of the two ports. The scopes differ, so nothing was
    overwritten — but every globex document sat in a directory belonging to
    acme's Kind, where the container→Kind index says it is an acme Deal."""
    k = two_workspaces
    await k.instance_async("acme-scope")
    await k.instance_async("globex-scope")
    await k.write_document("acme-scope", "Deal", "d-1", {
        "apiVersion": "acme.example/v1", "kind": "Deal",
        "metadata": {"name": "d-1"}, "spec": {"title": "T", "amount": 10},
    })
    await k.write_document("globex-scope", "Deal", "d-1", {
        "apiVersion": "globex.example/v1", "kind": "Deal",
        "metadata": {"name": "d-1"}, "spec": {"title": "T", "stage": "won"},
    })
    assert (tmp_path / "acme-scope" / "acme-deals" / "d-1.yaml").exists()
    assert (tmp_path / "globex-scope" / "globex-deals" / "d-1.yaml").exists()
    assert not (tmp_path / "globex-scope" / "acme-deals").exists()
