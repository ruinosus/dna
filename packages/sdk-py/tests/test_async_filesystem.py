"""Async filesystem adapter tests."""
import pytest
import yaml as pyyaml
from dna.adapters.filesystem.source import FilesystemSource
from dna.adapters.filesystem.writable import FilesystemWritableSource


@pytest.fixture
def fs_dir(tmp_path):
    scope_dir = tmp_path / "test-mod"
    scope_dir.mkdir()
    manifest = {"kind": "Genome", "name": "test-mod", "spec": {"agents": ["bot"]}}
    (scope_dir / "manifest.yaml").write_text(pyyaml.dump(manifest))
    agents_dir = scope_dir / "agents"
    agents_dir.mkdir()
    agent = {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o"}}
    (agents_dir / "bot.yaml").write_text(pyyaml.dump(agent))
    return tmp_path


@pytest.mark.asyncio
async def test_load_bootstrap_docs(fs_dir):
    from dna.kernel.protocols import package_doc_for_scope
    source = FilesystemSource(str(fs_dir))
    manifest = await package_doc_for_scope(source, "test-mod")
    assert manifest is not None
    assert manifest["kind"] == "Genome"
    assert manifest["name"] == "test-mod"


@pytest.mark.asyncio
async def test_load_all(fs_dir):
    source = FilesystemSource(str(fs_dir))
    docs = await source.load_all("test-mod")
    kinds = {d.get("kind") for d in docs}
    assert "Genome" in kinds
    assert "Agent" in kinds


@pytest.mark.asyncio
async def test_writable_save_and_load(fs_dir):
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel

    k = Kernel()
    k.load(HelixExtension())
    source = FilesystemWritableSource(str(fs_dir), kernel=k)
    new_doc = {"kind": "Agent", "name": "new-agent", "spec": {"model": "gpt-4o"}}
    await source.save_document("test-mod", "Agent", "new-agent", new_doc)
    docs = await source.load_all("test-mod")
    names = {d.get("name") for d in docs}
    assert "new-agent" in names


@pytest.mark.asyncio
async def test_list_scopes(fs_dir):
    source = FilesystemWritableSource(str(fs_dir))
    scopes = await source.list_scopes()
    assert "test-mod" in scopes


@pytest.mark.asyncio
async def test_close_is_noop(fs_dir):
    source = FilesystemSource(str(fs_dir))
    await source.close()
