"""BundleHandle — source-agnostic view of a single bundle directory.

A bundle is a logical container holding a marker file (AGENTS.md, SOUL.md,
SAFETYPOLICY.md, program.md, ...) plus optional sidecar files (scripts/,
references/, IDENTITY.md, etc.). Readers and writers receive a BundleHandle
and operate through this interface instead of pathlib / os.path — so the
same reader works whether the bundle lives on the filesystem, in a Postgres
row group, or in S3 / GCS / etc.

Background: Phase 8 audit (docs/superpowers/plans/2026-04-24-phase-8-port-cleanliness.md)
found that ReaderPort.detect/read and WriterPort.write were typed `path: Path`,
forcing every backing store to materialise a real filesystem dir before
invoking readers — which Postgres / S3 cannot do. By switching to
`BundleHandle`, Postgres adapter (PR2) can implement `PostgresBundleHandle`
backed by an `dna_bundle_entries` table and reuse all existing readers.

Migration philosophy: existing readers get a backward-compat escape hatch
via ``handle.path: Path | None`` — when the handle wraps a real directory,
the property returns it; otherwise None. Code that genuinely needs Path
semantics (e.g. shutil.copy) can opt in explicitly. The expectation is
that this property goes away over time as more backends ship.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable


@runtime_checkable
class BundleHandle(Protocol):
    """Source-agnostic interface for reading + writing a bundle's entries.

    Implementations:
      - ``FilesystemBundleHandle`` (this module) — wraps ``pathlib.Path``.
      - ``DictBundleHandle`` (this module) — in-memory, used in tests.
      - ``DictBundleHandle`` is also how the SQL adapter serves bundles —
        hydrated from ``dna_bundle_entries`` rows.

    Entry naming convention: a posix-style relative path inside the bundle.
    Top-level entries are bare names (``"SAFETYPOLICY.md"``,
    ``"IDENTITY.md"``); nested entries use forward slashes
    (``"scripts/run.py"``, ``"references/spec.md"``).
    """

    @property
    def name(self) -> str:
        """Bundle directory name (e.g. ``'talent-screener'``,
        ``'pii-ml-filter'``). Used by readers as a default doc name when
        the marker frontmatter omits ``metadata.name``.
        """
        ...

    def exists(self, entry: str) -> bool:
        """True if the named entry (file or directory) exists in this bundle."""
        ...

    def read_text(self, entry: str, encoding: str = "utf-8") -> str:
        """Read entry content as text. Raises ``FileNotFoundError`` if absent."""
        ...

    def read_bytes(self, entry: str) -> bytes:
        """Read entry content as bytes. Raises ``FileNotFoundError`` if absent."""
        ...

    def iter_entries(self, *, recursive: bool = False) -> Iterator[str]:
        """Yield entry names (relative to the bundle root).

        When ``recursive=False`` (default), only direct children are
        yielded — both regular files and subdirectories (e.g. ``"scripts"``).
        When ``recursive=True``, descend into subdirectories yielding only
        regular files (no directory entries) using forward-slash separators.
        """
        ...

    def is_file(self, entry: str) -> bool:
        """True if ``entry`` points at a regular file (not a directory).
        Used by readers that filter out subdirs from ``iter_entries()``.
        """
        ...

    def write_text(self, entry: str, content: str, encoding: str = "utf-8") -> None:
        """Write text content to the entry, creating parent dirs as needed.

        Read-only handles MUST raise ``NotImplementedError`` (or a subclass).
        """
        ...

    def write_bytes(self, entry: str, content: bytes) -> None:
        """Write bytes content. Read-only handles raise ``NotImplementedError``."""
        ...

    @property
    def path(self) -> Path | None:
        """Filesystem path when the handle wraps a real directory; ``None``
        otherwise.

        ESCAPE HATCH — prefer the explicit read/write/iter methods. Use this
        only when an external library demands a real ``Path`` (e.g.
        ``shutil.copy``, ``ZipFile``, third-party tooling that takes paths).
        Code paths that need this should gracefully degrade when ``None``.
        """
        ...


# ---------------------------------------------------------------------------
# Filesystem implementation
# ---------------------------------------------------------------------------


class FilesystemBundleHandle:
    """``BundleHandle`` backed by a real filesystem directory.

    Constructed by ``FilesystemSource.load_all`` for each detected bundle
    and passed to the matching reader's ``read(handle)`` method.
    """

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def name(self) -> str:
        return self._root.name

    def exists(self, entry: str) -> bool:
        return (self._root / entry).exists()

    def read_text(self, entry: str, encoding: str = "utf-8") -> str:
        return (self._root / entry).read_text(encoding=encoding)

    def read_bytes(self, entry: str) -> bytes:
        return (self._root / entry).read_bytes()

    def iter_entries(self, *, recursive: bool = False) -> Iterator[str]:
        if not self._root.is_dir():
            return
        if recursive:
            for child in self._root.rglob("*"):
                if child.is_file():
                    yield child.relative_to(self._root).as_posix()
        else:
            for child in self._root.iterdir():
                yield child.name

    def is_file(self, entry: str) -> bool:
        return (self._root / entry).is_file()

    def write_text(self, entry: str, content: str, encoding: str = "utf-8") -> None:
        target = self._root / entry
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)

    def write_bytes(self, entry: str, content: bytes) -> None:
        target = self._root / entry
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    @property
    def path(self) -> Path | None:
        return self._root


# ---------------------------------------------------------------------------
# In-memory implementation (testing + reader audits)
# ---------------------------------------------------------------------------


class DictBundleHandle:
    """``BundleHandle`` backed by an in-memory ``dict[str, str | bytes]``.

    Use in tests and reader audits to verify that a reader works
    independent of the filesystem. ``path`` returns ``None`` so any
    Path-dependent code path raises a recognisable failure.

    Example:
        >>> handle = DictBundleHandle("my-skill", {
        ...     "SKILL.md": "---\\nname: my-skill\\n---\\nbody",
        ...     "scripts/run.py": "print('hi')",
        ... })
        >>> handle.read_text("SKILL.md")
        '---\\nname: my-skill\\n---\\nbody'
    """

    def __init__(self, name: str, entries: dict[str, str | bytes]) -> None:
        self._name = name
        # Normalise entries: store text as-is, bytes as-is.
        self._entries: dict[str, str | bytes] = dict(entries)

    @property
    def name(self) -> str:
        return self._name

    def exists(self, entry: str) -> bool:
        if entry in self._entries:
            return True
        # Match directory prefixes — e.g. "scripts" exists if any entry
        # starts with "scripts/".
        prefix = entry.rstrip("/") + "/"
        return any(k.startswith(prefix) for k in self._entries)

    def read_text(self, entry: str, encoding: str = "utf-8") -> str:
        v = self._require(entry)
        if isinstance(v, bytes):
            return v.decode(encoding)
        return v

    def read_bytes(self, entry: str) -> bytes:
        v = self._require(entry)
        if isinstance(v, str):
            return v.encode("utf-8")
        return v

    def iter_entries(self, *, recursive: bool = False) -> Iterator[str]:
        if recursive:
            for k in self._entries:
                yield k
            return
        seen: set[str] = set()
        for k in self._entries:
            top = k.split("/", 1)[0]
            if top not in seen:
                seen.add(top)
                yield top

    def is_file(self, entry: str) -> bool:
        return entry in self._entries

    def write_text(self, entry: str, content: str, encoding: str = "utf-8") -> None:
        self._entries[entry] = content

    def write_bytes(self, entry: str, content: bytes) -> None:
        self._entries[entry] = content

    @property
    def path(self) -> Path | None:
        return None

    def _require(self, entry: str) -> str | bytes:
        try:
            return self._entries[entry]
        except KeyError as e:
            raise FileNotFoundError(
                f"DictBundleHandle({self._name!r}) has no entry {entry!r}"
            ) from e


__all__ = [
    "BundleHandle",
    "FilesystemBundleHandle",
    "DictBundleHandle",
]
