"""Phase 16 — kernel layer policy enforcement tests.

Covers the new semantics introduced by scope segregation:

- ``_NON_OVERLAYABLE_KINDS`` allowlist hard-locks Genome /
  KindDefinition / LayerPolicy regardless of declared policy.
- ``LayerPolicy`` docs (Phase 16 canonical) override the legacy
  ``Module.spec.layers`` field when both declare a policy for the
  same (layer_id, alias) tuple.
- ``LayerPolicy`` docs alone (no Module.spec.layers) drive enforcement.

Uses a mock filesystem source so tests are hermetic and fast.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.protocols import LayerPolicy, LayerPolicyViolationError


# ---------------------------------------------------------------------------
# Fixtures — fake writable filesystem source that holds raw docs in memory.
# ---------------------------------------------------------------------------


class _MemorySource:
    """Minimal in-memory WritableSourcePort for layer-policy tests.

    Enough surface to satisfy ``Kernel.instance_async`` and
    ``Kernel.write_document``: load_bootstrap_docs, load_all, load_layer,
    save_document, delete_document, plus stubs for the other
    WritableSourcePort methods.
    """

    def __init__(self, manifest_doc, scope_docs=None):
        self.manifest_doc = manifest_doc
        self.scope_docs = list(scope_docs or [])
        self.save_calls: list[dict] = []
        self.delete_calls: list[dict] = []

    @property
    def supports_readers(self) -> bool:
        return False

    async def load_bootstrap_docs(self, scope, *, tenant=None):
        from dna.kernel.protocols import BOOTSTRAP_KIND_NAMES
        out = []
        if isinstance(self.manifest_doc, dict) and self.manifest_doc.get("kind") in (
            *BOOTSTRAP_KIND_NAMES, "Module",
        ):
            out.append(self.manifest_doc)
        for d in self.scope_docs:
            if d.get("kind") in BOOTSTRAP_KIND_NAMES:
                out.append(d)
        return out

    async def load_all(self, scope, readers=None):
        # Real source adapters scan the same scope dir twice (bootstrap
        # for the root file + load_all walks it recursively too via rglob),
        # so the manifest doc shows up in BOTH. Mirror that here so
        # `mi.root` finds the Genome doc.
        out = []
        if isinstance(self.manifest_doc, dict) and self.manifest_doc.get("kind"):
            out.append(self.manifest_doc)
        out.extend(self.scope_docs)
        return out

    async def resolve_ref(self, scope, ref):
        return ""

    async def load_layer(self, scope, layer_id, layer_value, readers=None):
        return []

    async def list_doc_refs(self, scope, *, kind=None, tenant=None):
        out = await self.load_all(scope)
        return [(d.get("kind"), (d.get("metadata") or {}).get("name")) for d in out]

    async def load_one(self, scope, kind, name, *, readers=None, tenant=None):
        for d in await self.load_all(scope):
            if d.get("kind") == kind and (d.get("metadata") or {}).get("name") == name:
                return d
        return None

    async def query(
        self, scope, kind, *,
        filter=None, projection=None, limit=None, offset=None,
        order_by=None, tenant=None,
    ):
        from dna.kernel.query_fallback import query_via_load_all
        async for row in query_via_load_all(
            self, scope, kind,
            filter=filter, projection=projection, limit=limit,
            offset=offset, order_by=order_by, tenant=tenant,
        ):
            yield row

    async def count(self, scope, kind, *, filter=None, group_by=None, tenant=None):
        # F2 — count is a SourcePort member now; runtime_checkable
        # isinstance(WritableSourcePort) requires it on the fake.
        from dna.kernel.query_fallback import count_via_query
        return await count_via_query(
            self, scope, kind, filter=filter, group_by=group_by, tenant=tenant,
        )

    async def close(self) -> None:
        return None

    async def save_document(
        self, scope, kind, name, raw, author=None,
        *, tenant=None, layer=None,
    ):
        self.save_calls.append(
            {"scope": scope, "kind": kind, "name": name,
             "tenant": tenant, "layer": layer}
        )
        return "v1"

    async def delete_document(
        self, scope, kind, name, *, tenant=None, layer=None,
    ):
        self.delete_calls.append(
            {"scope": scope, "kind": kind, "name": name,
             "tenant": tenant, "layer": layer}
        )

    async def save_manifest(self, scope, manifest):
        return "v1"

    async def list_versions(self, scope, kind, name):
        return []

    async def get_version(self, scope, kind, name, version_id):
        return {}

    async def publish(self, scope, kind, name):
        return ""

    async def load_drafts(self, scope):
        return []

    async def list_scopes(self):
        return ["test-scope"]

    async def capabilities(self):
        return {}


def _module_doc_with_layers(layers_spec):
    """Build a Module raw doc with the given spec.layers field."""
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Genome",
        "metadata": {"name": "test-scope"},
        "spec": {"layers": layers_spec or []},
    }


def _layer_policy_doc(name, layer_id, policies):
    """Build a LayerPolicy raw doc for filesystem `policies/` directory."""
    return {
        "apiVersion": "github.com/ruinosus/dna/policy/v1",
        "kind": "LayerPolicy",
        "metadata": {"name": name},
        "spec": {"layer_id": layer_id, "policies": policies},
    }


def _build_kernel_with_source(source):
    """Wire a Kernel with the given source + a no-op cache."""
    from dna.adapters.filesystem import FilesystemCache

    k = Kernel()
    k.source(source)
    # FilesystemCache requires a path; tests don't actually populate it.
    import tempfile
    k.cache(FilesystemCache(tempfile.mkdtemp(prefix="dna-test-")))
    # Load all the standard extensions so Module / Genome / LayerPolicy
    # / Agent kinds are registered. Mirrors Kernel.quick().
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())
    return k


# ---------------------------------------------------------------------------
# Allowlist of non-overlayable Kinds
# ---------------------------------------------------------------------------


class TestNonOverlayableKindsAllowlist:
    def test_module_constant_contains_expected_kinds(self) -> None:
        # Now a DERIVED instance property (s-kernel-kindport-classification-attrs):
        # read it off a fully-loaded kernel instead of the class.
        assert Kernel.auto()._NON_OVERLAYABLE_KINDS == frozenset(
            {"Genome", "KindDefinition", "LayerPolicy"}
        )

    @pytest.mark.asyncio
    async def test_package_write_to_layer_raises(self) -> None:
        source = _MemorySource(_module_doc_with_layers([]))
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "test-scope"},
            "spec": {"version": "1.0.0"},
        }
        with pytest.raises(LayerPolicyViolationError, match="non-overlayable"):
            await k.write_document(
                "test-scope", "Genome", "test-scope", raw,
                layer=("tenant", "acme"),
            )
        assert source.save_calls == []  # write never reached the adapter

    @pytest.mark.asyncio
    async def test_kinddefinition_write_to_layer_raises(self) -> None:
        source = _MemorySource(_module_doc_with_layers([]))
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "dna.kind/v1",
            "kind": "KindDefinition",
            "metadata": {"name": "MyKind"},
            "spec": {"target_kind": "MyKind", "target_api_version": "demo/v1", "alias": "demo-mykind"},
        }
        with pytest.raises(LayerPolicyViolationError, match="non-overlayable"):
            await k.write_document(
                "test-scope", "KindDefinition", "MyKind", raw,
                layer=("tenant", "acme"),
            )

    @pytest.mark.asyncio
    async def test_layerpolicy_write_to_layer_raises(self) -> None:
        source = _MemorySource(_module_doc_with_layers([]))
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/policy/v1",
            "kind": "LayerPolicy",
            "metadata": {"name": "tenant-default"},
            "spec": {"layer_id": "tenant", "policies": {"helix-agent": "open"}},
        }
        with pytest.raises(LayerPolicyViolationError, match="non-overlayable"):
            await k.write_document(
                "test-scope", "LayerPolicy", "tenant-default", raw,
                layer=("tenant", "acme"),
            )

    @pytest.mark.asyncio
    async def test_package_write_to_base_succeeds(self) -> None:
        # Writes to the base layer (layer=None) bypass the allowlist —
        # the allowlist only restricts overlay writes.
        source = _MemorySource(_module_doc_with_layers([]))
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Genome",
            "metadata": {"name": "test-scope"},
            "spec": {"version": "1.0.0"},
        }
        await k.write_document(
            "test-scope", "Genome", "test-scope", raw, layer=None,
        )
        assert len(source.save_calls) == 1
        assert source.save_calls[0]["layer"] is None

    @pytest.mark.asyncio
    async def test_agent_write_to_layer_unaffected_by_allowlist(self) -> None:
        # Agent is overlayable. Allowlist must not interfere.
        source = _MemorySource(_module_doc_with_layers([]))
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "you are brad"},
        }
        await k.write_document(
            "test-scope", "Agent", "brad", raw,
            layer=("tenant", "acme"),
        )
        assert len(source.save_calls) == 1


# ---------------------------------------------------------------------------
# LayerPolicy docs drive enforcement
# ---------------------------------------------------------------------------


class TestLayerPolicyDocsEnforcement:
    @pytest.mark.asyncio
    async def test_layerpolicy_doc_locks_agent(self) -> None:
        # No Module.spec.layers; LayerPolicy doc declares LOCKED.
        manifest = _module_doc_with_layers([])
        scope_docs = [
            _layer_policy_doc(
                "tenant-default",
                "tenant",
                {"helix-agent": "locked"},
            ),
        ]
        source = _MemorySource(manifest, scope_docs=scope_docs)
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "tweaked"},
        }
        with pytest.raises(LayerPolicyViolationError, match="LOCKED"):
            await k.write_document(
                "test-scope", "Agent", "brad", raw,
                layer=("tenant", "acme"),
            )

    @pytest.mark.asyncio
    async def test_layerpolicy_doc_open_allows_write(self) -> None:
        manifest = _module_doc_with_layers([])
        scope_docs = [
            _layer_policy_doc(
                "tenant-default",
                "tenant",
                {"helix-agent": "open"},
            ),
        ]
        source = _MemorySource(manifest, scope_docs=scope_docs)
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "tweaked"},
        }
        await k.write_document(
            "test-scope", "Agent", "brad", raw,
            layer=("tenant", "acme"),
        )
        assert len(source.save_calls) == 1

    @pytest.mark.asyncio
    async def test_layerpolicy_doc_filters_by_layer_id(self) -> None:
        # Policy declares LOCKED for "branch" layer, not "tenant" —
        # writes to tenant layer succeed.
        manifest = _module_doc_with_layers([])
        scope_docs = [
            _layer_policy_doc(
                "branch-rules",
                "branch",
                {"helix-agent": "locked"},
            ),
        ]
        source = _MemorySource(manifest, scope_docs=scope_docs)
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "x"},
        }
        # tenant layer is unrestricted (no policy declared for tenant).
        await k.write_document(
            "test-scope", "Agent", "brad", raw,
            layer=("tenant", "acme"),
        )
        assert len(source.save_calls) == 1


# ---------------------------------------------------------------------------
# Conflict resolution: LayerPolicy doc wins over Module.spec.layers
# ---------------------------------------------------------------------------


class TestLayerPolicyConflictResolution:
    @pytest.mark.asyncio
    async def test_layerpolicy_doc_wins_over_module_spec_layers(self) -> None:
        # Module says OPEN, LayerPolicy doc says LOCKED — LayerPolicy wins.
        # Dict-format spec.layers (the format _enforce_layer_policy_with_mi
        # reads directly): {layer_id: {alias: policy}}.
        manifest = _module_doc_with_layers(
            {"tenant": {"helix-agent": "open"}}
        )
        scope_docs = [
            _layer_policy_doc(
                "tenant-default",
                "tenant",
                {"helix-agent": "locked"},
            ),
        ]
        source = _MemorySource(manifest, scope_docs=scope_docs)
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "x"},
        }
        with pytest.raises(LayerPolicyViolationError, match="LOCKED"):
            await k.write_document(
                "test-scope", "Agent", "brad", raw,
                layer=("tenant", "acme"),
            )

    # Phase 16 commit 4 — legacy Module.spec.layers fallback REMOVED.
    # The previous test ``test_module_spec_layers_used_when_no_layer_policy_doc``
    # is intentionally deleted. LayerPolicy docs are the only source
    # of truth for overlay rules now.

    @pytest.mark.asyncio
    async def test_no_policy_anywhere_defaults_to_open(self) -> None:
        manifest = _module_doc_with_layers([])
        source = _MemorySource(manifest, scope_docs=[])
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "x"},
        }
        # Should succeed.
        await k.write_document(
            "test-scope", "Agent", "brad", raw,
            layer=("tenant", "acme"),
        )
        assert len(source.save_calls) == 1


# ---------------------------------------------------------------------------
# Empty / no-op cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_no_module_doc_at_all(self) -> None:
        # Source has no Module / no Genome / no LayerPolicy. Writes to
        # base succeed; writes to overlay default to OPEN (no policy).
        source = _MemorySource({})  # empty manifest
        k = _build_kernel_with_source(source)
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Agent",
            "metadata": {"name": "brad"},
            "spec": {"instruction": "x"},
        }
        await k.write_document(
            "test-scope", "Agent", "brad", raw,
            layer=("tenant", "acme"),
        )
        assert len(source.save_calls) == 1

    def test_LayerPolicy_enum_values(self) -> None:
        assert LayerPolicy.OPEN.value == "open"
        assert LayerPolicy.RESTRICTED.value == "restricted"
        assert LayerPolicy.LOCKED.value == "locked"
