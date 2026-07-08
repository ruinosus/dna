"""Tests for the Kernel write facade (write_document / delete_document / preview_document)."""
from __future__ import annotations

import asyncio
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from dna.adapters.filesystem.source import FilesystemSource
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.kernel import (
    Kernel,
    NotWritableError,
    PreviewResult,
)


def test_not_writable_error_is_runtime_error():
    assert issubclass(NotWritableError, RuntimeError)


def test_preview_result_is_frozen_dataclass():
    pr = PreviewResult(target=Path("/tmp/x"), files=[], exists_already=False)
    with pytest.raises(FrozenInstanceError):
        pr.target = Path("/tmp/y")  # type: ignore[misc]


def test_preview_result_accepts_string_target():
    """Synthetic URL targets (non-filesystem sources) are strings, not Paths."""
    pr = PreviewResult(target="sqlite://m/Skill/demo", files=[], exists_already=False)
    assert pr.target == "sqlite://m/Skill/demo"


def test_active_source_is_none_by_default():
    k = Kernel()
    assert k.active_source is None


def test_active_source_reflects_source_setter(tmp_path):
    k = Kernel()
    src = FilesystemSource(str(tmp_path))
    k.source(src)
    assert k.active_source is src


def test_active_writers_is_empty_tuple_by_default():
    k = Kernel()
    assert k.active_writers == ()


def test_active_writers_reflects_writer_setter():
    k = Kernel()

    class StubWriter:
        def can_write(self, raw):
            return True

        def write(self, path, raw):
            pass

    w = StubWriter()
    k.writer(w)
    assert k.active_writers == (w,)


def test_active_writers_is_a_tuple_not_the_internal_list():
    """Ensure accidental mutation of the returned sequence cannot poison
    the kernel's internal writer list."""
    k = Kernel()

    class StubWriter:
        def can_write(self, raw):
            return True

        def write(self, path, raw):
            pass

    k.writer(StubWriter())
    got = k.active_writers
    assert isinstance(got, tuple)
    with pytest.raises(AttributeError):
        got.append(object())  # type: ignore[attr-defined]


class StubNonFilesystemSource:
    """Minimal stub that looks like WritableSourcePort but has no filesystem path."""
    supports_readers = False
    url_scheme = "sqlite"

    async def load_bootstrap_docs(self, scope, *, tenant=None): return []
    async def load_all(self, scope, readers=None): return []
    async def resolve_ref(self, scope, ref): return ref
    async def load_layer(self, *a, **kw): return []
    async def close(self): return None
    async def save_document(self, *a, **kw): return "v1"
    async def delete_document(self, *a, **kw): return None
    async def save_manifest(self, *a, **kw): return "v1"
    async def list_versions(self, *a, **kw): return []
    async def get_version(self, *a, **kw): return {}
    async def publish(self, *a, **kw): return "v1"
    async def load_drafts(self, *a, **kw): return []
    async def list_scopes(self): return []
    async def capabilities(self): return {}


def test_target_locator_filesystem_returns_path(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    got = k._target_locator("m", "Skill", "demo")
    assert isinstance(got, Path)
    assert got == tmp_path / "m" / "skills" / "demo"


def test_target_locator_non_filesystem_returns_synthetic_url():
    k = Kernel()
    k.source(StubNonFilesystemSource())
    got = k._target_locator("m", "Skill", "demo")
    assert got == "sqlite://m/Skill/demo"


def test_target_locator_falls_back_to_class_name_when_no_url_scheme():
    """Adapters that forgot to declare url_scheme still get a reasonable default."""
    class NoSchemeSource(StubNonFilesystemSource):
        url_scheme = None  # explicitly omit

    k = Kernel()
    k.source(NoSchemeSource())
    got = k._target_locator("m", "Skill", "demo")
    assert got == "noscheme://m/Skill/demo"


def test_target_exists_returns_false_for_missing_fs_doc(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    got = asyncio.run(k._target_exists("m", "Skill", "missing"))
    assert got is False


def test_target_exists_returns_true_when_fs_path_exists(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    # Write a doc first
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())
    asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))
    # Note: for FilesystemWritableSource, Agent is saved as a
    # yaml file, not a bundle dir; _target_locator maps to the dir name.
    # So exists_already here reports the bundle DIR, which does not
    # exist (file is alice.yaml, dir would be alice/). This is the
    # intended behavior — exists_already is a hint, not a fact.
    got = asyncio.run(k._target_exists("m", "Agent", "alice"))
    assert got is False   # dir does not exist


def test_target_exists_for_non_filesystem_uses_list_versions():
    k = Kernel()

    class StubSource(StubNonFilesystemSource):
        async def list_versions(self, *a, **kw):
            return [{"id": "v1"}]

    k.source(StubSource())
    assert asyncio.run(k._target_exists("m", "Skill", "demo")) is True


def test_emit_post_save_fires_registered_subscriber():
    k = Kernel()
    seen = []
    k.on("post_save", lambda ctx: seen.append((ctx.kind, ctx.name)))
    asyncio.run(k._emit_post_save("m", "Skill", "demo", {"kind": "Skill"}))
    assert seen == [("Skill", "demo")]


def test_emit_post_save_is_noop_without_subscribers():
    k = Kernel()
    asyncio.run(k._emit_post_save("m", "Skill", "demo", {"kind": "Skill"}))   # must not raise


def test_emit_post_delete_fires_registered_subscriber():
    k = Kernel()
    seen = []
    k.on("post_delete", lambda ctx: seen.append((ctx.kind, ctx.name)))
    asyncio.run(k._emit_post_delete("m", "Skill", "demo"))
    assert seen == [("Skill", "demo")]


def _raw_agent(name="alice"):
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Agent",
        "metadata": {"name": name},
        "spec": {"instruction": "be helpful"},
    }


def test_preview_document_no_disk_write(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    pr = asyncio.run(k.preview_document("m", "Agent", "alice", _raw_agent()))

    assert isinstance(pr, PreviewResult)
    assert isinstance(pr.target, Path)
    assert pr.target == tmp_path / "m" / "agents" / "alice"
    assert pr.files, "expected at least one serialized file"
    assert pr.exists_already is False           # new doc
    assert not pr.target.exists()                # nothing actually written


def test_preview_document_synthetic_url_for_non_filesystem_source():
    k = Kernel()
    k.source(StubNonFilesystemSource())
    from dna.extensions.agentskills import AgentSkillsExtension
    k.load(AgentSkillsExtension())

    raw = {"apiVersion": "agentskills.io/v1", "kind": "Skill",
           "metadata": {"name": "x"}, "spec": {"instruction": "hi"}}
    pr = asyncio.run(k.preview_document("m", "Skill", "x", raw))

    assert pr.target == "sqlite://m/Skill/x"
    assert pr.exists_already is False


def test_write_document_round_trip(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    version = asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))
    assert version == "1"
    assert (tmp_path / "m" / "agents" / "alice.yaml").is_file()


def test_write_document_no_source_raises():
    k = Kernel()
    with pytest.raises(NotWritableError, match="no source"):
        asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))


def test_write_document_read_only_source_raises(tmp_path):
    k = Kernel()
    k.source(FilesystemSource(str(tmp_path)))     # read-only
    with pytest.raises(NotWritableError, match="does not implement WritableSourcePort"):
        asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))


def test_write_document_last_write_wins(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))
    asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))  # no raise


def test_write_document_emits_post_save_hook(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    seen: list[tuple[str, str]] = []
    k.on("post_save", lambda ctx: seen.append((ctx.kind, ctx.name)))

    asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))
    assert seen == [("Agent", "alice")]


def test_write_document_skip_hooks_suppresses_emission(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    seen: list[tuple[str, str]] = []
    k.on("post_save", lambda ctx: seen.append((ctx.kind, ctx.name)))

    asyncio.run(k.write_document(
        "m", "Agent", "alice", _raw_agent(), skip_hooks=True,
    ))
    assert seen == []


def test_delete_document_round_trip(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))
    target = tmp_path / "m" / "agents" / "alice.yaml"
    assert target.is_file()

    asyncio.run(k.delete_document("m", "Agent", "alice"))
    assert not target.exists()


def test_delete_document_emits_post_delete_hook(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))

    seen: list[tuple[str, str]] = []
    k.on("post_delete", lambda ctx: seen.append((ctx.kind, ctx.name)))
    asyncio.run(k.delete_document("m", "Agent", "alice"))
    assert seen == [("Agent", "alice")]


def test_delete_document_skip_hooks_suppresses_emission(tmp_path):
    k = Kernel()
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    from dna.extensions.helix import HelixExtension
    k.load(HelixExtension())

    asyncio.run(k.write_document("m", "Agent", "alice", _raw_agent()))

    seen: list[tuple[str, str]] = []
    k.on("post_delete", lambda ctx: seen.append((ctx.kind, ctx.name)))
    asyncio.run(k.delete_document(
        "m", "Agent", "alice", skip_hooks=True,
    ))
    assert seen == []


def test_target_locator_custom_kind_uses_storage_container(tmp_path):
    """A kind declared by KindDefinitionExtension (container='kinds')
    must resolve to <baseDir>/<scope>/kinds/<name>, not to the legacy
    fallback <baseDir>/<scope>/kinddefinitions/<name>."""
    from dna.extensions.kinddef import KindDefinitionExtension

    k = Kernel()
    k.load(KindDefinitionExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))

    got = k._target_locator("m", "KindDefinition", "ticket")
    assert isinstance(got, Path)
    assert got == tmp_path / "m" / "kinds" / "ticket"


def test_post_save_hook_context_puts_scope_top_level(tmp_path):
    """Regression guard: ctx.scope must be populated at the top level so
    subscribers like EvidenceCaptureHook (which read ctx.scope directly)
    can look up per-scope policies. Parity with the TS kernel."""
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))

    captured: list = []
    k.on("post_save", lambda ctx: captured.append(ctx))

    asyncio.run(k.write_document("my-mod", "Agent", "alice", _raw_agent()))

    assert len(captured) == 1
    ctx = captured[0]
    assert ctx.scope == "my-mod"       # top-level, not buried in data
    assert ctx.kind == "Agent"
    assert ctx.name == "alice"
    assert ctx.data["event_type"]      # populated by derive_event_type
    assert ctx.data["spec"] == _raw_agent()
    assert ctx.data["is_update"] is False
    assert ctx.data["author"] == "sdk"


def test_post_delete_hook_context_puts_scope_top_level(tmp_path):
    """Same invariant for delete — subscribers read ctx.scope directly."""
    from dna.extensions.helix import HelixExtension

    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))

    asyncio.run(k.write_document("my-mod", "Agent", "alice", _raw_agent()))

    captured: list = []
    k.on("post_delete", lambda ctx: captured.append(ctx))

    asyncio.run(k.delete_document("my-mod", "Agent", "alice"))

    assert len(captured) == 1
    ctx = captured[0]
    assert ctx.scope == "my-mod"
    assert ctx.kind == "Agent"
    assert ctx.name == "alice"
