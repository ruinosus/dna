"""FakeKernelSlice guard — the anti-cosmetic-decomposition test (``s-kernel-decomp-f1``).

Each of the 7 kernel collaborators that used to hold ``self._k: "Kernel"`` (the
whole god-object) now declares a NARROW ``*Host`` Protocol
(``dna.kernel.collaborator_ports``). This test proves the narrowing is
REAL, not cosmetic: every collaborator is instantiated with a ``FakeKernelSlice``
that exposes ONLY its ``*Host`` surface — a plain ``SimpleNamespace``, NOT a
``Kernel`` — and its main path is exercised. If a collaborator reaches for a
kernel member outside its declared Protocol, the fake raises ``AttributeError``
and this test fails → you either tighten the collaborator or (in code review)
widen the Protocol. Widening the back-ref silently is now impossible.

Three layers of proof:
  1. ``test_<collab>_runs_on_narrow_fake`` — behavior on the fake (the teeth).
  2. ``test_kernel_satisfies_<Host>`` — a real ``Kernel`` structurally satisfies
     each narrow Protocol (so the kernel still passes ``self`` — zero runtime change).
  3. ``test_fake_is_a_slice_not_the_kernel`` + ``test_missing_member_breaks`` —
     the fake is genuinely a slice (lacks god-object members) and the guard has
     teeth (a fake missing a used member breaks the collaborator).
"""
from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.kernel.bundle_io import BundleIO
from dna.kernel.collaborator_ports import (
    BundleIOHost,
    CompositionResolverHost,
    InstanceBuilderHost,
    InvalidationHost,
    LayerPolicyHost,
    QueryEngineHost,
    SourceSyncHost,
)
from dna.kernel.composition_resolver import CompositionResolver
from dna.kernel.instance_builder import InstanceBuilder
from dna.kernel.invalidation import InvalidationController
from dna.kernel.layer_policy import LayerPolicyEnforcer
from dna.kernel.protocols import StoragePattern
from dna.kernel.query_engine import QueryEngine
from dna.kernel.source_sync import SourceSync


# --------------------------------------------------------------------------
# Fake helpers — a slice exposes ONLY the members handed to it. SimpleNamespace
# raises AttributeError for anything else (that IS the boundary enforcement).
# --------------------------------------------------------------------------

# A sentinel god-object member that MUST NOT be present on any narrow slice.
# (If a fake accidentally carried the whole kernel, `hasattr(fake, _GOD_MEMBER)`
# would be True and `test_fake_is_a_slice_not_the_kernel` would fail.)
_GOD_MEMBER = "hooks"


def _slice(**members) -> types.SimpleNamespace:
    ns = types.SimpleNamespace(**members)
    assert not hasattr(ns, _GOD_MEMBER), "slice leaked a god-object member"
    return ns


def _async_ret(value):
    async def _fn(*_a, **_k):
        return value

    return _fn


# Shared canned role-slices (only the members each collaborator actually touches
# on the exercised path need real behavior; the rest satisfy the Protocol shape).

def _kindlookup(**over):
    base = dict(
        _kinds={},
        kind_plane=lambda kind, *, api_version=None: "composition",
        storage_for_kind=lambda kn: None,
        _alias_for=lambda k: k,
        _ensure_generic_readers_writers=lambda: None,
    )
    base.update(over)
    return base


def _docstore(**over):
    base = dict(
        _source=None,
        _readers=[],
        _writers=[],
        tenant=None,
        _main_loop=None,
        _parse_doc=lambda raw, origin="local": None,
        _granular_doc_cached=_async_ret(None),
    )
    base.update(over)
    return base


def _inheritance(**over):
    base = dict(
        _INHERIT_PARENT_SCOPE="_lib",
        _INHERITABLE_KINDS=frozenset(),
        _NON_OVERLAYABLE_KINDS=frozenset(),
        _base_instance_cached=lambda s: None,
        _base_instance_cached_async=_async_ret(None),
        _catalog_scopes=_async_ret([]),
        _compute_resolution_chain=_async_ret([]),
    )
    base.update(over)
    return base


def _writeops(**over):
    base = dict(
        write_document=_async_ret(None),
        write_bundle_entry_async=_async_ret(None),
    )
    base.update(over)
    return base


def _buildctx(**over):
    base = dict(
        _cache=None,
        _profiles=[],
        _resolvers={},
        _register_kind_definitions=lambda raws: False,
        _register_custom_kinds=lambda m: None,
    )
    base.update(over)
    return base


# --------------------------------------------------------------------------
# 1. The teeth — each collaborator runs its main path on a NARROW fake
# --------------------------------------------------------------------------


def test_instance_builder_runs_on_narrow_fake():
    fake = _slice(**_kindlookup(), **_docstore(), **_inheritance(), **_buildctx())
    builder = InstanceBuilder(fake)  # type: ignore[arg-type]
    mi = builder.build([], "myscope")  # pure-compute core; MI just stores the ref
    assert mi.scope == "myscope"
    assert isinstance(fake, InstanceBuilderHost)


@pytest.mark.asyncio
async def test_query_engine_runs_on_narrow_fake():
    canned = {"kind": "Agent", "metadata": {"name": "n"}, "spec": {}}
    fake = _slice(
        **_docstore(_source=object(), _granular_doc_cached=_async_ret(canned)),
        **_inheritance(),
    )
    qe = QueryEngine(fake)  # type: ignore[arg-type]
    got = await qe.get_document("myscope", "Agent", "n")
    assert got == canned
    assert isinstance(fake, QueryEngineHost)


@pytest.mark.asyncio
async def test_composition_resolver_runs_on_narrow_fake():
    fake = _slice(
        **_kindlookup(), **_docstore(), **_inheritance(),
        **_writeops(),
        _LAYER_OBSERVERS_MAX=1000, _layer_observers={},
    )
    cr = CompositionResolver(fake)  # type: ignore[arg-type]
    chain = await cr.compute_resolution_chain("myscope", None)
    scopes = [s for s, _ in chain]
    assert "myscope" in scopes and "_lib" in scopes  # inherit-by-default fallback
    assert isinstance(fake, CompositionResolverHost)


def test_bundle_io_runs_on_narrow_fake():
    kind_port = types.SimpleNamespace(
        kind="Agent",
        storage=types.SimpleNamespace(
            pattern=StoragePattern.YAML, container="agents", marker="AGENT.md",
            body_field=None,
        ),
    )
    fake = _slice(**_kindlookup(_kinds={("v1", "Agent"): kind_port}), **_docstore())
    bio = BundleIO(fake)  # type: ignore[arg-type]
    out = bio.serialize("myscope", "Agent", "n", {"spec": {}})
    assert "files" in out and out["files"][0]["relativePath"] == "agents/n.yaml"
    assert isinstance(fake, BundleIOHost)


@pytest.mark.asyncio
async def test_source_sync_runs_on_narrow_fake():
    fake_src = types.SimpleNamespace(load_layer=_async_ret([]))
    fake = _slice(**_kindlookup(), **_docstore())
    ss = SourceSync(fake)  # type: ignore[arg-type]
    manifest = await ss.digest_manifest("myscope", source=fake_src)
    assert manifest == {}
    assert isinstance(fake, SourceSyncHost)


def test_layer_policy_runs_on_narrow_fake():
    fake_mi = types.SimpleNamespace(all=lambda kind: [])
    fake = _slice(
        **_kindlookup(),
        **_inheritance(_base_instance_cached=lambda s: fake_mi),
    )
    lp = LayerPolicyEnforcer(fake)  # type: ignore[arg-type]
    # OPEN policy (no LayerPolicy docs, K not non-overlayable) → returns None.
    assert lp.check("myscope", "Agent", "n", {}, ("branch", "x")) is None
    assert isinstance(fake, LayerPolicyHost)


def test_invalidation_runs_on_narrow_fake():
    dropped: list[str] = []
    fake_kcache = types.SimpleNamespace(
        base_drop=lambda s: dropped.append(s),
        doc_drop_key=lambda key: None,
    )
    fake = _slice(
        _SCHEMA_INVALIDATING_KINDS=frozenset({"Agent"}),
        _batch_mode_depth=0,
        _batch_pending=[],
        _kcache=fake_kcache,
        _write_observers=[],
        _holders=[],
        _layer_observers={},
    )
    inv = InvalidationController(fake)  # type: ignore[arg-type]
    inv.invalidate(scope="myscope", kind="Agent", name="n", op="save")
    assert dropped == ["myscope"]  # schema-invalidating kind dropped the base cache
    assert isinstance(fake, InvalidationHost)


# --------------------------------------------------------------------------
# 2. A real Kernel structurally satisfies every narrow Host (zero runtime change)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [
        InstanceBuilderHost,
        QueryEngineHost,
        CompositionResolverHost,
        BundleIOHost,
        SourceSyncHost,
        LayerPolicyHost,
        InvalidationHost,
    ],
)
def test_kernel_satisfies_host(host):
    k = Kernel.auto()
    assert isinstance(k, host), f"Kernel must structurally satisfy {host.__name__}"


# --------------------------------------------------------------------------
# 3. The fake is a slice, and the guard has teeth
# --------------------------------------------------------------------------


def test_fake_is_a_slice_not_the_kernel():
    """The widest fake (instance_builder's) is still << the Kernel surface and
    lacks god-object members — proof this is a narrow interface, not the kernel."""
    fake = _slice(**_kindlookup(), **_docstore(), **_inheritance(), **_buildctx())
    members = {m for m in vars(fake) if not m.startswith("__")}
    # instance_builder is the widest back-ref; still a small slice.
    assert len(members) <= 24
    # It is NOT a Kernel and lacks the god-object surface a Kernel exposes.
    assert not isinstance(fake, Kernel)
    for god in ("hooks", "_toolreg", "load", "write_document", "search", "auto"):
        assert not hasattr(fake, god), f"slice leaked kernel member {god!r}"
    # The Kernel, by contrast, carries all of them.
    k = Kernel.auto()
    for god in ("hooks", "_toolreg", "load", "search"):
        assert hasattr(k, god)


@pytest.mark.asyncio
async def test_missing_member_breaks_the_collaborator():
    """Negative control: drop a member the collaborator uses and it must raise
    AttributeError — proving the fake genuinely enforces the boundary."""
    # query_engine.get_document asserts `k._source`; a fake without it breaks.
    incomplete = _slice(
        **{k: v for k, v in _docstore().items() if k != "_source"},
        **_inheritance(),
    )
    qe = QueryEngine(incomplete)  # type: ignore[arg-type]
    with pytest.raises(AttributeError):
        await qe.get_document("myscope", "Agent", "n")


# --------------------------------------------------------------------------
# 4. AST guard — no migrated collaborator may re-declare ``kernel: "Kernel"``
#    (the whole god-object). Every back-ref must be typed by a narrow ``*Host``.
# --------------------------------------------------------------------------

# (module basename in dna/kernel) -> class holding the back-ref.
_MIGRATED_COLLABORATORS = {
    "instance_builder": "InstanceBuilder",
    "query_engine": "QueryEngine",
    "composition_resolver": "CompositionResolver",
    "bundle_io": "BundleIO",
    "source_sync": "SourceSync",
    "layer_policy": "LayerPolicyEnforcer",
    "invalidation": "InvalidationController",
}

_KERNEL_DIR = Path(__file__).resolve().parents[1] / "dna" / "kernel"


def _init_kernel_annotation(module: str, cls_name: str) -> str:
    """Return the source text of the ``kernel`` param annotation of
    ``cls_name.__init__`` in ``<module>.py``."""
    tree = ast.parse((_KERNEL_DIR / f"{module}.py").read_text())
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == cls_name
    )
    init = next(
        n for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "__init__"
    )
    arg = next(a for a in init.args.args if a.arg == "kernel")
    assert arg.annotation is not None, f"{module}.{cls_name} kernel arg has no annotation"
    return ast.literal_eval(arg.annotation) if isinstance(
        arg.annotation, ast.Constant
    ) else ast.unparse(arg.annotation)


@pytest.mark.parametrize("module,cls_name", sorted(_MIGRATED_COLLABORATORS.items()))
def test_no_collaborator_declares_bare_kernel(module, cls_name):
    ann = _init_kernel_annotation(module, cls_name)
    assert ann != "Kernel", (
        f"{module}.{cls_name}.__init__ re-declared the god-object "
        f"`kernel: \"Kernel\"` — use a narrow *Host Protocol from "
        f"dna.kernel.collaborator_ports instead."
    )
    assert ann.endswith("Host"), (
        f"{module}.{cls_name}.__init__ kernel annotation {ann!r} is not a narrow "
        f"*Host Protocol."
    )
