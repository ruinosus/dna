"""Vendored semver — npm-style constraints, no external deps.

Phase 10. Used by the Module catalog to resolve version constraints
in lockfiles ("does ``^1.2.0`` allow ``1.4.2``?", "what's the highest
version satisfying ``~1.2.3``?").

Supports:
  - SemVer 2.0 cores: MAJOR.MINOR.PATCH
  - Optional pre-release tag: ``1.2.3-rc.1`` (sorts BEFORE 1.2.3)
  - Optional build metadata: ``1.2.3+sha.abc`` (ignored for ordering)
  - Constraint operators: ``=``, ``^``, ``~``, ``>``, ``>=``, ``<``,
    ``<=``, wildcard ``x``/``*``, range ``>=1.2.3 <2.0.0``

Excludes (intentional, out of scope):
  - npm's range syntax ``1.2.3 - 1.4.0`` (hyphen). Use ``>=1.2.3 <=1.4.0``.
  - ``||`` alternation. Use multiple constraints if you need it.

The 0.0.0-unversioned sentinel: a Module with ``spec.version is None``
sorts as ``Version("0.0.0-unversioned")`` — lower than any real
release, so the outdated/update flow naturally skips it (no real
release ever satisfies a constraint of ``unversioned``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering


_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z\-.]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z\-.]+))?$"
)


class InvalidVersion(ValueError):
    """Raised when a string can't be parsed as semver."""


class InvalidConstraint(ValueError):
    """Raised when a constraint string is malformed."""


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str | int, ...] = ()
    build: str = ""

    @classmethod
    def parse(cls, s: str) -> Version:
        m = _SEMVER_RE.match(s.strip())
        if not m:
            raise InvalidVersion(f"not a semver string: {s!r}")
        pre_str = m.group("pre") or ""
        pre_parts: tuple[str | int, ...] = ()
        if pre_str:
            parts: list[str | int] = []
            for p in pre_str.split("."):
                if p.isdigit():
                    parts.append(int(p))
                else:
                    parts.append(p)
            pre_parts = tuple(parts)
        return cls(
            major=int(m["major"]),
            minor=int(m["minor"]),
            patch=int(m["patch"]),
            prerelease=pre_parts,
            build=m.group("build") or "",
        )

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            s += "-" + ".".join(str(p) for p in self.prerelease)
        if self.build:
            s += "+" + self.build
        return s

    def _core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._core() == other._core() and self.prerelease == other.prerelease

    def __lt__(self, other: Version) -> bool:
        if self._core() != other._core():
            return self._core() < other._core()
        # SemVer 2.0 §11: prerelease versions sort BEFORE the same core
        # without prerelease.
        if not self.prerelease and other.prerelease:
            return False
        if self.prerelease and not other.prerelease:
            return True
        # Both have prerelease — compare segment by segment.
        for a, b in zip(self.prerelease, other.prerelease):
            if a == b:
                continue
            if isinstance(a, int) and isinstance(b, int):
                return a < b
            if isinstance(a, int):  # numeric < alpha
                return True
            if isinstance(b, int):
                return False
            return str(a) < str(b)
        return len(self.prerelease) < len(other.prerelease)

    def is_unversioned(self) -> bool:
        return self.prerelease == ("unversioned",) and self._core() == (0, 0, 0)


UNVERSIONED = Version(0, 0, 0, prerelease=("unversioned",))


def parse(s: str | None) -> Version:
    """Parse ``s`` into a Version. ``None``/empty → UNVERSIONED sentinel."""
    if not s:
        return UNVERSIONED
    return Version.parse(s)


# ─────────────────────────────────────────────────────────────────────
# Constraints
# ─────────────────────────────────────────────────────────────────────

_OPS = ("=", "^", "~", ">=", ">", "<=", "<")


@dataclass(frozen=True)
class _Bound:
    op: str  # one of: =, >, >=, <, <=
    version: Version

    def matches(self, v: Version) -> bool:
        if self.op == "=":
            return v == self.version
        if self.op == ">":
            return v > self.version
        if self.op == ">=":
            return v >= self.version
        if self.op == "<":
            return v < self.version
        if self.op == "<=":
            return v <= self.version
        raise InvalidConstraint(f"unknown op {self.op!r}")


def _expand_caret(v: Version) -> list[_Bound]:
    # ^1.2.3 → >=1.2.3 <2.0.0 (compatible-major)
    # ^0.2.3 → >=0.2.3 <0.3.0 (npm convention: 0.x is treated minor-as-major)
    # ^0.0.3 → >=0.0.3 <0.0.4 (0.0.x patch-as-major)
    lo = _Bound(">=", v)
    if v.major > 0:
        hi = _Bound("<", Version(v.major + 1, 0, 0))
    elif v.minor > 0:
        hi = _Bound("<", Version(0, v.minor + 1, 0))
    else:
        hi = _Bound("<", Version(0, 0, v.patch + 1))
    return [lo, hi]


def _expand_tilde(v: Version) -> list[_Bound]:
    # ~1.2.3 → >=1.2.3 <1.3.0
    return [
        _Bound(">=", v),
        _Bound("<", Version(v.major, v.minor + 1, 0)),
    ]


def _expand_wildcard(s: str) -> list[_Bound]:
    # 1.2.x  → >=1.2.0 <1.3.0
    # 1.x    → >=1.0.0 <2.0.0
    # *      → no bounds (matches everything)
    if s.strip() in ("*", "x", "X"):
        return []
    parts = s.strip().split(".")
    if len(parts) == 2:  # "1.x"
        major = int(parts[0])
        return [
            _Bound(">=", Version(major, 0, 0)),
            _Bound("<", Version(major + 1, 0, 0)),
        ]
    if len(parts) == 3 and parts[2].lower() in ("x", "*"):  # "1.2.x"
        major, minor = int(parts[0]), int(parts[1])
        return [
            _Bound(">=", Version(major, minor, 0)),
            _Bound("<", Version(major, minor + 1, 0)),
        ]
    raise InvalidConstraint(f"bad wildcard {s!r}")


def _parse_atom(atom: str) -> list[_Bound]:
    s = atom.strip()
    if not s:
        return []
    if "x" in s.lower() or s == "*":
        return _expand_wildcard(s)
    if s.startswith("^"):
        return _expand_caret(Version.parse(s[1:]))
    if s.startswith("~"):
        return _expand_tilde(Version.parse(s[1:]))
    for op in (">=", "<=", ">", "<", "="):
        if s.startswith(op):
            return [_Bound(op, Version.parse(s[len(op):]))]
    # Bare version → exact match
    return [_Bound("=", Version.parse(s))]


@dataclass(frozen=True)
class Constraint:
    """Conjunction of bounds. Use ``Constraint.parse`` to construct."""
    bounds: tuple[_Bound, ...]
    raw: str

    @classmethod
    def parse(cls, s: str) -> Constraint:
        bounds: list[_Bound] = []
        # Whitespace separates atoms in a range; commas accepted too.
        atoms = [a for a in re.split(r"[\s,]+", s.strip()) if a]
        for atom in atoms:
            bounds.extend(_parse_atom(atom))
        return cls(tuple(bounds), s)

    def matches(self, v: Version) -> bool:
        # Unversioned never satisfies a real constraint.
        if v.is_unversioned():
            return False
        return all(b.matches(v) for b in self.bounds)

    def __str__(self) -> str:
        return self.raw


def max_satisfying(versions: list[Version], constraint: str) -> Version | None:
    """Return the highest version in ``versions`` that satisfies the
    constraint, or None if nothing matches."""
    c = Constraint.parse(constraint)
    candidates = [v for v in versions if c.matches(v)]
    if not candidates:
        return None
    return max(candidates)


def is_outdated(installed: str | None, available: list[str], constraint: str) -> bool:
    """True iff a higher-than-installed version satisfying the
    constraint is available."""
    inst = parse(installed)
    versions = [Version.parse(s) for s in available if s]
    best = max_satisfying(versions, constraint)
    if best is None:
        return False
    return best > inst
