"""Tests for LayerPolicy enforcement in kernel.write_document."""
from __future__ import annotations

import pytest


def test_layer_policy_violation_error_is_importable():
    from dna.kernel.protocols import LayerPolicyViolationError
    assert issubclass(LayerPolicyViolationError, Exception)


def test_layer_policy_violation_error_carries_message():
    from dna.kernel.protocols import LayerPolicyViolationError
    err = LayerPolicyViolationError("test reason")
    assert str(err) == "test reason"


def test_writable_source_port_save_accepts_layer_kwarg():
    """Protocol contract: save_document signature accepts optional layer kwarg."""
    import inspect
    from dna.kernel.protocols import WritableSourcePort
    sig = inspect.signature(WritableSourcePort.save_document)
    params = sig.parameters
    assert "layer" in params
    assert params["layer"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["layer"].default is None


def test_writable_source_port_delete_accepts_layer_kwarg():
    import inspect
    from dna.kernel.protocols import WritableSourcePort
    sig = inspect.signature(WritableSourcePort.delete_document)
    params = sig.parameters
    assert "layer" in params
    assert params["layer"].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["layer"].default is None


def test_kernel_write_document_forwards_layer_to_adapter(tmp_path):
    """Kernel.write_document forwards layer kwarg to the adapter."""
    import asyncio
    from dna.kernel import Kernel

    k = Kernel()

    # Fake writable source that records kwargs
    class FakeWritable:
        def __init__(self):
            self.save_calls = []
            self.delete_calls = []

        async def save_document(self, scope, kind, name, raw, author=None, *, layer=None):
            self.save_calls.append({"scope": scope, "kind": kind, "name": name, "author": author, "layer": layer})
            return "v1"

        async def delete_document(self, scope, kind, name, *, layer=None):
            self.delete_calls.append({"scope": scope, "kind": kind, "name": name, "layer": layer})

        # Required by _require_writable_source type check (SourcePort methods)
        @property
        def supports_readers(self):
            return False

        async def load_bootstrap_docs(self, scope, *, tenant=None):
            return []

        async def load_all(self, scope, readers=None):
            return []

        async def resolve_ref(self, scope, ref):
            return ref

        async def load_layer(self, scope, layer_id, layer_value, readers=None):
            return []

        async def close(self):
            return None

        async def save_manifest(self, scope, manifest):
            return "v1"

        async def list_versions(self, scope, kind, name):
            return []

        async def get_version(self, scope, kind, name, version_id):
            return {}

        async def publish(self, scope, kind, name):
            return "v1"

        async def load_drafts(self, scope):
            return []

        async def list_scopes(self):
            return []

        async def capabilities(self):
            return {}

        async def list_doc_refs(self, scope, *, kind=None, tenant=None):
            return []

        async def load_one(self, scope, kind, name, *, readers=None, tenant=None):
            return None

        async def query(
            self, scope, kind, *,
            filter=None, projection=None, limit=None, offset=None,
            order_by=None, tenant=None,
        ):
            if False:
                yield {}

        async def count(self, scope, kind, *, filter=None, group_by=None, tenant=None):
            # F2 — count is a SourcePort member now; runtime_checkable
            # isinstance(WritableSourcePort) requires it on the fake.
            return {"total": 0, "groups": None}

    fake = FakeWritable()

    # Force isinstance(fake, WritableSourcePort) to return True by runtime protocol check
    # Since WritableSourcePort is @runtime_checkable, duck-typing via matching methods should work.
    k._source = fake

    raw = {"apiVersion": "x", "kind": "K", "metadata": {"name": "n"}, "spec": {}}
    asyncio.run(k.write_document("s", "K", "n", raw, layer=("tenant", "T1"), skip_hooks=True))

    assert len(fake.save_calls) == 1
    assert fake.save_calls[0]["layer"] == ("tenant", "T1")

    asyncio.run(k.delete_document("s", "K", "n", layer=("tenant", "T1"), skip_hooks=True))
    assert len(fake.delete_calls) == 1
    assert fake.delete_calls[0]["layer"] == ("tenant", "T1")


# ---------------------------------------------------------------------------
# Task 5 — _check_layer_policy enforcement tests
# ---------------------------------------------------------------------------


def _make_scope(tmp_path, module_layers_yaml: str):
    """Create a minimal scope dir with a Genome + LayerPolicy doc.

    Phase 16 — overlay rules now live in ``policies/<id>.yaml`` as
    ``LayerPolicy`` docs (not ``Module.spec.layers``). The
    ``module_layers_yaml`` argument retains its dict-of-dicts shape
    (``tenant: helix-agent: locked``) for back-compat with
    callsites; we extract the (layer_id, alias, policy) tuples and
    write them as LayerPolicy docs.
    """
    import yaml
    scope_dir = tmp_path / "s"
    scope_dir.mkdir()
    # Minimal Genome as the scope-root identity doc.
    (scope_dir / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n"
        "  name: s\n"
        "spec: {}\n"
    )
    # Parse the legacy "layers: ..." snippet into LayerPolicy docs.
    parsed = yaml.safe_load("spec:\n" + module_layers_yaml)
    layers = (parsed or {}).get("spec", {}).get("layers") or {}
    if isinstance(layers, dict):
        policies_dir = scope_dir / "policies"
        policies_dir.mkdir(exist_ok=True)
        for layer_id, alias_to_policy in layers.items():
            if not isinstance(alias_to_policy, dict):
                continue
            (policies_dir / f"{layer_id}.yaml").write_text(yaml.safe_dump({
                "apiVersion": "github.com/ruinosus/dna/policy/v1",
                "kind": "LayerPolicy",
                "metadata": {"name": f"{layer_id}-default"},
                "spec": {
                    "layer_id": layer_id,
                    "policies": dict(alias_to_policy),
                },
            }, sort_keys=False))
    return tmp_path


def _kernel_with_fs(tmp_path):
    from dna.kernel import Kernel
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    k = Kernel()
    k.load(HelixExtension())
    src = FilesystemWritableSource(tmp_path, kernel=k)
    k.source(src)
    k.cache(FilesystemCache(tmp_path / ".dna-cache"))
    return k


def test_policy_locked_rejects_any_write(tmp_path):
    import asyncio
    from dna.kernel.protocols import LayerPolicyViolationError
    _make_scope(tmp_path, "  layers:\n    tenant:\n      helix-agent: locked\n")
    k = _kernel_with_fs(tmp_path)
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {"description": "hi"},
    }
    with pytest.raises(LayerPolicyViolationError, match="LOCKED"):
        asyncio.run(k.write_document("s", "Agent", "x", raw, layer=("tenant", "T1")))


def test_policy_open_allows_write(tmp_path):
    """OPEN policy lets the write go through without raising.

    NOTE: We don't assert on layer-file persistence here because
    FilesystemWritableSource layer routing is Task 6 in this chunk.
    Task 5 scope: policy check must not raise on OPEN.
    """
    import asyncio
    _make_scope(tmp_path, "  layers:\n    tenant:\n      helix-agent: open\n")
    k = _kernel_with_fs(tmp_path)
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {"description": "hi"},
    }
    # Must not raise
    asyncio.run(k.write_document("s", "Agent", "x", raw, layer=("tenant", "T1")))


def test_policy_no_module_defaults_to_open(tmp_path):
    """Scope without Module doc: policy check is a no-op (defaults OPEN)."""
    import asyncio
    (tmp_path / "s").mkdir()
    k = _kernel_with_fs(tmp_path)
    raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {},
    }
    # Should not raise
    asyncio.run(k.write_document("s", "Agent", "x", raw, layer=("tenant", "T1")))


def test_policy_restricted_rejects_add_of_new_doc(tmp_path):
    import asyncio
    from dna.kernel.protocols import LayerPolicyViolationError
    _make_scope(tmp_path, "  layers:\n    tenant:\n      helix-agent: restricted\n")
    k = _kernel_with_fs(tmp_path)
    # Don't write the base doc — tenant tries to add a new doc to its layer
    new_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "new"},
        "spec": {"description": "x"},
    }
    with pytest.raises(LayerPolicyViolationError, match="RESTRICTED.*cannot add"):
        asyncio.run(k.write_document("s", "Agent", "new", new_raw, layer=("tenant", "T1")))


def test_policy_restricted_allows_override_of_existing_doc(tmp_path):
    import asyncio
    _make_scope(tmp_path, "  layers:\n    tenant:\n      helix-agent: restricted\n")
    k = _kernel_with_fs(tmp_path)
    # Write base first
    base_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "existing"},
        "spec": {"model": "gpt-4o-mini"},
    }
    asyncio.run(k.write_document("s", "Agent", "existing", base_raw))
    # Override in tenant layer — only changing existing keys → allowed
    override_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "existing"},
        "spec": {"model": "gpt-5-mini"},
    }
    asyncio.run(k.write_document("s", "Agent", "existing", override_raw, layer=("tenant", "T1")))


def test_policy_restricted_rejects_new_top_level_spec_key(tmp_path):
    import asyncio
    from dna.kernel.protocols import LayerPolicyViolationError
    _make_scope(tmp_path, "  layers:\n    tenant:\n      helix-agent: restricted\n")
    k = _kernel_with_fs(tmp_path)
    base_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {"model": "gpt-4o-mini"},
    }
    asyncio.run(k.write_document("s", "Agent", "x", base_raw))
    # Overlay adds a NEW_KEY that doesn't exist in base
    added_raw = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": "x"},
        "spec": {"model": "gpt-4o-mini", "NEW_KEY": 1},
    }
    with pytest.raises(LayerPolicyViolationError, match="new top-level spec keys"):
        asyncio.run(k.write_document("s", "Agent", "x", added_raw, layer=("tenant", "T1")))
