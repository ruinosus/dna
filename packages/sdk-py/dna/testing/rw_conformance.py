"""Reader/Writer round-trip conformance kit (s-dna-rw-roundtrip-suite).

The behavioral counterpart of the ``kernel.reader()`` / ``kernel.writer()``
boot gates. The gates check that the ReaderPort/WriterPort surface exists
BY NAME (``runtime_checkable`` Protocols can't do more); THIS suite checks
that the surfaces BEHAVE — for EVERY reader/writer pair registered in a
kernel, it enforces the round-trip invariant that is the thesis of the
notation (spec §2.1): the writer re-emits what the reader read, and the
emit→read→emit cycle is a fixpoint (the first write is the only
normalization that ever happens).

Per registered Kind that has a claiming writer, the suite generates:

  * ``serialize_shape``       — ``serialize()`` returns well-shaped entries
    (``relativePath`` + ``content`` XOR ``content_bytes``), non-empty.
  * ``write_serialize_coherent`` — ``write(bundle, raw)`` produces exactly
    the same file tree as materializing ``serialize(raw)``. The two
    surfaces of WriterPort must not drift.
  * ``writer_output_readable`` — a registered reader ``detect()``s the
    emitted bundle (container-aware, same routing as the scanner) and
    ``read()``s it back to the same Kind with the fixture's name.
  * ``round_trip_fixpoint``   — ``serialize(read(materialize(serialize(raw))))``
    equals the first ``serialize(raw)`` byte-for-byte.

Plus, for every REAL bundle found under ``real_bundle_roots`` (e.g. the
market-integration scope with real marketplace Skills / souls / AGENTS.md):

  * ``real_roundtrip:<container>/<name>`` — read the real artifact, emit,
    re-read, re-emit: the two emits must be byte-identical and the Kind
    stable. (Byte-fidelity against the ORIGINAL disk bytes, with its
    documented normalization allowlist, lives in the market-conformance
    suite; this kit enforces the format-agnostic fixpoint every pair must
    honor, including third-party ones.)

Consumption contract
--------------------

``reader_writer_conformance_suite(kernel_factory)`` returns a list of
:class:`RWConformanceCase`. ``kernel_factory`` is a zero-arg callable
returning a LOADED kernel (e.g. ``Kernel.auto()``); it is called once at
suite-construction time (readers/writers are stateless — cases don't
mutate the kernel). Each ``case.run()`` is synchronous and uses temp
dirs it cleans up itself.

Kinds whose default synthetic fixture doesn't satisfy a hand-rolled
writer can be overridden via ``fixtures={kind: raw_dict}``.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dna.kernel.bundle_handle import FilesystemBundleHandle
from dna.testing.source_conformance import CaseNotApplicable

KernelFactory = Callable[[], Any]

#: Fixture-name prefix — every synthetic bundle is named ``rw-kit-<slug>``.
FIXTURE_NAME_PREFIX = "rw-kit-"


def default_fixture(kind_port: Any) -> dict[str, Any]:
    """Minimal synthetic raw doc for a Kind, derived from its
    StorageDescriptor (``body_field`` when declared, ``content``
    otherwise). Override per-kind via the ``fixtures`` argument when a
    hand-rolled writer needs richer spec."""
    sd = getattr(kind_port, "storage", None)
    body_field = (getattr(sd, "body_field", None) or "content") if sd else "content"
    name = FIXTURE_NAME_PREFIX + kind_port.kind.lower()
    return {
        "apiVersion": kind_port.api_version,
        "kind": kind_port.kind,
        "metadata": {
            "name": name,
            "description": "Round-trip conformance kit fixture.",
        },
        "spec": {body_field: "Round-trip conformance kit body.\n"},
    }


# Spec seeds for builtin Kinds whose hand-rolled writers key off specific
# fields (merged over the default fixture's spec). Keys that aren't
# registered in the kernel under test are simply ignored, so this table
# can list Kinds from extensions that don't ship everywhere.
DEFAULT_SPEC_SEEDS: dict[str, dict[str, Any]] = {
    "Skill": {"instruction": "Round-trip conformance kit instruction.\n"},
    "Soul": {"soul_content": "## Personality\n\nRound-trip kit soul.\n"},
    "Agent": {"instruction": "Round-trip conformance kit instruction.\n"},
    "AgentProgram": {"instruction": "Round-trip conformance kit program.\n"},
    "Research": {"synthesis": "Round-trip conformance kit synthesis.\n"},
    # GraphifyArtifact bundles are only valid WITH their graph.json payload
    # (the dedicated reader's detect() requires it); without one the bundle
    # falls to the generic MANIFEST.md reader, which reads a different
    # shape than the dedicated writer emits.
    "GraphifyArtifact": {"graph_data": {"nodes": [], "links": []}},
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _materialize(entries: list[dict[str, Any]], bundle_dir: Path) -> None:
    """Write serialize() entries into ``bundle_dir`` (text + binary)."""
    for f in entries:
        target = bundle_dir / f["relativePath"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if "content_bytes" in f:
            target.write_bytes(f["content_bytes"])
        else:
            target.write_text(f["content"], encoding="utf-8")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _entries_bytes(entries: list[dict[str, Any]]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for f in entries:
        payload = f["content_bytes"] if "content_bytes" in f \
            else f["content"].encode("utf-8")
        out[f["relativePath"]] = payload
    return out


def _ordered_readers(readers: tuple[Any, ...] | list[Any], container: str) -> list[Any]:
    """Scanner-equivalent routing: container-owned readers first, unscoped
    fallback second, foreign-container readers excluded (H3)."""
    owned = [r for r in readers if r._owner_container == container]
    unscoped = [r for r in readers if r._owner_container is None]
    return owned + unscoped


def _detecting_reader(readers: Any, bundle_dir: Path) -> Any | None:
    handle = FilesystemBundleHandle(bundle_dir)
    for r in _ordered_readers(readers, bundle_dir.parent.name):
        try:
            if r.detect(handle):
                return r
        except Exception:  # noqa: BLE001 — detect() is a probe (scanner parity)
            continue
    return None


def _assert_entry_shape(entries: Any, who: str) -> None:
    assert isinstance(entries, list) and entries, (
        f"{who}.serialize() must return a NON-EMPTY list of entries "
        f"(got {entries!r}) — a writer that emits nothing round-trips nothing."
    )
    for f in entries:
        assert isinstance(f, dict) and isinstance(f.get("relativePath"), str), (
            f"{who}.serialize() entry missing str relativePath: {f!r}"
        )
        has_text = isinstance(f.get("content"), str)
        has_bytes = isinstance(f.get("content_bytes"), (bytes, bytearray))
        assert has_text != has_bytes, (
            f"{who}.serialize() entry {f.get('relativePath')!r} must carry "
            f"exactly one of content (str) / content_bytes (bytes)."
        )


# ---------------------------------------------------------------------------
# case implementations — each receives a bound _PairCtx
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _PairCtx:
    kind: str
    container: str
    raw: dict[str, Any]
    writer: Any
    readers: tuple[Any, ...]


def _case_serialize_shape(ctx: _PairCtx) -> None:
    _assert_entry_shape(ctx.writer.serialize(ctx.raw), type(ctx.writer).__name__)


def _case_write_serialize_coherent(ctx: _PairCtx) -> None:
    with tempfile.TemporaryDirectory(prefix="rw-kit-") as tmp:
        name = ctx.raw["metadata"]["name"]
        ser_dir = Path(tmp) / "ser" / ctx.container / name
        wri_dir = Path(tmp) / "wri" / ctx.container / name
        ser_dir.mkdir(parents=True)
        wri_dir.mkdir(parents=True)
        _materialize(ctx.writer.serialize(ctx.raw), ser_dir)
        ctx.writer.write(FilesystemBundleHandle(wri_dir), ctx.raw)
        ser_tree, wri_tree = _tree_bytes(ser_dir), _tree_bytes(wri_dir)
        assert ser_tree == wri_tree, (
            f"{type(ctx.writer).__name__}: write() and serialize() drift for "
            f"kind {ctx.kind} — serialize emitted {sorted(ser_tree)}, write "
            f"emitted {sorted(wri_tree)} (and/or contents differ). The two "
            f"surfaces must stay coherent (canonical impl: write = "
            f"write_entries_to_handle(bundle, self.serialize(raw)))."
        )


def _case_writer_output_readable(ctx: _PairCtx) -> None:
    with tempfile.TemporaryDirectory(prefix="rw-kit-") as tmp:
        name = ctx.raw["metadata"]["name"]
        bundle_dir = Path(tmp) / ctx.container / name
        bundle_dir.mkdir(parents=True)
        _materialize(ctx.writer.serialize(ctx.raw), bundle_dir)
        reader = _detecting_reader(ctx.readers, bundle_dir)
        assert reader is not None, (
            f"NO registered reader detect()s the bundle "
            f"{type(ctx.writer).__name__} emits for kind {ctx.kind} "
            f"(files: {sorted(_tree_bytes(bundle_dir))}) — the writer's "
            f"output is invisible to every scan; register a matching "
            f"ReaderPort or fix the marker."
        )
        raw2 = reader.read(FilesystemBundleHandle(bundle_dir))
        assert raw2.get("kind") == ctx.kind, (
            f"{type(reader).__name__} read the {ctx.kind} bundle back as "
            f"kind {raw2.get('kind')!r} — writer/reader pair mismatch."
        )
        got_name = (raw2.get("metadata") or {}).get("name")
        assert got_name == name, (
            f"identity lost in round-trip: wrote name {name!r}, "
            f"read back {got_name!r}."
        )


def _case_round_trip_fixpoint(ctx: _PairCtx) -> None:
    """The §2.1 idempotence invariant: starting from a READ raw (the
    writer-input fixture may legitimately be normalized once — e.g.
    body-trailing-whitespace canonicalization), every further
    emit→read→emit cycle must be a byte fixpoint."""
    with tempfile.TemporaryDirectory(prefix="rw-kit-") as tmp:
        name = ctx.raw["metadata"]["name"]

        def _cycle(raw: dict, step: str) -> tuple[list[dict], dict]:
            entries = ctx.writer.serialize(raw)
            bundle_dir = Path(tmp) / step / ctx.container / name
            bundle_dir.mkdir(parents=True)
            _materialize(entries, bundle_dir)
            reader = _detecting_reader(ctx.readers, bundle_dir)
            if reader is None:  # failed loudly in writer_output_readable
                raise CaseNotApplicable(
                    f"no reader detects {ctx.kind} output — see "
                    f"writer_output_readable failure."
                )
            return entries, reader.read(FilesystemBundleHandle(bundle_dir))

        _, raw2 = _cycle(ctx.raw, "normalize")   # one-time normalization
        second, raw3 = _cycle(raw2, "second")
        third, _ = _cycle(raw3, "third")
        assert _entries_bytes(third) == _entries_bytes(second), (
            f"{ctx.kind}: emit→read→emit is NOT a fixpoint even after the "
            f"one permitted normalization pass — the "
            f"{type(ctx.writer).__name__} pair loses or mutates data on "
            f"EVERY cycle. Second emit: {_entries_bytes(second)!r}; "
            f"third: {_entries_bytes(third)!r}."
        )


_PAIR_CASES: list[tuple[str, Callable[[_PairCtx], None]]] = [
    ("serialize_shape", _case_serialize_shape),
    ("write_serialize_coherent", _case_write_serialize_coherent),
    ("writer_output_readable", _case_writer_output_readable),
    ("round_trip_fixpoint", _case_round_trip_fixpoint),
]


def _case_real_roundtrip(
    readers: tuple[Any, ...], writers: tuple[Any, ...], bundle_dir: Path,
) -> None:
    reader = _detecting_reader(readers, bundle_dir)
    assert reader is not None  # enumeration guarantees detection
    raw1 = reader.read(FilesystemBundleHandle(bundle_dir))
    writer = next((w for w in writers if w.can_write(raw1)), None)
    if writer is None:
        raise CaseNotApplicable(
            f"real bundle {bundle_dir.name} read as kind "
            f"{raw1.get('kind')!r} which no registered writer claims."
        )
    first = writer.serialize(raw1)
    _assert_entry_shape(first, type(writer).__name__)
    with tempfile.TemporaryDirectory(prefix="rw-kit-real-") as tmp:
        re_dir = Path(tmp) / bundle_dir.parent.name / bundle_dir.name
        re_dir.mkdir(parents=True)
        _materialize(first, re_dir)
        re_reader = _detecting_reader(readers, re_dir)
        assert re_reader is not None, (
            f"re-emitted bundle for {bundle_dir.name} is undetectable — "
            f"{type(writer).__name__} does not re-emit the marker "
            f"{type(reader).__name__} keyed on."
        )
        raw2 = re_reader.read(FilesystemBundleHandle(re_dir))
        assert raw2.get("kind") == raw1.get("kind"), (
            f"real bundle {bundle_dir.name}: kind flipped from "
            f"{raw1.get('kind')!r} to {raw2.get('kind')!r} on re-read."
        )
        second = writer.serialize(raw2)
        assert _entries_bytes(second) == _entries_bytes(first), (
            f"real bundle {bundle_dir.parent.name}/{bundle_dir.name}: "
            f"emit→read→emit is not a fixpoint — data is lost or mutated "
            f"on every write cycle."
        )


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RWConformanceCase:
    """One runnable reader/writer conformance case."""

    name: str
    kind: str | None
    _fn: Callable[[], None] = field(repr=False)

    def run(self) -> None:
        """Run the case. Raises AssertionError on a broken invariant,
        :class:`CaseNotApplicable` (a skip) when the pair can't be
        exercised for an honest, documented reason."""
        self._fn()

    def __repr__(self) -> str:  # readable pytest ids
        return f"RWConformanceCase({self.name})"


def _iter_real_bundles(readers: tuple[Any, ...], root: Path) -> list[Path]:
    """Find real bundle dirs under a scope root: the root itself (standalone
    scope-root markers like AGENTS.md), depth-1 dirs and depth-2 dirs —
    the layouts the filesystem scanner walks."""
    candidates: list[Path] = [root]
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith((".", "_")):
            candidates.append(child)
            for grand in sorted(child.iterdir()):
                if grand.is_dir() and not grand.name.startswith((".", "_")):
                    candidates.append(grand)
    return [c for c in candidates if _detecting_reader(readers, c) is not None]


def reader_writer_conformance_suite(
    kernel_factory: KernelFactory,
    *,
    fixtures: dict[str, dict[str, Any]] | None = None,
    real_bundle_roots: list[Path | str] | None = None,
) -> list[RWConformanceCase]:
    """THE public round-trip conformance suite for Reader/Writer pairs.

    Args:
        kernel_factory: zero-arg callable returning a LOADED kernel
            (``Kernel.auto()``, or a hand-wired kernel with your
            extension). Called once — readers/writers are stateless.
        fixtures: per-kind raw-document overrides for Kinds whose
            hand-rolled writer needs a richer spec than the synthetic
            default (see :func:`default_fixture`).
        real_bundle_roots: scope directories holding REAL bundles (e.g.
            ``scopes/market-integration/.dna/market-demo``); every bundle
            a registered reader detects gains a ``real_roundtrip`` case.

    Returns:
        list of :class:`RWConformanceCase` — parametrize in pytest
        (``ids=lambda c: c.name``) and call ``case.run()``.
    """
    kernel = kernel_factory()
    kernel._ensure_generic_readers_writers()
    readers = tuple(kernel.active_readers)
    writers = tuple(kernel.active_writers)
    fixtures = fixtures or {}

    cases: list[RWConformanceCase] = []
    for kp in kernel._kinds.values():
        kind = kp.kind
        raw = fixtures.get(kind)
        if raw is None:
            raw = default_fixture(kp)
            raw["spec"].update(DEFAULT_SPEC_SEEDS.get(kind, {}))
        writer = next((w for w in writers if w.can_write(raw)), None)
        sd = getattr(kp, "storage", None)
        container = (getattr(sd, "container", None) or "bundles") if sd else "bundles"
        if writer is None:
            # Not a bundle-writable Kind (pure-YAML records etc.) — one
            # explicit skip so the matrix stays honest instead of silent.
            def _skip(kind: str = kind) -> None:
                raise CaseNotApplicable(
                    f"kind {kind} has no registered writer — nothing to "
                    f"round-trip (YAML-record kinds are exercised by the "
                    f"source conformance kit instead)."
                )
            cases.append(RWConformanceCase(
                name=f"{kind}:no_writer", kind=kind, _fn=_skip,
            ))
            continue
        ctx = _PairCtx(
            kind=kind, container=container, raw=raw,
            writer=writer, readers=readers,
        )
        for case_name, fn in _PAIR_CASES:
            cases.append(RWConformanceCase(
                name=f"{kind}:{case_name}", kind=kind,
                _fn=(lambda fn=fn, ctx=ctx: fn(ctx)),
            ))

    for root in (real_bundle_roots or []):
        root = Path(root)
        if not root.is_dir():
            raise FileNotFoundError(
                f"real_bundle_roots entry does not exist: {root}"
            )
        for bundle_dir in _iter_real_bundles(readers, root):
            rel = bundle_dir.relative_to(root.parent).as_posix()
            cases.append(RWConformanceCase(
                name=f"real_roundtrip:{rel}", kind=None,
                _fn=(lambda b=bundle_dir: _case_real_roundtrip(readers, writers, b)),
            ))

    return cases
