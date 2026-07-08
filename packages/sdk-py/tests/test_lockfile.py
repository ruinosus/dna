"""Integration tests for lockfile — generate, write, read, verify."""
import pytest
from pathlib import Path
from dna.kernel import Kernel
from dna.kernel.lock import write_lockfile, read_lockfile, verify_lock, LockEntry, Lockfile


BASE_DIR = Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"


@pytest.fixture
def mi():
    return Kernel.quick("open-swe", base_dir=str(BASE_DIR))


# ── TestGenerateLock ──

class TestGenerateLock:
    def test_all_docs_have_64_char_sha(self, mi):
        lock = mi.generate_lock()
        assert len(lock.documents) > 0
        for entry in lock.documents:
            assert len(entry.sha256) == 64, f"SHA for {entry.kind}/{entry.name} is not 64 chars"

    def test_scope_matches(self, mi):
        lock = mi.generate_lock()
        assert lock.scope == "open-swe"

    def test_deterministic(self, mi):
        lock1 = mi.generate_lock()
        lock2 = mi.generate_lock()
        sha_map1 = {(e.kind, e.name): e.sha256 for e in lock1.documents}
        sha_map2 = {(e.kind, e.name): e.sha256 for e in lock2.documents}
        assert sha_map1 == sha_map2


# ── TestWriteReadRoundtrip ──

class TestWriteReadRoundtrip:
    def test_write_read_entries_match(self, mi, tmp_path):
        lock = mi.generate_lock()
        lock_file = tmp_path / ".dna.lock"
        write_lockfile(lock, lock_file)

        restored = read_lockfile(lock_file)
        assert restored.scope == lock.scope
        assert len(restored.documents) == len(lock.documents)

        original_map = {(e.kind, e.name): e.sha256 for e in lock.documents}
        restored_map = {(e.kind, e.name): e.sha256 for e in restored.documents}
        assert original_map == restored_map

    def test_read_missing_file_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent.lock"
        result = read_lockfile(missing)
        assert isinstance(result, Lockfile)
        assert result.documents == []


# ── TestVerifyLock ──

class TestVerifyLock:
    def test_verify_passes_when_unchanged(self, mi, tmp_path):
        lock = mi.generate_lock()
        lock_file = tmp_path / ".dna.lock"
        write_lockfile(lock, lock_file)

        result = verify_lock(mi, lock_file)
        assert result.ok
        assert result.added == []
        assert result.removed == []
        assert result.changed == []

    def test_detects_added_doc(self, mi, tmp_path):
        """Remove one entry from the lock before writing — verify sees it as added."""
        lock = mi.generate_lock()
        # Drop the first doc so the lock doesn't know about it
        removed_entry = lock.documents[0]
        trimmed_lock = Lockfile(
            scope=lock.scope,
            documents=lock.documents[1:],
            lock_version=lock.lock_version,
            generated_at=lock.generated_at,
        )
        lock_file = tmp_path / ".dna.lock"
        write_lockfile(trimmed_lock, lock_file)

        result = verify_lock(mi, lock_file)
        assert not result.ok
        expected_key = f"{removed_entry.kind}/{removed_entry.name}"
        assert expected_key in result.added
        assert result.removed == []
        assert result.changed == []

    def test_detects_removed_doc(self, mi, tmp_path):
        """Add a fake entry to the lock — verify sees it as removed from MI."""
        lock = mi.generate_lock()
        fake_entry = LockEntry(
            name="ghost-agent",
            kind="Agent",
            api_version="helix/v1",
            origin="local",
            path="",
            sha256="a" * 64,
        )
        augmented_lock = Lockfile(
            scope=lock.scope,
            documents=lock.documents + [fake_entry],
            lock_version=lock.lock_version,
            generated_at=lock.generated_at,
        )
        lock_file = tmp_path / ".dna.lock"
        write_lockfile(augmented_lock, lock_file)

        result = verify_lock(mi, lock_file)
        assert not result.ok
        assert "Agent/ghost-agent" in result.removed
        assert result.added == []
        assert result.changed == []

    def test_detects_changed_sha(self, mi, tmp_path):
        """Mutate one entry's sha256 — verify detects it as changed."""
        lock = mi.generate_lock()
        # Pick first entry and corrupt its SHA
        target = lock.documents[0]
        mutated = LockEntry(
            name=target.name,
            kind=target.kind,
            api_version=target.api_version,
            origin=target.origin,
            path=target.path,
            sha256="0" * 64,  # Wrong SHA
        )
        mutated_docs = [mutated] + lock.documents[1:]
        mutated_lock = Lockfile(
            scope=lock.scope,
            documents=mutated_docs,
            lock_version=lock.lock_version,
            generated_at=lock.generated_at,
        )
        lock_file = tmp_path / ".dna.lock"
        write_lockfile(mutated_lock, lock_file)

        result = verify_lock(mi, lock_file)
        assert not result.ok
        expected_key = f"{target.kind}/{target.name}"
        assert expected_key in result.changed
        assert result.added == []
        assert result.removed == []
