"""RegistryHost narrow-fake guard (``s-kernel-decomp-f3-kindregistry``).

Fase 3 moved the Kind registration funnel (``kind()`` / ``kind_from_descriptor``
/ the 2-phase-load per-scope funnel) OUT of the Kernel god-object and INTO the
``KindRegistry`` collaborator. Per the épico's anti-cosmetic rule (spec §3.1 /
anti-goal §5.3), the collaborator must NOT hold the whole 117-member Kernel as a
back-ref — it reaches the wider kernel through the NARROW ``RegistryHost``
Protocol (hooks fan-out, the ``_readers`` rescan gate, generic reader/writer
wiring, ``_generics_resolved``). This test proves the narrowing is real:

  1. ``register_kind`` runs its main path against a plain ``SimpleNamespace``
     exposing ONLY the RegistryHost surface — reach past it → ``AttributeError``.
  2. A real ``Kernel`` structurally satisfies ``RegistryHost`` (so the kernel
     still passes ``self`` — zero runtime change).
  3. The fake is genuinely a slice (lacks god-object members).
"""
from __future__ import annotations

import types

from dna.kernel import Kernel
from dna.kernel.collaborator_ports import RegistryHost
from dna.kernel.kinds.base import KindBase
from dna.kernel.kinds.registry import KindRegistry
from dna.kernel.protocols import StorageDescriptor


class _FakeKind(KindBase):
    api_version = "rh.io/v1"
    kind = "Widget"
    alias = "rh-widget"
    storage = StorageDescriptor.yaml("widgets")


class _AliaslessKind(KindBase):
    api_version = "rh.io/v1"
    kind = "Gizmo"
    alias = None  # present (satisfies KindPort) but falsy → generation path
    storage = StorageDescriptor.yaml("gizmos")


def _registry_host_fake(**over) -> types.SimpleNamespace:
    """A slice exposing ONLY the RegistryHost surface (SimpleNamespace raises
    AttributeError for anything else — that IS the boundary enforcement)."""
    base = dict(
        _generics_resolved=True,
        _readers=[],
        _ensure_generic_readers_writers=lambda: None,
        hooks=types.SimpleNamespace(
            has=lambda name: False,
            emit=lambda name, ctx: None,
        ),
    )
    base.update(over)
    return types.SimpleNamespace(**base)


def test_register_kind_runs_on_narrow_fake():
    """The H1 register path lands the kind + flips the host's generics flag,
    touching NOTHING outside RegistryHost."""
    host = _registry_host_fake()
    reg = KindRegistry(host=host)  # type: ignore[arg-type]

    reg.register_kind(_FakeKind())

    assert reg.port_for("Widget") is not None
    assert host._generics_resolved is False  # register flipped it via the host
    assert isinstance(host, RegistryHost)


def test_register_kind_generates_alias_via_host_owner_ctx():
    """The aliasless path reads the LAZY ``_loading_ext_owner`` off the host via
    getattr-with-default (absent here → falls back to the api_version token)."""
    host = _registry_host_fake()
    reg = KindRegistry(host=host)  # type: ignore[arg-type]

    reg.register_kind(_AliaslessKind())

    port = reg.port_for("Gizmo")
    assert port is not None
    assert port.alias == "rh-gizmo"  # <owner=rh>-<kebab(Gizmo)>
    assert getattr(port, "__alias_generated__", False) is True


def test_view_registry_without_host_does_lookups_only():
    """A view-only registry (host=None, e.g. CompositionEngine wrapping a kinds
    map) still resolves lookups — registration is simply never called on it."""
    reg = KindRegistry({("rh.io/v1", "Widget"): _FakeKind()})
    assert reg._host is None
    assert reg.port_for("Widget") is not None
    assert reg.alias_for("Widget") == "rh-widget"


def test_kernel_satisfies_registry_host():
    k = Kernel.auto()
    assert isinstance(k, RegistryHost)


def test_fake_is_a_slice_not_the_kernel():
    host = _registry_host_fake()
    assert not isinstance(host, Kernel)
    for god in ("load", "write_document", "search", "kind", "_kindreg", "query"):
        assert not hasattr(host, god), f"slice leaked kernel member {god!r}"
