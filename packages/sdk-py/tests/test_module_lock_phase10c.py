"""Phase 10c — per-tenant Genome install lockfile + outdated resolver."""
from __future__ import annotations

import pytest

from dna.kernel.module_lock import (
    LOCKFILE_VERSION,
    OutdatedReport,
    GenomeEntry,
    GenomeLockfile,
    compute_outdated,
    diff_versions,
    load_lockfile,
    sha256_file,
    write_lockfile,
)


def test_lockfile_load_missing_returns_empty(tmp_path):
    lock = load_lockfile(tmp_path, "acme")
    assert lock.tenant == "acme"
    assert lock.packages == []
    assert lock.lock_version == LOCKFILE_VERSION


def test_lockfile_round_trip(tmp_path):
    lock = GenomeLockfile(tenant="acme")
    lock.upsert(GenomeEntry(
        source="platform/hr-screening",
        version_constraint="^1.0.0",
        resolved_version="1.4.2",
        resolved_sha256="abc123",
        installed_at="2026-04-15T10:00:00Z",
    ))
    p = write_lockfile(lock, tmp_path)
    assert p.is_file()
    assert p.parent.name == "acme"
    assert p.parent.parent.name == "tenants"

    reloaded = load_lockfile(tmp_path, "acme")
    assert reloaded.tenant == "acme"
    assert len(reloaded.packages) == 1
    m = reloaded.packages[0]
    assert m.source == "platform/hr-screening"
    assert m.resolved_version == "1.4.2"


def test_upsert_replaces_same_source():
    lock = GenomeLockfile(tenant="acme")
    lock.upsert(GenomeEntry("a/b", "^1.0.0", "1.0.0", "x", "t"))
    lock.upsert(GenomeEntry("a/b", "^1.0.0", "1.5.0", "y", "t2"))
    assert len(lock.packages) == 1
    assert lock.packages[0].resolved_version == "1.5.0"


def test_remove_returns_false_when_missing():
    lock = GenomeLockfile(tenant="acme")
    assert lock.remove("not/there") is False


def test_lockfile_rejects_newer_version(tmp_path):
    """An SDK loading a future lockfile must fail loud, not silently downgrade."""
    p = tmp_path / "tenants" / "acme" / ".dna.lock"
    p.parent.mkdir(parents=True)
    p.write_text("lockVersion: 999\ntenant: acme\npackages: []\n")
    with pytest.raises(ValueError, match="newer than this SDK"):
        load_lockfile(tmp_path, "acme")


def test_sha256_file_stable(tmp_path):
    p = tmp_path / "f.yaml"
    p.write_text("hello\n")
    h1 = sha256_file(p)
    h2 = sha256_file(p)
    assert h1 == h2 and len(h1) == 64


def test_diff_versions_classifies_bump():
    assert diff_versions("1.0.0", "2.0.0") == "major"
    assert diff_versions("1.0.0", "1.5.0") == "minor"
    assert diff_versions("1.0.0", "1.0.5") == "patch"
    assert diff_versions("1.0.0-rc.1", "1.0.0-rc.2") == "prerelease"


def test_compute_outdated_picks_highest_within_constraint():
    lock = GenomeLockfile(tenant="acme")
    lock.upsert(GenomeEntry("p/safety", "^1.0.0", "1.4.2", "x", "t"))
    lock.upsert(GenomeEntry("p/up-to-date", "^1.0.0", "1.5.0", "y", "t"))

    available = {
        "p/safety": ["1.0.0", "1.4.2", "1.5.0", "2.0.0"],   # 1.5.0 in constraint
        "p/up-to-date": ["1.0.0", "1.5.0"],                  # already at 1.5.0
    }
    reports = compute_outdated(lock, available)
    assert len(reports) == 1
    r: OutdatedReport = reports[0]
    assert r.source == "p/safety"
    assert r.current == "1.4.2"
    assert r.available == "1.5.0"   # NOT 2.0.0 (caret excludes major bump)
    assert r.update_kind == "minor"


def test_compute_outdated_skips_unknown_source():
    """Genome in lock with no entries in catalog → silently skipped."""
    lock = GenomeLockfile(tenant="acme")
    lock.upsert(GenomeEntry("p/missing", "^1.0.0", "1.0.0", "x", "t"))
    assert compute_outdated(lock, {}) == []


def test_compute_outdated_handles_unversioned_resolved():
    """When the lock holds an unversioned install but the catalog has
    semver releases, the resolver SHOULD flag an update — there is a
    real version to upgrade into."""
    lock = GenomeLockfile(tenant="acme")
    # ``resolved_version=""`` is unversioned in the lock
    lock.upsert(GenomeEntry("p/x", "*", "", "x", "t"))
    reports = compute_outdated(lock, {"p/x": ["1.0.0", "2.0.0"]})
    assert len(reports) == 1
    assert reports[0].available == "2.0.0"
