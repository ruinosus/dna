"""``OVERLAYABLE_FIELDS`` — the per-Kind allowlist of tenant-overridable fields.

Before this suite the allowlist was declared by exactly ONE Kind
(``GenomeKind``), read by exactly ONE consumer (the definitions read
use-case, to tell a portal which form inputs to enable) and enforced by
NOTHING — its own docstring promised enforcement "in
``_apply_package_field_overlay``", a function that has never existed in this
codebase. A value that looks like policy but is not is worse than no value:
the consumer greys out the inputs, and a direct API call writes anyway.

What is locked here:

* the DEFAULT is *unrestricted* (``None``) — a Kind that declares nothing
  places no per-field restriction, so enforcement landing does not silently
  freeze the spec of every Kind in the system;
* BOTH policy ports enforce it, with the postures they already use for
  ``LayerPolicy`` (write port raises, merge port drops-with-a-warning) —
  the i-049 lesson that a protection held on one port and not the other is
  a bug, not a design;
* the rule is *a non-allowlisted top-level spec key may not CHANGE the base
  value* — writing it back unchanged is a no-op, not a violation (the
  consumer submits the whole effective spec, read-only fields included);
* it composes with ``LayerPolicy`` by CONJUNCTION — neither can widen the
  other;
* any Kind can declare it from its ``.kind.yaml``, next to ``ui_schema``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio  # noqa: F401  (fixtures below are async)
import warnings
import yaml

from dna.kernel.compose.layer_policy import LayerPolicyEnforcer
from dna.kernel.compose.layer_resolver import DefaultLayerResolver
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import LayerPolicy, LayerPolicyViolationError


# ── the write port: LayerPolicyEnforcer ────────────────────────────────────


class _FakeDoc:
    def __init__(self, spec):
        self.spec = spec
        self.raw = {"spec": spec}


class _FakeMI:
    def __init__(self, policies_for_layer=None, existing=None):
        self._lp = policies_for_layer or []
        self._existing = existing

    def _all(self, kind):
        return self._lp if kind == "LayerPolicy" else []

    def _one(self, kind, name):
        return self._existing


class _FakePort:
    def __init__(self, overlayable_fields):
        self.OVERLAYABLE_FIELDS = overlayable_fields


class _FakeKernel:
    def __init__(self, non_overlayable=frozenset(), port=None):
        self._NON_OVERLAYABLE_KINDS = non_overlayable
        self._port = port

    def _alias_for(self, kind):
        return f"owner-{kind.lower()}"

    def kind_port_for(self, kind, *, api_version=None):
        return self._port


def _enforce(kernel, mi, *, kind="Skill", name="x", raw, layer=("tenant-a", "")):
    LayerPolicyEnforcer(kernel)._enforce(
        mi, "scope", kind, name, raw, layer,
        LayerPolicy=LayerPolicy, LayerPolicyViolationError=LayerPolicyViolationError,
    )


def _lp_doc(layer_id, alias, mode):
    return _FakeDoc({"layer_id": layer_id, "policies": {alias: mode}})


def test_kindbase_default_is_unrestricted():
    """The default must be "no per-field restriction", never "nothing is
    overlayable" — every Kind but one declares nothing, so an empty-set
    default would freeze the whole system the moment enforcement lands."""
    assert KindBase.OVERLAYABLE_FIELDS is None


def test_genome_allowlist_is_unchanged():
    """Back-compat: the one Kind that already declared an allowlist keeps
    declaring exactly the same four runtime-default fields."""
    from dna.extensions.helix import GenomeKind

    assert GenomeKind.OVERLAYABLE_FIELDS == frozenset(
        {"default_agent", "default_llm", "budget", "tags"}
    )


def test_write_port_rejects_change_to_field_outside_the_allowlist():
    kernel = _FakeKernel(port=_FakePort(frozenset({"instruction"})))
    mi = _FakeMI(existing=_FakeDoc({"instruction": "base", "model": "gpt-4"}))
    with pytest.raises(LayerPolicyViolationError, match=r"\[.model.\].*not overlayable"):
        _enforce(kernel, mi, raw={"spec": {"model": "claude"}})


def test_write_port_allows_change_to_an_allowlisted_field():
    kernel = _FakeKernel(port=_FakePort(frozenset({"instruction"})))
    mi = _FakeMI(existing=_FakeDoc({"instruction": "base", "model": "gpt-4"}))
    _enforce(kernel, mi, raw={"spec": {"instruction": "mine"}})


def test_write_port_allows_a_non_allowlisted_key_written_back_unchanged():
    """The consumer submits the WHOLE effective spec — read-only fields
    included, at their inherited values. That is not an override."""
    kernel = _FakeKernel(port=_FakePort(frozenset({"instruction"})))
    mi = _FakeMI(existing=_FakeDoc({"instruction": "base", "model": "gpt-4"}))
    _enforce(kernel, mi, raw={"spec": {"instruction": "mine", "model": "gpt-4"}})


def test_write_port_with_no_base_doc_requires_every_key_allowlisted():
    kernel = _FakeKernel(port=_FakePort(frozenset({"instruction"})))
    mi = _FakeMI(existing=None)
    with pytest.raises(LayerPolicyViolationError, match=r"\[.model.\].*not overlayable"):
        _enforce(kernel, mi, raw={"spec": {"model": "claude"}})


def test_write_port_undeclared_allowlist_is_unrestricted():
    kernel = _FakeKernel(port=_FakePort(None))
    mi = _FakeMI(existing=_FakeDoc({"a": 1}))
    _enforce(kernel, mi, raw={"spec": {"a": 2, "b": 3}})


def test_write_port_unregistered_kind_is_unrestricted():
    """No port (kind not registered on this kernel) → nothing to enforce."""
    kernel = _FakeKernel(port=None)
    mi = _FakeMI(existing=_FakeDoc({"a": 1}))
    _enforce(kernel, mi, raw={"spec": {"a": 2, "b": 3}})


def test_write_port_declared_empty_allowlist_blocks_every_change():
    kernel = _FakeKernel(port=_FakePort(frozenset()))
    mi = _FakeMI(existing=_FakeDoc({"a": 1}))
    with pytest.raises(LayerPolicyViolationError, match="not overlayable"):
        _enforce(kernel, mi, raw={"spec": {"a": 2}})


def test_locked_message_wins_over_the_field_allowlist():
    """Coarse before fine: a LOCKED Kind is refused as LOCKED, so the error
    names the broadest reason rather than an incidental field."""
    kernel = _FakeKernel(port=_FakePort(frozenset({"instruction"})))
    mi = _FakeMI(
        policies_for_layer=[_lp_doc("tenant-a", "owner-skill", "locked")],
        existing=_FakeDoc({"model": "gpt-4"}),
    )
    with pytest.raises(LayerPolicyViolationError, match="LOCKED"):
        _enforce(kernel, mi, raw={"spec": {"model": "claude"}})


def test_open_policy_does_not_unlock_a_non_allowlisted_field():
    """Conjunction: LayerPolicy decides WHETHER a Kind may be overlaid in a
    layer; the allowlist decides WHICH fields. Neither widens the other."""
    kernel = _FakeKernel(port=_FakePort(frozenset({"instruction"})))
    mi = _FakeMI(
        policies_for_layer=[_lp_doc("tenant-a", "owner-skill", "open")],
        existing=_FakeDoc({"model": "gpt-4"}),
    )
    with pytest.raises(LayerPolicyViolationError, match="not overlayable"):
        _enforce(kernel, mi, raw={"spec": {"model": "claude"}})


def test_timeline_is_exempt_from_the_allowlist():
    """Timeline events are append-only across overlays regardless of policy
    (ADR 2026-05-10) — the merge port concatenates them even onto a LOCKED
    instance. The allowlist must not become the one rule able to refuse the
    write that records them."""
    kernel = _FakeKernel(port=_FakePort(frozenset({"instruction"})))
    mi = _FakeMI(existing=_FakeDoc({"instruction": "base", "timeline": []}))
    _enforce(kernel, mi, raw={"spec": {"timeline": [{"at": "2026-01-01"}]}})


def test_structurally_non_overlayable_kind_still_raises_first():
    kernel = _FakeKernel(
        non_overlayable=frozenset({"Genome"}), port=_FakePort(frozenset({"tags"})),
    )
    with pytest.raises(LayerPolicyViolationError, match="non-overlayable"):
        _enforce(kernel, _FakeMI(), kind="Genome", raw={"spec": {"tags": ["x"]}})


# ── the merge port stays deliberately unenforced ───────────────────────────


def _base_doc(kind, spec):
    return {"apiVersion": "v1", "kind": kind, "metadata": {"name": "x"}, "spec": spec}


def _resolve(resolver, kind, base_spec, overlay_spec):
    class _Src:
        def load_layer(self, _scope, _lid, _lv):
            return [_base_doc(kind, overlay_spec)]

    return resolver.resolve(
        [_base_doc(kind, base_spec)], {"tenant": "acme"}, _Src(), "scope", {},
    )[0]["spec"]


def test_merge_port_does_not_apply_the_field_allowlist():
    """The asymmetry with LayerPolicy (enforced on BOTH ports) is a decision,
    not an oversight, so it is pinned here.

    A LayerPolicy doc is written by the scope OPERATOR and opted into per
    scope; re-applying it on merge only touches deployments that asked for
    it. ``OVERLAYABLE_FIELDS`` is declared globally by the Kind AUTHOR, so
    enforcing it on merge would retroactively rewrite overlays already stored
    in every deployment. The gate belongs on what a layer may AUTHOR."""
    resolver = DefaultLayerResolver(kind_aliases={"Skill": "owner-skill"})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        merged = _resolve(
            resolver, "Skill",
            {"instruction": "base", "model": "gpt-4"},
            {"instruction": "mine", "model": "claude"},
        )
    assert merged == {"instruction": "mine", "model": "claude"}


def test_a_tenant_published_genome_still_merges_its_non_allowlisted_identity():
    """The concrete feature that write-path-only enforcement protects.

    ``Genome`` declares an allowlist that excludes ``owner_tenant``, yet a
    tenant-published Genome exists precisely to declare it — the mechanism
    the allowlist was written to describe and the real one disagree, and only
    an unenforced allowlist let both survive. Enforcing on merge silently
    drops the field and the tenant Genome stops identifying its tenant
    (test_load_manifest_tenant_phase9 goes red)."""
    from dna.extensions.helix import GenomeKind

    assert "owner_tenant" not in GenomeKind.OVERLAYABLE_FIELDS
    resolver = DefaultLayerResolver(kind_aliases={"Genome": "helix-genome"})
    merged = _resolve(
        resolver, "Genome",
        {"visibility": "public"},
        {"visibility": "public", "owner_tenant": "acme"},
    )
    assert merged["owner_tenant"] == "acme"


# ── the descriptor: declarable from a .kind.yaml ───────────────────────────


def _descriptor(**spec_extra: Any) -> dict[str, Any]:
    return {
        "apiVersion": "github.com/ruinosus/dna/core/v1",
        "kind": "KindDefinition",
        "metadata": {"name": "overlay-test"},
        "spec": {
            "target_api_version": "overlaytest.example/v1",
            "target_kind": "OverlayTest",
            "alias": "overlaytest-overlay-test",
            "origin": "overlaytest.example",
            "storage": {"type": "yaml", "container": "overlay-tests"},
            **spec_extra,
        },
    }


def test_descriptor_can_declare_the_allowlist():
    from dna.kernel.meta import DeclarativeKindPort
    from dna.kernel.models import TypedKindDefinition

    typed = TypedKindDefinition.from_raw(
        _descriptor(overlayable_fields=["instruction", "model"])
    )
    port = DeclarativeKindPort(typed)
    assert port.OVERLAYABLE_FIELDS == frozenset({"instruction", "model"})


def test_descriptor_without_the_field_is_unrestricted():
    from dna.kernel.meta import DeclarativeKindPort
    from dna.kernel.models import TypedKindDefinition

    port = DeclarativeKindPort(TypedKindDefinition.from_raw(_descriptor()))
    assert port.OVERLAYABLE_FIELDS is None


def test_descriptor_rejects_a_non_list_allowlist():
    from dna.kernel.models import TypedKindDefinition

    with pytest.raises(ValueError, match="overlayable_fields must be a list"):
        TypedKindDefinition.from_raw(_descriptor(overlayable_fields="instruction"))


def test_published_schema_declares_overlayable_fields():
    from dna.kernel.kinds.schema import kind_definition_schema

    props = kind_definition_schema()["properties"]["spec"]["properties"]
    assert props["overlayable_fields"]["type"] == ["array", "null"]
    assert props["overlayable_fields"]["items"] == {"type": "string"}


# ── the consumer-visible payload: read_definition_impl ─────────────────────

_BASE = "dna-cloud"
_WID = "ws-overlay0000000000000001"


def _doc(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "github.com/ruinosus/dna/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def live(tmp_path: Path):
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.application.live import LiveDna
    from dna.kernel import Kernel

    base = tmp_path / ".dna"
    _write(base / _BASE / "Genome.yaml", _doc("Genome", _BASE, {}))
    _write(base / _BASE / "agents" / "assistant.yaml",
           _doc("Agent", "assistant", {"instruction": "Base agent.", "model": "gpt-4"}))
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_BASE, kernel=k, provider=None,
                   vendor_workspace=None, workspace_definitions_base=_BASE)


@pytest.mark.asyncio
async def test_read_reports_every_field_editable_for_an_undeclared_kind(live) -> None:
    """THE user-visible reason this work exists: ``Agent`` declares no
    allowlist, so a schema-driven editor must render its form EDITABLE — not
    a wall of disabled inputs. ``overlayable_fields`` is the resolved set the
    tenant may override, not the raw (usually absent) declaration."""
    from dna.application.runtime import read_definition_impl

    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["overlayable"] is True
    fields = set(out["overlayable_fields"])
    assert fields, "an undeclared Kind must not render a fully read-only form"
    assert set(out["ui_schema"]) <= fields
    assert {"instruction", "model"} <= fields


@pytest.mark.asyncio
async def test_read_reports_only_the_declared_fields_when_a_kind_declares(
    live, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dna.application.runtime import read_definition_impl

    port = live.kernel.kind_port_for("Agent")
    monkeypatch.setattr(port, "OVERLAYABLE_FIELDS", frozenset({"instruction"}))
    out = await read_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant")
    assert out["overlayable_fields"] == ["instruction"]


@pytest.mark.asyncio
async def test_apply_is_vetoed_end_to_end_for_a_non_allowlisted_field(
    live, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The declaration reaches the actual write path, not just a unit fake."""
    from dna.application.runtime import apply_definition_impl

    port = live.kernel.kind_port_for("Agent")
    monkeypatch.setattr(port, "OVERLAYABLE_FIELDS", frozenset({"instruction"}))
    with pytest.raises(LayerPolicyViolationError, match="not overlayable"):
        await apply_definition_impl(
            live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant",
            spec={"instruction": "Base agent.", "model": "claude"})
    # …and the allowlisted field still writes.
    await apply_definition_impl(
        live, scope=_BASE, tenant=_WID, kind="Agent", name="assistant",
        spec={"instruction": "Mine.", "model": "gpt-4"})
