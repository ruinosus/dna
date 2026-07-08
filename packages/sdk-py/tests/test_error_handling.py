"""Tests for v3 error handling — YAML malformed, missing deps, parse failures.

GAP-20: Error handling tests — validates that the kernel and adapters
handle errors gracefully (log + continue, don't crash).
"""
from __future__ import annotations

import logging
import pytest
from pathlib import Path

from dna.kernel import Kernel
from dna.kernel.document import Document
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import ReaderPort, ResolveError, StorageDescriptor
from dna.adapters.filesystem import FilesystemSource


BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


# ── FilesystemSource error paths ──

class TestFilesystemErrors:
    @pytest.mark.asyncio
    async def test_missing_scope_raises(self, tmp_path):
        src = FilesystemSource(tmp_path)
        with pytest.raises(FileNotFoundError):
            await src.load_all("nonexistent")

    @pytest.mark.asyncio
    async def test_missing_manifest_returns_none(self, tmp_path):
        from dna.kernel.protocols import package_doc_for_scope
        scope_dir = tmp_path / "my-mod"
        scope_dir.mkdir()
        src = FilesystemSource(tmp_path)
        # Phase 16 — empty scope dir yields no bootstrap Genome; helper
        # returns None instead of raising (raise was a load_manifest-only
        # contract).
        assert await package_doc_for_scope(src, "my-mod") is None

    @pytest.mark.asyncio
    async def test_malformed_yaml_logged_not_crash(self, tmp_path, caplog):
        """A YAML file with invalid syntax is logged and skipped."""
        scope_dir = tmp_path / "broken"
        scope_dir.mkdir()
        (scope_dir / "manifest.yaml").write_text("kind: Genome\nmetadata:\n  name: broken\nspec: {}")
        (scope_dir / "bad.yaml").write_text("kind: Foo\n  bad indent: [")

        src = FilesystemSource(tmp_path)
        with caplog.at_level(logging.WARNING):
            docs = await src.load_all("broken")

        # The valid manifest.yaml is loaded, bad.yaml is skipped
        assert len(docs) >= 1
        valid_names = [d.get("metadata", {}).get("name") for d in docs]
        assert "broken" in valid_names

    @pytest.mark.asyncio
    async def test_yaml_without_kind_skipped(self, tmp_path):
        """A YAML file without 'kind' is ignored (not a manifest document)."""
        scope_dir = tmp_path / "noking"
        scope_dir.mkdir()
        (scope_dir / "config.yaml").write_text("database: postgres\nport: 5432")

        src = FilesystemSource(tmp_path)
        docs = await src.load_all("noking")
        assert len(docs) == 0

    @pytest.mark.asyncio
    async def test_missing_layer_returns_empty(self, tmp_path):
        """load_layer for non-existent layer returns empty list (no error)."""
        scope_dir = tmp_path / "mod"
        scope_dir.mkdir()
        src = FilesystemSource(tmp_path)
        result = await src.load_layer("mod", "tenant", "nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_resolve_ref_missing_returns_empty(self, tmp_path):
        """resolve_ref for non-existent file returns empty string."""
        scope_dir = tmp_path / "mod"
        scope_dir.mkdir()
        src = FilesystemSource(tmp_path)
        assert await src.resolve_ref("mod", "nonexistent.md") == ""

    @pytest.mark.asyncio
    async def test_reader_error_logged_not_crash(self, tmp_path, caplog):
        """If a reader raises an exception during detect/read, it's logged and skipped."""

        class BrokenReader(ReaderPort):
            def detect(self, path):
                raise RuntimeError("reader exploded")

            def read(self, path):
                raise RuntimeError("should not get here")

        scope_dir = tmp_path / "mod"
        scope_dir.mkdir()
        subdir = scope_dir / "some-bundle"
        subdir.mkdir()
        (subdir / "file.txt").write_text("hello")

        src = FilesystemSource(tmp_path)
        with caplog.at_level(logging.WARNING):
            docs = await src.load_all("mod", readers=[BrokenReader()])

        # Should not crash, just log
        assert any("reader exploded" in r.message for r in caplog.records)


# ── Kernel parse error paths ──

class TestKernelParseErrors:
    def test_parse_error_falls_back_to_raw(self, caplog):
        """If KindPort.parse() raises, Document still created with typed=None."""

        class BadKind(KindBase):
            api_version = "bad/v1"
            kind = "BadKind"
            alias = "bad-kind"
            origin = "test"
            storage = StorageDescriptor.yaml("bad")

            def parse(self, raw): raise ValueError("parse boom")

        k = Kernel()
        k.kind(BadKind())
        raw = {"apiVersion": "bad/v1", "kind": "BadKind", "metadata": {"name": "x"}, "spec": {"v": 1}}

        with caplog.at_level(logging.WARNING):
            doc = k._parse_doc(raw, origin="local")

        assert doc.name == "x"
        assert doc.kind == "BadKind"
        assert doc.typed is None  # Fell back to raw
        assert any("parse boom" in r.message for r in caplog.records)

    def test_unknown_kind_creates_untyped_doc(self):
        """Documents with unregistered kinds are created with typed=None."""
        k = Kernel()
        raw = {"apiVersion": "unknown/v1", "kind": "Mystery", "metadata": {"name": "m"}, "spec": {}}
        doc = k._parse_doc(raw, origin="local")
        assert doc.kind == "Mystery"
        assert doc.typed is None


# ── Kernel dependency resolution errors ──

class TestDependencyResolutionErrors:
    def test_unknown_scheme_collected(self, tmp_path):
        """Dependencies with unknown URI scheme are collected in resolve_errors."""
        scope_dir = tmp_path / "mod"
        scope_dir.mkdir()
        (scope_dir / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
            "metadata:\n  name: mod\n"
            "spec:\n  dependencies:\n    - source: ftp://example.com/skills\n"
        )

        from dna.adapters.filesystem import FilesystemSource, FilesystemCache
        k = Kernel()
        k.source(FilesystemSource(tmp_path))
        k.cache(FilesystemCache(tmp_path))
        # No resolver for "ftp" scheme
        from dna.extensions.helix import HelixExtension
        k.load(HelixExtension())

        mi = k.instance("mod")
        assert len(mi.resolve_errors) == 1
        assert "ftp" in mi.resolve_errors[0]

    def test_resolver_error_collected(self, tmp_path):
        """ResolveError from a resolver is collected, not raised."""
        scope_dir = tmp_path / "mod"
        scope_dir.mkdir()
        (scope_dir / "manifest.yaml").write_text(
            "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
            "metadata:\n  name: mod\n"
            "spec:\n  dependencies:\n    - source: broken://fail\n"
        )

        class FailResolver:
            async def resolve(self, uri, dep):
                raise ResolveError("resolver failed hard")

            def cache_key(self, uri):
                return "broken-fail"

        from dna.adapters.filesystem import FilesystemSource, FilesystemCache
        k = Kernel()
        k.source(FilesystemSource(tmp_path))
        k.cache(FilesystemCache(tmp_path))
        k.resolver("broken", FailResolver())
        from dna.extensions.helix import HelixExtension
        k.load(HelixExtension())

        mi = k.instance("mod")
        assert any("resolver failed hard" in e for e in mi.resolve_errors)


# ── ManifestInstance error paths ──

class TestMIErrors:
    def test_build_prompt_unknown_agent(self):
        mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))
        result = mi.build_prompt(agent="ghost-agent")
        assert "not found" in result

    def test_describe_missing_doc(self):
        mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))
        result = mi.describe("Skill", "nonexistent-skill")
        assert "not found" in result

    def test_one_missing_returns_none(self):
        mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))
        assert mi.one("Genome", "ghost") is None

    def test_ref_empty_string(self):
        mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))
        assert mi.ref("") == ""

    def test_ref_nonexistent_file_returns_original(self):
        """Unresolvable ref returns the original value (passthrough fallback)."""
        mi = Kernel.quick("open-swe", base_dir=str(BASE_DIR))
        assert mi.ref("nonexistent/file.md") == "nonexistent/file.md"

    def test_composition_with_unknown_alias(self):
        """dep_filters referencing an unknown alias produces a warning, not a crash."""
        from dna.kernel.instance import ManifestInstance

        class WeirdKind:
            api_version = "w/v1"
            kind = "Weird"
            alias = "weird-kind"
            model = dict
            origin = "test"
            is_root = False
            is_prompt_target = False
            flatten_in_context = False

            def dep_filters(self): return {"refs": "nonexistent-alias"}
            def get_default_agent_name(self, doc): return None
            def get_layer_policies(self, doc): return None
            def parse(self, raw): return raw
            def describe(self, doc): return None
            def summary(self, doc): return None
            def prompt_template(self): return None

        doc = Document.from_raw({
            "apiVersion": "w/v1", "kind": "Weird",
            "metadata": {"name": "w1"}, "spec": {"refs": ["something"]},
        })
        kinds = {("w/v1", "Weird"): WeirdKind()}
        mi = ManifestInstance(scope="test", documents=[doc], kinds=kinds)
        cr = mi.composition_result
        # Should produce a warning, not crash
        assert any("nonexistent-alias" in w for w in cr.warnings)


# ── Hook error paths ──

class TestHookErrors:
    def test_middleware_error_propagates(self):
        """Middleware errors DO propagate (middleware is inline, not fire-and-forget)."""
        from dna.kernel.hooks import HookRegistry, HookContext

        hooks = HookRegistry()

        def bad_middleware(ctx):
            raise ValueError("middleware boom")

        hooks.use("pre_build_prompt", bad_middleware)
        with pytest.raises(ValueError, match="middleware boom"):
            hooks.run_middleware("pre_build_prompt", HookContext())

    def test_event_error_logged(self, caplog):
        """Event errors are logged but NOT raised."""
        from dna.kernel.hooks import HookRegistry, HookContext

        hooks = HookRegistry()

        def bad_event(ctx):
            raise RuntimeError("event boom")

        hooks.on("post_build_prompt", bad_event)
        with caplog.at_level(logging.WARNING):
            hooks.emit("post_build_prompt", HookContext())  # Should not raise

        assert any("event boom" in r.message for r in caplog.records)

    def test_has_empty_hooks(self):
        from dna.kernel.hooks import HookRegistry
        hooks = HookRegistry()
        assert hooks.has("anything") is False

    def test_has_with_middleware(self):
        from dna.kernel.hooks import HookRegistry
        hooks = HookRegistry()
        hooks.use("pre_build_prompt", lambda ctx: ctx)
        assert hooks.has("pre_build_prompt") is True


# ── Parse error hook (GAP-27) ──

class TestParseErrorHook:
    def test_parse_error_emits_event(self):
        """When KindPort.parse() fails, a parse_error event is emitted."""
        from dna.kernel.hooks import HookContext

        class BadKind(KindBase):
            api_version = "bad/v1"
            kind = "BadKind"
            alias = "bad-kind"
            origin = "test"
            storage = StorageDescriptor.yaml("bad")
            def parse(self, raw): raise TypeError("bad parse")

        captured: list[HookContext] = []

        k = Kernel()
        k.kind(BadKind())
        k.on("parse_error", lambda ctx: captured.append(ctx))

        raw = {"apiVersion": "bad/v1", "kind": "BadKind", "metadata": {"name": "x"}, "spec": {}}
        k._parse_doc(raw, origin="local")

        assert len(captured) == 1
        assert captured[0].kind == "BadKind"
        assert captured[0].name == "x"
        assert "bad parse" in captured[0].data["error"]


# ── supports_readers port property (W2 fix) ──

class TestSupportsReaders:
    def test_filesystem_source_supports_readers(self):
        source = FilesystemSource(str(BASE_DIR))
        assert source.supports_readers is True

    def test_sqlite_source_does_not_support_readers(self):
        import tempfile, os
        from dna.adapters.sqlite.source import SqliteSource
        db = os.path.join(tempfile.mkdtemp(), "test.db")
        source = SqliteSource(db)
        assert source.supports_readers is False

    def test_async_adapter_delegates_supports_readers(self):
        from dna.adapters.async_adapter import AsyncSourceAdapter
        source = FilesystemSource(str(BASE_DIR))
        async_source = AsyncSourceAdapter(source)
        assert async_source.supports_readers is True

    def test_async_adapter_false_for_sqlite(self):
        import tempfile, os
        from dna.adapters.async_adapter import AsyncSourceAdapter
        from dna.adapters.sqlite.source import SqliteSource
        db = os.path.join(tempfile.mkdtemp(), "test.db")
        async_source = AsyncSourceAdapter(SqliteSource(db))
        assert async_source.supports_readers is False


# ── Extension error isolation (W3 fix) ──

class TestExtensionErrorIsolation:
    def test_bad_extension_with_hook_does_not_crash(self):
        """When extension_error hook is registered, bad extensions don't crash."""
        from dna.kernel.hooks import HookContext

        class BadExtension:
            name = "bad-ext"
            version = "1.0.0"
            def register(self, kernel):
                raise RuntimeError("extension init failed")

        captured: list[HookContext] = []

        k = Kernel()
        k.on("extension_error", lambda ctx: captured.append(ctx))
        k.load(BadExtension())  # Should NOT raise

        assert len(captured) == 1
        assert captured[0].name == "bad-ext"
        assert "extension init failed" in captured[0].data["error"]

    def test_bad_extension_without_hook_raises(self):
        """Without extension_error hook, bad extensions still raise (backward compat)."""

        class BadExtension:
            name = "bad-ext"
            version = "1.0.0"
            def register(self, kernel):
                raise RuntimeError("boom")

        k = Kernel()
        with pytest.raises(RuntimeError, match="boom"):
            k.load(BadExtension())
