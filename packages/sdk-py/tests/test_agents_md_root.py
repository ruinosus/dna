"""The repo's front door is a live agents.md/v1 instance (s-dna-agent-ready).

``AGENTS.md`` at the repository root is the agent-agnostic onboarding doc
AND a document the SDK itself parses — dogfooding market fidelity at the
entry point. Every test here runs against the REAL root file (never a
copy): the reader is exercised directly on the repo root, and the full
scan → typed → composition → write-round-trip pipeline runs through a
scope whose ``AGENTS.md`` is a symlink to it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.kernel.bundle_handle import FilesystemBundleHandle
from dna.adapters.filesystem import FilesystemSource, FilesystemCache
from dna.extensions.agentsmd import AgentDefinitionReader

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_MD = REPO_ROOT / "AGENTS.md"

SCOPE = "root-dogfood"


class TestReaderOnRepoRoot:
    """The agentsmd reader consumes the repository root directly."""

    def test_root_file_exists(self):
        assert AGENTS_MD.is_file(), "the repo must ship a root AGENTS.md"

    def test_detects_and_reads_the_real_root_file(self):
        reader = AgentDefinitionReader()
        bundle = FilesystemBundleHandle(REPO_ROOT)
        assert reader.detect(bundle), "repo root must detect as an AGENTS.md bundle"
        raw = reader.read(bundle)
        assert raw["apiVersion"] == "agents.md/v1"
        assert raw["kind"] == "AgentDefinition"
        assert raw["metadata"]["name"], "name derives from the bundle directory"
        # No frontmatter → spec.content preserves the file verbatim.
        assert raw["spec"]["content"] == AGENTS_MD.read_text()


@pytest.fixture(scope="module")
def dogfood():
    """Kernel scan over a scope whose AGENTS.md IS the real root file
    (symlink — the bytes on disk are the single source of truth)."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        scope_dir = Path(tmp) / SCOPE
        scope_dir.mkdir()
        (scope_dir / "AGENTS.md").symlink_to(AGENTS_MD)
        k = Kernel.auto()
        k.source(FilesystemSource(tmp))
        k.cache(FilesystemCache(tmp))
        yield k, k.instance(SCOPE)


class TestKernelPipeline:
    def test_scan_yields_a_typed_agents_md_document(self, dogfood):
        _, mi = dogfood
        doc = next(
            (d for d in mi.documents if d.kind == "AgentDefinition" and d.name == SCOPE),
            None,
        )
        assert doc is not None, "scope-root AGENTS.md must scan as a document"
        assert doc.raw.get("apiVersion") == "agents.md/v1"
        assert doc.typed is not None, "root AGENTS.md must type-validate"
        content = doc.spec.get("content", "")
        assert "Domain Notation of Anything" in content
        assert "dna sdlc" in content, "the SDLC protocol must be part of the front door"

    def test_root_agents_md_is_a_full_prompt_target(self, dogfood):
        """agents.md/v1 is a full agent archetype: composing a prompt with
        the repo's own AGENTS.md as target renders the real prose."""
        _, mi = dogfood
        prompt = mi.build_prompt(agent=SCOPE)
        assert "Never hand-edit" in prompt
        assert "dna sdlc story create" in prompt

    def test_write_roundtrip_byte_identical(self, dogfood):
        """Market fidelity at the front door: the writer re-emits the root
        AGENTS.md byte-identical (no frontmatter is ever invented)."""
        k, mi = dogfood
        doc = next(d for d in mi.documents if d.kind == "AgentDefinition" and d.name == SCOPE)
        payload = k.serialize_document(SCOPE, doc.kind, doc.name, doc.raw)
        files = {f["relativePath"]: f["content"] for f in payload["files"]}
        assert files["AGENTS.md"].encode("utf-8") == AGENTS_MD.read_bytes()
