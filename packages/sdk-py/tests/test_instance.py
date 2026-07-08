from __future__ import annotations


def test_mi_read_spec_returns_field(tmp_path):
    """mi.read_spec reads a field from a specific document without
    requiring the caller to hold a Document reference."""
    from dna.kernel import Kernel
    from dna.extensions.helix import HelixExtension
    from dna.extensions.agentskills import AgentSkillsExtension
    from dna.adapters.filesystem.source import FilesystemSource

    base = tmp_path / ".dna" / "scope1"
    (base / "agents").mkdir(parents=True)
    (base / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: scope1\nspec:\n  default_agent: foo\n"
    )
    (base / "agents" / "foo.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Agent\nmetadata:\n  name: foo\nspec:\n  soul: my-soul\n  skills: [a, b]\n"
    )

    kernel = Kernel()
    kernel.load(HelixExtension())
    kernel.load(AgentSkillsExtension())
    from dna.adapters.filesystem.cache import FilesystemCache
    kernel.source(FilesystemSource(str(tmp_path / ".dna")))
    kernel.cache(FilesystemCache(str(tmp_path / ".cache")))
    mi = kernel.instance("scope1")

    assert mi.read_spec("Agent", "foo", "soul") == "my-soul"
    assert mi.read_spec("Agent", "foo", "nope", default="x") == "x"
    assert mi.read_spec("Agent", "foo", "nope") is None
    assert mi.read_spec_list("Agent", "foo", "skills") == ["a", "b"]
    assert mi.read_spec_list("Agent", "foo", "nope") == []
    assert mi.read_metadata("Agent", "foo", "name") == "foo"


def test_mi_read_spec_raises_on_unknown_document(tmp_path):
    """Unknown (kind, name) pair should raise KeyError."""
    import pytest
    from dna.kernel import Kernel
    from dna.extensions.helix import HelixExtension
    from dna.adapters.filesystem.source import FilesystemSource

    base = tmp_path / ".dna" / "scope1"
    base.mkdir(parents=True)
    (base / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\nmetadata:\n  name: scope1\nspec: {}\n"
    )
    kernel = Kernel()
    kernel.load(HelixExtension())
    from dna.adapters.filesystem.cache import FilesystemCache
    kernel.source(FilesystemSource(str(tmp_path / ".dna")))
    kernel.cache(FilesystemCache(str(tmp_path / ".cache")))
    mi = kernel.instance("scope1")

    with pytest.raises(KeyError, match="Agent.*missing"):
        mi.read_spec("Agent", "missing", "field")
