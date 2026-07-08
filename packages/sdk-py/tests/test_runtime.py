"""Tests for Runtime class — Python parity with TypeScript."""
from __future__ import annotations
from pathlib import Path

from dna import Kernel
from dna.kernel.runtime import Runtime


BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


class TestRuntime:
    def test_runtime_extends_kernel(self):
        rt = Runtime()
        assert isinstance(rt, Runtime)
        assert isinstance(rt, Kernel)
        assert hasattr(rt, "source")
        assert hasattr(rt, "storage")
        assert hasattr(rt, "instance")
        assert hasattr(rt, "manifest")

    def test_runtime_auto_loads_extensions(self):
        rt = Runtime.auto()
        assert isinstance(rt, Kernel)  # auto() returns Kernel, not Runtime
        assert len(rt._kinds) > 0

    def test_manifest_loads(self):
        from dna.adapters.filesystem.source import FilesystemSource
        from dna.adapters.filesystem.cache import FilesystemCache

        rt = Runtime.auto()
        rt.storage(FilesystemSource(str(BASE_DIR)))
        rt.cache(FilesystemCache(str(BASE_DIR)))
        m = rt.manifest("open-swe")
        assert len(m.documents) > 0
        assert m.scope == "open-swe"

    def test_runtime_importable_from_top_level(self):
        from dna import Runtime as Rt
        assert Rt is Runtime
