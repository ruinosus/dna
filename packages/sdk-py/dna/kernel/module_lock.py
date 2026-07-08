"""Per-tenant Genome install lockfile (.dna.lock v5; Phase 16).

Storage: ``<base>/tenants/<tenant>/.dna.lock`` (per-tenant, single file
covering all the tenant's installs across scopes). Platform-owned
Genomes are NOT tracked here — they're the catalog itself, not
consumed artifacts.

File shape (YAML, v5):

    lockVersion: 5
    generated_at: "2026-04-28T12:34:56Z"
    tenant: acme
    packages:
      - source: "platform/hr-screening"
        version_constraint: "^1.0.0"
        resolved_version: "1.4.2"
        resolved_sha256: "<sha256 of Genome.yaml>"
        installed_at: "2026-04-15T10:22:00Z"

The existing scope-level `.dna.lock` (v3, document SHA tracking) is
preserved at its scope-level location — this v5 file is a separate
per-tenant doc with a different top-level key set.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Phase 16 — Genome replaces Module as the lockfile entity.
LOCKFILE_VERSION = 6


@dataclass
class GenomeEntry:
    """One installed Genome in the tenant's lockfile (Phase 16, v6).

    Decision #3 of the source-as-distribution spec: ``installed_from``
    + ``target_*`` track the distribution origin and the runtime target
    separately. ``source`` keeps the canonical ``<owner>/<name>``
    identity used by the existing catalog API.
    """
    source: str                   # "<owner>/<name>"
    version_constraint: str       # what the consumer asked for, e.g. "^1.0.0"
    resolved_version: str         # what they got, e.g. "1.4.2"
    resolved_sha256: str          # tamper-detect on the Genome.yaml
    installed_at: str             # ISO 8601 UTC
    # New in v6: distribution origin + runtime target. Optional with
    # safe defaults so legacy v5 entries upgrade cleanly.
    installed_from: str = ""       # source URL the bundle was READ from
    target_tenant: str = ""        # tenant the artifact landed in (defaults to lockfile tenant)
    target_source_url: str = ""    # writable source the artifact landed in

    @classmethod
    def from_dict(cls, d: dict) -> GenomeEntry:
        return cls(
            source=d["source"],
            version_constraint=d.get("version_constraint", "*"),
            resolved_version=d.get("resolved_version", ""),
            resolved_sha256=d.get("resolved_sha256", ""),
            installed_at=d.get("installed_at", ""),
            installed_from=d.get("installed_from", ""),
            target_tenant=d.get("target_tenant", ""),
            target_source_url=d.get("target_source_url", ""),
        )

    def to_dict(self) -> dict:
        out = {
            "source": self.source,
            "version_constraint": self.version_constraint,
            "resolved_version": self.resolved_version,
            "resolved_sha256": self.resolved_sha256,
            "installed_at": self.installed_at,
        }
        # Only emit v6 fields when populated — keeps legacy lockfiles
        # diff-clean for entries that never went through the
        # community/distribution path.
        if self.installed_from:
            out["installed_from"] = self.installed_from
        if self.target_tenant:
            out["target_tenant"] = self.target_tenant
        if self.target_source_url:
            out["target_source_url"] = self.target_source_url
        return out


@dataclass
class GenomeLockfile:
    """Top-level v5 lockfile (Phase 16)."""
    tenant: str = ""
    packages: list[GenomeEntry] = field(default_factory=list)
    lock_version: int = LOCKFILE_VERSION
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def find(self, source: str) -> GenomeEntry | None:
        for m in self.packages:
            if m.source == source:
                return m
        return None

    def upsert(self, entry: GenomeEntry) -> None:
        existing = self.find(entry.source)
        if existing is not None:
            self.packages.remove(existing)
        self.packages.append(entry)

    def remove(self, source: str) -> bool:
        existing = self.find(source)
        if existing is None:
            return False
        self.packages.remove(existing)
        return True


def _lock_path(base_dir: Path, tenant: str) -> Path:
    return base_dir / "tenants" / tenant / ".dna.lock"


def resolve_lockfile_root(source_base_dir: object | None = None) -> Path:
    """Pick the directory under which per-tenant ``.dna.lock`` files live.

    Resolution order (Phase 10g):
      1. ``DNA_LOCKFILE_DIR`` env — explicit operator override. Always wins.
      2. ``source_base_dir`` argument — for filesystem sources, the
         lockfile sits next to the manifest data (back-compat with the
         Phase 10c filesystem-only design).
      3. ``~/.cache/dna/locks/`` — fallback for SQL-backed sources where
         no on-disk base exists. Per-user directory, mirrors the
         ``~/.cache/dna/litellm/...`` pattern used elsewhere in the harness.

    The directory is created on first write by ``write_lockfile`` (no
    eager mkdir here — keeps the read path side-effect-free).
    """
    import os
    env = os.environ.get("DNA_LOCKFILE_DIR")
    if env:
        return Path(env).expanduser()
    if source_base_dir is not None:
        return Path(str(source_base_dir))
    return Path("~/.cache/dna/locks").expanduser()


def load_lockfile(base_dir: Path, tenant: str) -> GenomeLockfile:
    """Load the tenant's lockfile, or return an empty one when missing."""
    p = _lock_path(base_dir, tenant)
    if not p.is_file():
        return GenomeLockfile(tenant=tenant)
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError:
        return GenomeLockfile(tenant=tenant)
    if data.get("lockVersion", 0) > LOCKFILE_VERSION:
        raise ValueError(
            f"lockfile at {p} has lockVersion={data['lockVersion']} which is "
            f"newer than this SDK supports ({LOCKFILE_VERSION}). Upgrade the "
            "SDK."
        )
    raw_entries = data.get("packages") or []
    return GenomeLockfile(
        tenant=data.get("tenant") or tenant,
        packages=[GenomeEntry.from_dict(m) for m in raw_entries],
        lock_version=int(data.get("lockVersion", LOCKFILE_VERSION)),
        generated_at=data.get("generated_at", ""),
    )


def write_lockfile(lock: GenomeLockfile, base_dir: Path) -> Path:
    """Write the lockfile atomically. Sorts entries by source for stable diffs."""
    p = _lock_path(base_dir, lock.tenant)
    p.parent.mkdir(parents=True, exist_ok=True)
    sorted_entries = sorted(lock.packages, key=lambda m: m.source)
    serialized = [m.to_dict() for m in sorted_entries]
    payload: dict[str, Any] = {
        "lockVersion": LOCKFILE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant": lock.tenant,
        "packages": serialized,
    }
    tmp = p.with_suffix(".lock.tmp")
    tmp.write_text(yaml.dump(payload, default_flow_style=False, sort_keys=False))
    tmp.replace(p)
    return p


def sha256_file(path: Path) -> str:
    """Hex digest of a file. Caller's responsibility to handle missing path."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────────────
# Outdated resolver
# ─────────────────────────────────────────────────────────────────────


@dataclass
class OutdatedReport:
    source: str                      # "<owner>/<name>"
    constraint: str                  # what the lock asked for
    current: str                     # resolved version in lock
    available: str                   # highest matching version in catalog
    update_kind: str                 # "patch" | "minor" | "major" | "prerelease"


def diff_versions(current: str, target: str) -> str:
    """Classify the bump kind. Used for UX coloring.

    ``current`` may be empty / unversioned — treat as 0.0.0 so the
    resulting kind reflects the target's magnitude (almost always
    'major' which is exactly what we want to surface to the user:
    this is a big change because you have nothing pinned).
    """
    from dna.kernel.semver import Version
    cv = Version.parse(current) if current else Version(0, 0, 0)
    tv = Version.parse(target)
    if cv.major != tv.major:
        return "major"
    if cv.minor != tv.minor:
        return "minor"
    if cv.patch != tv.patch:
        return "patch"
    return "prerelease"


def compute_outdated(
    lock: GenomeLockfile,
    available_per_package: dict[str, list[str]],
) -> list[OutdatedReport]:
    """Walk lock.packages and report any with a higher matching version.

    ``available_per_package`` maps ``<owner>/<name>`` → list of available
    semver strings (typically harvested from
    ``GET /catalog/{owner}/{name}/versions``).
    """
    from dna.kernel.semver import is_outdated, max_satisfying, Version

    out: list[OutdatedReport] = []
    for m in lock.packages:
        avail = available_per_package.get(m.source, [])
        if not avail:
            continue
        # is_outdated(installed, ...) treats "" as None → unversioned
        # → returns True when ANY real version exists. That's the
        # right call for "this install has no version pinned but the
        # publisher does" — surface it as updatable.
        installed = m.resolved_version or None
        if not is_outdated(installed, avail, m.version_constraint):
            continue
        best = max_satisfying([Version.parse(v) for v in avail], m.version_constraint)
        if best is None:
            continue
        out.append(OutdatedReport(
            source=m.source,
            constraint=m.version_constraint,
            current=m.resolved_version or "(unversioned)",
            available=str(best),
            update_kind=diff_versions(m.resolved_version, str(best)),
        ))
    return out
