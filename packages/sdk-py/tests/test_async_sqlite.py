"""Async SQLite adapter tests."""
import pytest
import pytest_asyncio
from dna.adapters.sqlite.source import SqliteSource


@pytest_asyncio.fixture
async def sqlite_source(tmp_path):
    source = SqliteSource(str(tmp_path / "test.db"))
    await source.connect()
    yield source
    await source.close()


@pytest.mark.asyncio
async def test_save_and_load_manifest(sqlite_source):
    from dna.kernel.protocols import package_doc_for_scope
    manifest = {"kind": "Genome", "name": "test", "spec": {"agents": ["bot"]}}
    await sqlite_source.save_manifest("test", manifest)
    await sqlite_source.publish("test", "Genome", "test")
    loaded = await package_doc_for_scope(sqlite_source, "test")
    assert loaded is not None
    assert loaded["kind"] == "Genome"


@pytest.mark.asyncio
async def test_save_and_load_document(sqlite_source):
    manifest = {"kind": "Genome", "name": "test", "spec": {}}
    await sqlite_source.save_manifest("test", manifest)
    await sqlite_source.publish("test", "Genome", "test")
    doc = {"kind": "Agent", "name": "bot", "spec": {"model": "gpt-4o"}}
    await sqlite_source.save_document("test", "Agent", "bot", doc)
    await sqlite_source.publish("test", "Agent", "bot")
    docs = await sqlite_source.load_all("test")
    names = {d.get("name") for d in docs}
    assert "bot" in names


@pytest.mark.asyncio
async def test_list_scopes(sqlite_source):
    manifest = {"kind": "Genome", "name": "test", "spec": {}}
    await sqlite_source.save_manifest("test", manifest)
    await sqlite_source.publish("test", "Genome", "test")
    scopes = await sqlite_source.list_scopes()
    assert "test" in scopes


@pytest.mark.asyncio
async def test_close(sqlite_source):
    await sqlite_source.close()
