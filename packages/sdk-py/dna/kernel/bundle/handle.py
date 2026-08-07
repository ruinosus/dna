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

    An ``entry`` is a PATH, and that is what distinguishes it from an instance
    ``name`` — see the note on ``FilesystemBundleHandle._entry_path``. Every
    implementation is expected to hold ``dna.kernel.errors.validate_bundle_entry``:
    the rule is part of the CONTRACT, not one backend's defensive habit,
    because a traversing entry is a filesystem escape on one backend and a
    malformed ``dna_bundle_entries`` row on the others — an escape deferred
    until something materialises it.
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

    def _entry_path(self, entry: str, *, resolve_leaf: bool = False) -> Path:
        """Validate ``entry``, join it onto the bundle root, and refuse the
        result unless it stays under that root.

        ``resolve_leaf`` selects WHICH containment rule applies, and the
        DIRECTION of the operation decides it — see "THE CARVE-OUT" below.
        Mutating callers (``write_text`` / ``write_bytes``) pass ``True`` and
        the whole path INCLUDING the leaf is resolved; read-only callers
        (``read_text`` / ``read_bytes`` / ``exists`` / ``is_file``) leave it
        ``False`` and only the parent chain is resolved.

        ``entry`` VS ``name`` — the divergence this method exists to close.
        An instance ``name`` (and a ``scope``) is ONE path component; an
        ``entry`` is a relative PATH anchored at the bundle root, and it
        legitimately contains ``/``. Same concept — caller-influenced text that
        becomes a location on disk — behind two different doors, held to two
        different rules (``validate_instance_name`` vs
        ``validate_bundle_entry``). ``606812c`` guarded the first door and
        ``887e858`` its read half; THIS door stayed open, and that is not a
        coincidence a reader should have to rediscover: when one of a pair is
        guarded and the other is not, the unguarded one is where the escape
        goes.

        And it went there. The escape was not a caller handing a crafted
        ``entry`` to a bundle-entry door — those were closed — it was that
        writers DERIVE entries from instance CONTENT (``spec.source_files``,
        ``spec.root_files``, ``spec.scripts|references|assets``,
        ``spec.extras``, ``spec.instruction_file``), and ``spec`` is caller
        input all the way from ``PUT /v1/definitions/{kind}/{name}``. Measured
        through ``Kernel.write_instance`` on the default ``Agent`` Kind: every
        one of those fields wrote a file outside the store root, on the base
        lane and the tenant lane, and an ABSOLUTE entry wrote to an arbitrary
        absolute path — a ``pathlib`` join DISCARDS the left operand when the
        right one is absolute, so no amount of store depth absorbs it.

        WHY HERE. This handle is the one door every writer must pass. Eight
        in-repo writers call ``bundle.write_text(f["relativePath"], …)``
        directly instead of the shared ``write_entries_to_handle`` sink, and
        ``spec.source_files`` is a kind-AGNOSTIC convention — so a guard per
        writer, or per Kind, would have repeated the enumeration mistake that
        caused the miss in the first place. One check where the path is built
        covers the writer somebody adds tomorrow.

        TWO CHECKS, not one, and neither is redundant:

        1. ``validate_bundle_entry`` refuses by SHAPE — absolute, ``..``,
           ``.``, NUL, backslash, over-long. It names the fault, so the caller
           can fix the field, and it fires identically on every backend.
        2. Containment refuses by RESOLVED LOCATION — what no textual rule can
           see: a SUBDIRECTORY inside the bundle that is itself a symlink
           pointing out of it, which relocates every entry written beneath it.
           Exactly the belt-and-braces relationship
           ``FilesystemSource._contained`` has with ``validate_instance_name``
           — do not delete either as duplicated work.

        THE CARVE-OUT, and it is ASYMMETRIC — the first version applied it in
        both directions and that was a live escape.

        On a READ, only the entry's PARENT CHAIN is resolved: a symlinked LEAF
        is followed and allowed. That is drawn around a real, supported
        pattern — this repo's own root ``AGENTS.md`` is symlinked INTO a scope
        (``tests/test_agents_md_root.py``) and is READ through this handle, so
        refusing a symlinked file would break it. On a read, a symlinked file
        is just content: following it discloses a file somebody with write
        access to the bundle directory deliberately pointed at.

        On a WRITE it is not content, it is an escape primitive. Measured
        before this parameter existed: ``write_text`` through a symlinked leaf
        was ACCEPTED, and the file OUTSIDE the bundle then read
        ``'OVERWRITTEN FROM INSIDE THE BUNDLE'``; ``write_bytes`` the same. The
        asymmetry is the whole point — planting a link costs an attacker one
        file inside the bundle, and a SYNCED OR CLONED bundle can carry one it
        did not author, so the write side must not trust it. Hence
        ``resolve_leaf=True`` on every mutating method, which resolves the leaf
        too and refuses when it lands outside.

        A symlinked DIRECTORY is refused in BOTH directions — it silently
        relocates a whole subtree, and anything written under it lands wherever
        the link points.

        NOT the same line as ``FilesystemSource._contained``, and an earlier
        version of this docstring claimed it was. ``_contained``
        (``adapters/filesystem/source.py``) resolves the WHOLE path including
        the leaf, unconditionally — it has no carve-out. What is true is that
        it never RUNS on the content files reached by a directory scan, so a
        symlinked ``AGENTS.md`` survives it; that is a consequence of where it
        is called, not a rule it deliberately relaxes. Two different things.
        Do not "restore parity" by weakening either one.

        COST. ``Path.resolve()`` is a realpath — an lstat per component — and
        it is paid on every entry READ as well as every write, so it sits on
        the ``load_all`` hot path (see the same note on
        ``FilesystemSource._contained``). Chosen over ``os.path.normpath``
        deliberately: ``normpath`` is textual and blind to the symlinked
        directory above, and a containment check a symlink defeats is not a
        containment check. Measured before adopting it: zero symlinks under any
        ``.dna/`` tree in either repo, so in practice nothing pays for a lookup
        that finds anything.
        """
        from dna.kernel.errors import PathEscapesStoreRoot, validate_bundle_entry

        validate_bundle_entry(entry)
        target = self._root / entry
        root = self._root.resolve()
        if resolve_leaf:
            # MUTATING call — resolve the LEAF too. ``Path.resolve()`` is
            # non-strict, so an entry that does not exist yet resolves to its
            # own literal location (the ordinary case); an entry that IS a
            # symlink resolves to wherever it points, which is what this
            # catches.
            checked = target.resolve()
        else:
            # READ call — the PARENT chain only, so a symlinked leaf stays
            # readable. ``entry`` has already been proven free of
            # ``..``/absolute segments, so the leaf is a plain component and
            # cannot move the location by itself.
            checked = target.parent.resolve()
        if checked != root and root not in checked.parents:
            raise PathEscapesStoreRoot(
                f"bundle entry {entry!r} resolves to {str(checked)!r}, which "
                f"is outside the bundle root {str(root)!r}. The entry passed "
                f"the shape rule, so something ON ITS PATH is a link or a "
                f"mount pointing out of the bundle. The bundle is the "
                f"boundary: fix the link, do not widen this check. (A "
                f"symlinked DIRECTORY is refused in both directions. A "
                f"symlinked FILE is readable on purpose — this repo symlinks "
                f"its root AGENTS.md into a scope — but is NOT writable "
                f"through, because following it on a write puts the bytes "
                f"outside the bundle.)"
            )
        return target

    @property
    def name(self) -> str:
        return self._root.name

    def exists(self, entry: str) -> bool:
        return self._entry_path(entry).exists()

    def read_text(self, entry: str, encoding: str = "utf-8") -> str:
        return self._entry_path(entry).read_text(encoding=encoding)

    def read_bytes(self, entry: str) -> bytes:
        return self._entry_path(entry).read_bytes()

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
        return self._entry_path(entry).is_file()

    # The two MUTATING methods — ``resolve_leaf=True``. A symlinked leaf is
    # content on a read and an escape primitive on a write; see the asymmetry
    # in ``_entry_path``. If a third mutating method is ever added here, it
    # passes ``resolve_leaf=True`` too.
    def write_text(self, entry: str, content: str, encoding: str = "utf-8") -> None:
        target = self._entry_path(entry, resolve_leaf=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)

    def write_bytes(self, entry: str, content: bytes) -> None:
        target = self._entry_path(entry, resolve_leaf=True)
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
        self._validate(entry)
        self._entries[entry] = content

    def write_bytes(self, entry: str, content: bytes) -> None:
        self._validate(entry)
        self._entries[entry] = content

    @staticmethod
    def _validate(entry: str) -> None:
        """Hold the same entry rule the filesystem handle holds.

        WRITES only, deliberately — and the asymmetry with
        ``FilesystemBundleHandle`` (which validates reads too) is the same
        distinction both times: that handle validates wherever it BUILDS A
        PATH, and a read builds one. Here a read is a dict lookup that cannot
        escape anything.

        A write can, later. This handle is how the SQL adapters serve and
        persist bundles, so its keys become ``dna_bundle_entries`` rows, and a
        row carrying ``../../../etc/cron.d/pwn`` escapes the moment anything
        materialises the bundle onto a filesystem (``dna emit``, a sync to an
        FS source, the rw-conformance kit). Refusing at the write keeps the
        escape from being STORED, which is the only place it can still be
        refused cheaply.
        """
        from dna.kernel.errors import validate_bundle_entry

        validate_bundle_entry(entry)

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
