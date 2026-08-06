"""A LAZY boot must confer the same Kind registry an eager one does.

``instance_async(scope, lazy=True)`` exists to skip the full ``load_all``
materialization of a scope's instances — the MI delegates ``all``/``one`` to
``kernel.query`` instead of holding parsed instances. That is a trade about
INSTANCES. It was silently also a trade about KINDS: the lazy branch loaded the
bootstrap instances (``load_bootstrap_docs`` — ``KindDefinition`` first, by
declared priority) and parsed them, but never ran the registration pass, so no
store-declared ``KindDefinition`` ever produced a port.

Everything that reads the registry therefore answered "that Kind does not
exist" on a lazily-booted kernel — including the generic instance use-cases in
``dna.application.instances``, which resolve their target through
``ports_in_scope``. Registration is what confers **schema validation** and
**storage routing**, so this is not a cosmetic difference between two boot
modes: on a lazy boot an approved Kind governs nothing.

What this file pins:

* the registry a lazy boot leaves behind is the one an eager boot leaves behind
  (the port, its apiVersion, its schema, its declared container);
* and it is EFFECTIVE — a violating instance is vetoed and a conforming one is
  routed into the declared container, measured on disk;
* the approval gate is untouched: an unapproved ``KindDefinition`` is still not
  registered by a lazy boot (registration is the gate; a lazy boot that
  registered everything would quietly repeal it);
* i-081 is untouched: a Kind declared by scope A's store is invisible to scope
  B, whether A was booted lazily or eagerly.

The lazy path deliberately does NOT run the declarative-kind rescan the eager
path runs after registration (``_rescan_after_kinddef_register_async``): that
rescan re-reads every instance in the scope, which is precisely the cost lazy
exists to avoid, and a lazy MI holds no instance list for it to enrich. What it
does need is the READER side effect of registration, which the registration
pass itself installs on the kernel.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod
from dna.kernel.protocols import SpecValidationError

_A = "scope-a"
_B = "scope-b"
_NS = "acme.example"
_API = f"{_NS}/v1"
_SCHEMA = {
    "type": "object",
    "required": ["title"],
    "properties": {"title": {"type": "string"}},
    "additionalProperties": False,
}


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


def _kinddef(
    *, namespace: str, kind: str, alias: str, container: str,
    approved_by: str | None = "approver@example.com",
) -> dict:
    spec: dict = {
        "target_api_version": f"{namespace}/v1",
        "target_kind": kind,
        "alias": alias,
        "origin": namespace,
        "storage": {"type": "yaml", "container": container},
        "schema": _SCHEMA,
    }
    if approved_by:
        spec["approved_by"] = approved_by
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": alias},
        "spec": spec,
    }


#: The SECOND door onto the same registry: ``custom_kinds`` on the scope's root
#: instance. Same store, same approval gate, same scope binding — and a lazy
#: boot that wired only the ``KindDefinition`` door would leave half the
#: mechanism dark. Declared in pairs (one approved, one not) so the gate is
#: measured on this door too and not merely assumed to be shared.
_CUSTOM_KINDS = [
    {"apiVersion": "acme.example/v1", "kind": "Gadget",
     "alias": "acme-gadget", "approved_by": "approver@example.com"},
    {"apiVersion": "acme.example/v1", "kind": "Gizmo",
     "alias": "acme-gizmo"},
]


def _genome(scope: str, *, custom_kinds: list | None = None) -> dict:
    spec: dict = {"description": f"fixture scope {scope}"}
    if custom_kinds:
        spec["custom_kinds"] = custom_kinds
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": scope},
        "spec": spec,
    }


def _doc(kind: str, name: str, spec: dict) -> dict:
    return {
        "apiVersion": _API,
        "kind": kind,
        "metadata": {"name": name},
        "spec": spec,
    }


def _write_yaml(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _base_with(tmp_path: Path, *, approved: bool = True) -> Path:
    """``scope-a`` declares ``Widget``; ``scope-b`` declares nothing."""
    base = tmp_path / ".dna"
    _write_yaml(
        base / _A / "Genome.yaml", _genome(_A, custom_kinds=_CUSTOM_KINDS),
    )
    _write_yaml(base / _B / "Genome.yaml", _genome(_B))
    _write_yaml(
        base / _A / "kinds" / "widget.yaml",
        _kinddef(
            namespace=_NS, kind="Widget", alias="acme-widget",
            container="widgets",
            approved_by="approver@example.com" if approved else None,
        ),
    )
    return base


def _kernel(base: Path) -> Kernel:
    return Kernel.auto(FilesystemWritableSource(str(base)))


# ── the gap ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_lazy_boot_registers_the_scopes_own_approved_kind(tmp_path):
    """The one fact the whole file rests on: after ``lazy=True`` the port is
    there, and it is the port the store declared — not merely a truthy object.

    Asserted through ``kind_port_for(scope=...)`` AND through the kinds map the
    lazy MI itself was handed, because the two are read by different consumers
    (the write pipeline reads the registry; plane routing and parsing read the
    MI's map) and a fix that satisfied only one would leave the other blind."""
    base = _base_with(tmp_path)
    k = _kernel(base)

    mi = await k.instance_async(_A, lazy=True)
    assert mi._lazy is True, "the fixture stopped exercising the lazy branch"

    port = k.kind_port_for("Widget", scope=_A)
    assert port is not None, (
        "a lazy boot left the scope's own approved Kind unregistered — every "
        "registry consumer will answer 'Kind not registered on this source'"
    )
    assert port.api_version == _API, port.api_version
    assert port.schema() == _SCHEMA, port.schema()
    assert getattr(port.storage, "container", None) == "widgets", port.storage
    assert (_API, "Widget") in mi._kinds, sorted(mi._kinds)


@pytest.mark.asyncio
async def test_a_lazy_boot_and_an_eager_boot_agree_on_the_registry(tmp_path):
    """Not "the lazy boot registers something" but "it registers the SAME
    thing". Two kernels over the same store, one booted each way; the
    (apiVersion, kind) keys of the scope's map must match exactly.

    Compared as sets of keys rather than object identity: the ports are
    synthesized per kernel, so identity would be a false negative, while an
    equal key set is what every lookup in the system actually resolves on."""
    base = _base_with(tmp_path)

    lazy_k = _kernel(base)
    await lazy_k.instance_async(_A, lazy=True)
    eager_k = _kernel(base)
    await eager_k.instance_async(_A, lazy=False)

    assert set(lazy_k.kinds_for_scope(_A)) == set(eager_k.kinds_for_scope(_A))
    # …and the difference is not vacuous: the declarative Kind is IN that set.
    assert (_API, "Widget") in set(eager_k.kinds_for_scope(_A))


@pytest.mark.asyncio
async def test_a_lazily_booted_kind_validates_and_routes(tmp_path):
    """Registration is only worth having because of what it confers. Both
    halves are measured — the veto on the write, the container on disk — since
    a registry entry that governed nothing would satisfy the test above."""
    base = _base_with(tmp_path)
    k = _kernel(base)
    await k.instance_async(_A, lazy=True)

    with pytest.raises(SpecValidationError) as vetoed:
        await k.write_instance(_A, "Widget", "bad", _doc("Widget", "bad", {"nope": 1}))
    assert "schema validation failed" in str(vetoed.value), str(vetoed.value)

    await k.write_instance(_A, "Widget", "ok", _doc("Widget", "ok", {"title": "fine"}))
    assert (base / _A / "widgets" / "ok.yaml").exists(), sorted(
        p.relative_to(base) for p in (base / _A).rglob("*.yaml")
    )


@pytest.mark.asyncio
async def test_the_generic_document_use_cases_resolve_it_after_a_lazy_boot(
    tmp_path,
):
    """The consumer that motivated this: ``dna.application.instances`` resolves
    its target through ``ports_in_scope``, which reads the same registry. This
    is the SDK-side twin of what the MCP generic tools do — no ``dna_cli``
    import, per the package boundary."""
    from dna.kernel.kinds.registry import ports_in_scope

    base = _base_with(tmp_path)
    k = _kernel(base)
    await k.instance_async(_A, lazy=True)

    names = {p.kind for p in ports_in_scope(k, _A)}
    assert "Widget" in names, sorted(names)


@pytest.mark.asyncio
async def test_a_lazy_boot_wires_the_other_registry_door_too(tmp_path):
    """``custom_kinds`` on the scope's root instance is the second store-loaded
    door onto the registry, and it needs no new file — whoever may write the
    root instance declares Kinds through it. A lazy boot that wired only the
    ``KindDefinition`` door would leave a Kind declared this way invisible for
    exactly the same reason, so it is asserted rather than inferred from
    "they share a funnel" (they do not — they are two methods).

    The unapproved half of the pair is the control: the gate on this door is
    PER ENTRY, so one root instance can carry both, and a lazy boot that
    registered the whole list would repeal it."""
    base = _base_with(tmp_path)
    k = _kernel(base)
    await k.instance_async(_A, lazy=True)

    assert k.kind_port_for("Gadget", scope=_A) is not None, (
        "a custom_kinds entry declared by the scope's root instance and "
        "approved is not registered by a lazy boot"
    )
    assert k.kind_port_for("Gizmo", scope=_A) is None, (
        "a lazy boot registered an UNAPPROVED custom_kinds entry"
    )
    assert k.kind_port_for("Gadget", scope=_B) is None, "i-081, second door"


# ── what must NOT change ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_lazy_boot_does_not_register_an_unapproved_kind(tmp_path):
    """The approval gate lives INSIDE the registration pass, so wiring that
    pass into the lazy boot could only repeal it by accident — which is exactly
    why it is asserted rather than assumed.

    The control is the same fixture with ``spec.approved_by`` removed: the
    instance is there, it parses, and it still confers nothing."""
    base = _base_with(tmp_path, approved=False)
    k = _kernel(base)
    await k.instance_async(_A, lazy=True)

    assert k.kind_port_for("Widget", scope=_A) is None, (
        "a lazy boot registered an UNAPPROVED Kind — the approval gate is the "
        "absence of registration, so this is the gate being repealed"
    )
    # …and the consequence, not just the symptom: nothing validates the write.
    await k.write_instance(_A, "Widget", "bad", _doc("Widget", "bad", {"nope": 1}))
    assert not (base / _A / "widgets" / "bad.yaml").exists()


@pytest.mark.asyncio
async def test_a_lazily_booted_kind_still_binds_only_to_its_own_scope(tmp_path):
    """i-081, through the lazy door. The registry key carries no scope, so the
    binding is a property of HOW the registration pass is called; a lazy boot
    that passed the wrong scope (or none) would re-open the process-wide leak
    that issue closed, and this is the direction that would show it."""
    base = _base_with(tmp_path)
    k = _kernel(base)

    await k.instance_async(_A, lazy=True)
    await k.instance_async(_B, lazy=True)

    assert k.kind_port_for("Widget", scope=_A) is not None
    assert k.kind_port_for("Widget", scope=_B) is None, (
        "scope B sees a Kind only scope A's store declared"
    )
    # The consequence in B: an unknown Kind, so no foreign schema governs it
    # and no foreign container routes it.
    await k.write_instance(_B, "Widget", "b1", _doc("Widget", "b1", {"nope": 1}))
    assert not (base / _B / "widgets" / "b1.yaml").exists()
