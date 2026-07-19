"""s-engram-rename — the ``scripts/migrate_lesson_learned_to_engram.py`` data
migration.

Kind resolution is an exact ``(apiVersion, kind)`` lookup with no fallback
(``kernel/instance.py:686``) — a stored ``LessonLearned`` doc is invisible to
the renamed ``Engram`` KindPort the instant the SDK pin advances, hence the
one-time rewrite. These tests drive the script's importable functions
directly against a scratch directory tree (never touching real ``.dna/``
data) and pin:

  * dry-run reports without writing;
  * ``--apply`` rewrites ONLY the two envelope fields, with the rest of the
    file — including line endings and trailing-newline-or-not — EXACT
    byte-for-byte (full-content ``==``, not a substring ``in`` check, which
    is exactly the class of bug (dropped trailing newline, CRLF silently
    normalized to LF) that a substring check would hide);
  * cross-reference strings deeper in the doc are left alone;
  * re-running is idempotent (no double-rewrite, no drift);
  * a half-migrated doc (``kind: Engram`` + a stale/missing ``apiVersion``)
    is reported as an ORPHAN error, never silently treated as "already
    migrated" — that half-state resolves under NEITHER identity;
  * writes are atomic (no partial file survives a write, no leftover temp
    file after a successful run).

The script lives at ``scripts/migrate_lesson_learned_to_engram.py``; we
import it by path (scripts/ isn't a package), mirroring
``test_seed_workspace_one.py``.
"""
from __future__ import annotations

import importlib.util
import pathlib

_SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "scripts" / "migrate_lesson_learned_to_engram.py"
)


def _load_script_module():
    import sys

    spec = importlib.util.spec_from_file_location(
        "migrate_lesson_learned_to_engram", _SCRIPT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Register before exec: the script's @dataclass (with `from __future__
    # import annotations`) resolves its own module via sys.modules at class
    # creation time — module_from_spec alone doesn't register it yet.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mig = _load_script_module()

_OLD_DOC = """kind: LessonLearned
metadata:
  name: rem-abc123
spec:
  summary: A test memory.
  area: testing
  surface_when:
  - feature_touched
  source_refs:
  - LessonLearned/rem-other
  affect: triumph
apiVersion: github.com/ruinosus/dna/sdlc/v1
"""

# The exact expected rewrite: ONLY the two envelope-field lines change,
# character for character elsewhere — including the trailing newline after
# `apiVersion:` (the last line), which a naive `\s*$` substitution eats.
_NEW_DOC = """kind: Engram
metadata:
  name: rem-abc123
spec:
  summary: A test memory.
  area: testing
  surface_when:
  - feature_touched
  source_refs:
  - LessonLearned/rem-other
  affect: triumph
apiVersion: github.com/ruinosus/dna/v1
"""

_UNRELATED_DOC = """kind: Story
metadata:
  name: s-unrelated
spec:
  title: not a memory
apiVersion: github.com/ruinosus/dna/sdlc/v1
"""


def _seed(tmp_path: pathlib.Path) -> pathlib.Path:
    lessons = tmp_path / "lessons-learned"
    lessons.mkdir()
    (lessons / "rem-abc123.yaml").write_text(_OLD_DOC, encoding="utf-8", newline="")
    (lessons / "unrelated.yaml").write_text(_UNRELATED_DOC, encoding="utf-8", newline="")
    return tmp_path


def _read_raw(path: pathlib.Path) -> str:
    """Read WITHOUT newline translation — the same way the script itself
    reads, so a test can tell a preserved CRLF from a silently-normalized
    LF (``Path.read_text`` alone would hide exactly that bug)."""
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


# ---------------------------------------------------------------------------
# dry run / apply / idempotency
# ---------------------------------------------------------------------------


def test_dry_run_reports_without_writing(tmp_path):
    root = _seed(tmp_path)
    report = mig.migrate([root], apply=False)
    assert report.scanned == 2
    assert len(report.found_old) == 1
    assert report.found_old[0].name == "rem-abc123.yaml"
    assert report.already_new == []
    assert report.migrated == []
    assert report.orphans == []
    # Nothing written — the file is untouched, EXACTLY (not just "close").
    assert _read_raw(root / "lessons-learned" / "rem-abc123.yaml") == _OLD_DOC


def test_apply_rewrites_only_the_two_envelope_fields(tmp_path):
    root = _seed(tmp_path)
    report = mig.migrate([root], apply=True)
    assert len(report.migrated) == 1

    rewritten = _read_raw(root / "lessons-learned" / "rem-abc123.yaml")
    # Exact full-content equality — catches a dropped trailing newline, a
    # stray whitespace change, or anything else a substring `in` check
    # would let slide.
    assert rewritten == _NEW_DOC

    # The unrelated Story doc is untouched, exactly.
    unrelated = _read_raw(root / "lessons-learned" / "unrelated.yaml")
    assert unrelated == _UNRELATED_DOC


def test_apply_is_idempotent(tmp_path):
    root = _seed(tmp_path)
    first = mig.migrate([root], apply=True)
    assert len(first.migrated) == 1
    after_first = _read_raw(root / "lessons-learned" / "rem-abc123.yaml")
    assert after_first == _NEW_DOC

    second = mig.migrate([root], apply=True)
    assert second.found_old == []
    assert second.migrated == []
    assert second.orphans == []
    assert len(second.already_new) == 1

    after_second = _read_raw(root / "lessons-learned" / "rem-abc123.yaml")
    assert after_second == after_first, "re-running must not touch an already-migrated doc"


def test_no_lesson_learned_docs_is_a_clean_zero_report(tmp_path):
    (tmp_path / "unrelated.yaml").write_text(_UNRELATED_DOC, encoding="utf-8", newline="")
    report = mig.migrate([tmp_path], apply=True)
    assert report.scanned == 1
    assert report.found_old == []
    assert report.migrated == []
    assert report.orphans == []
    assert report.errors == []


def test_missing_root_is_reported_as_an_error_not_a_crash(tmp_path):
    missing = tmp_path / "does-not-exist"
    report = mig.migrate([missing], apply=False)
    assert report.scanned == 0
    assert len(report.errors) == 1
    assert report.errors[0][0] == missing


# ---------------------------------------------------------------------------
# FIX 2 — half-migrated docs (kind: Engram + stale apiVersion) are ORPHANS,
# never silently classified as "already migrated"
# ---------------------------------------------------------------------------

_ORPHAN_DOC = """kind: Engram
metadata:
  name: rem-orphan
spec:
  summary: kind already renamed, apiVersion was never updated.
  area: testing
  surface_when:
  - feature_touched
  source_refs:
  - testing
  affect: triumph
apiVersion: github.com/ruinosus/dna/sdlc/v1
"""

_ORPHAN_NO_API_VERSION_DOC = """kind: Engram
metadata:
  name: rem-orphan-no-av
spec:
  summary: kind already renamed, apiVersion line missing entirely.
  area: testing
"""


def test_stale_api_version_is_an_orphan_not_a_silent_noop(tmp_path):
    """kind: Engram alone is NOT sufficient to call a doc migrated — Kind
    resolution is an exact (apiVersion, kind) 2-tuple with no fallback, so
    kind: Engram + apiVersion: .../sdlc/v1 resolves under NEITHER identity.
    Must be flagged, not silently skipped as already-migrated (that would
    make it an orphan this script can never surface again — `_classify`
    would keep calling it ALREADY_MIGRATED forever)."""
    lessons = tmp_path / "lessons-learned"
    lessons.mkdir()
    (lessons / "rem-orphan.yaml").write_text(_ORPHAN_DOC, encoding="utf-8", newline="")

    report = mig.migrate([tmp_path], apply=True)
    assert report.already_new == [], "a stale apiVersion must NOT count as already-migrated"
    assert report.found_old == [], "an orphan is not a rewrite candidate either"
    assert len(report.orphans) == 1
    assert report.orphans[0].name == "rem-orphan.yaml"
    assert len(report.errors) == 1
    assert report.errors[0][0] == lessons / "rem-orphan.yaml"
    assert "orphan" in report.errors[0][1].lower() or "apiVersion" in report.errors[0][1]

    # Never touched — apply=True must not "fix" an orphan by guessing.
    assert _read_raw(lessons / "rem-orphan.yaml") == _ORPHAN_DOC


def test_missing_api_version_is_also_an_orphan(tmp_path):
    lessons = tmp_path / "lessons-learned"
    lessons.mkdir()
    (lessons / "rem-orphan-no-av.yaml").write_text(
        _ORPHAN_NO_API_VERSION_DOC, encoding="utf-8", newline="",
    )
    report = mig.migrate([tmp_path], apply=True)
    assert report.already_new == []
    assert len(report.orphans) == 1
    assert len(report.errors) == 1


def test_orphan_report_summary_surfaces_the_error():
    report = mig.MigrationReport(
        scanned=1, orphans=[pathlib.Path("/x/rem-orphan.yaml")],
        errors=[(pathlib.Path("/x/rem-orphan.yaml"), "kind: Engram but apiVersion is not ...")],
    )
    text = report.summary(applied=True)
    assert "ORPHAN" in text
    assert "rem-orphan.yaml" in text


# ---------------------------------------------------------------------------
# FIX 3 — atomic writes
# ---------------------------------------------------------------------------


def test_apply_leaves_no_leftover_temp_files(tmp_path):
    root = _seed(tmp_path)
    mig.migrate([root], apply=True)
    leftovers = list((root / "lessons-learned").glob("*.tmp"))
    assert leftovers == [], f"atomic write must clean up its temp file, found {leftovers}"


def test_write_failure_never_leaves_a_partial_target(tmp_path, monkeypatch):
    """Simulate a crash mid-write (the OOM/eviction scenario the atomic
    write guards against): os.replace never runs, so the ORIGINAL file must
    still be intact — never truncated, never half-old-half-new."""
    root = _seed(tmp_path)
    target = root / "lessons-learned" / "rem-abc123.yaml"

    real_fdopen = mig.os.fdopen

    def _boom(fd, *a, **kw):
        f = real_fdopen(fd, *a, **kw)
        f.write("PARTIAL")
        f.flush()
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(mig.os, "fdopen", _boom)

    report = mig.migrate([root], apply=True)
    assert report.migrated == []
    assert len(report.errors) == 1

    # The target file is UNTOUCHED — still the original content, not
    # truncated, not partially rewritten.
    assert _read_raw(target) == _OLD_DOC
    # And the doomed temp file was cleaned up, not left behind.
    leftovers = list((root / "lessons-learned").glob(".*.tmp"))
    assert leftovers == [], f"a failed write must not leak its temp file, found {leftovers}"


# ---------------------------------------------------------------------------
# FIX 4 — newline convention preserved exactly (CRLF, and no-trailing-newline)
# ---------------------------------------------------------------------------


def test_no_trailing_newline_is_preserved(tmp_path):
    """apiVersion is the LAST line with NO trailing newline at all — the
    classic case a greedy `\\s*$` eats (`\\s` matches `\\n` too)."""
    doc_no_nl = _OLD_DOC.rstrip("\n")
    assert not doc_no_nl.endswith("\n")
    lessons = tmp_path / "lessons-learned"
    lessons.mkdir()
    path = lessons / "rem-no-nl.yaml"
    path.write_text(doc_no_nl, encoding="utf-8", newline="")

    report = mig.migrate([tmp_path], apply=True)
    assert len(report.migrated) == 1

    rewritten = _read_raw(path)
    assert not rewritten.endswith("\n"), "must not GAIN a trailing newline that wasn't there"
    assert rewritten == _NEW_DOC.rstrip("\n")


def test_crlf_line_endings_are_preserved(tmp_path):
    """A CRLF-terminated file must round-trip as CRLF throughout — not get
    silently normalized to LF (the default behavior of naive
    read_text()/write_text(), which use universal-newline translation)."""
    doc_crlf = _OLD_DOC.replace("\n", "\r\n")
    assert "\r\n" in doc_crlf
    lessons = tmp_path / "lessons-learned"
    lessons.mkdir()
    path = lessons / "rem-crlf.yaml"
    path.write_text(doc_crlf, encoding="utf-8", newline="")

    report = mig.migrate([tmp_path], apply=True)
    assert len(report.migrated) == 1

    rewritten = _read_raw(path)
    expected_crlf = _NEW_DOC.replace("\n", "\r\n")
    assert rewritten == expected_crlf
    # No bare, un-paired "\n" anywhere (every line ending is "\r\n").
    assert rewritten.replace("\r\n", "") .count("\n") == 0
