"""s-engram-rename — the ``scripts/migrate_lesson_learned_to_engram.py`` data
migration.

Kind resolution is an exact ``(apiVersion, kind)`` lookup with no fallback
(``kernel/instance.py:686``) — a stored ``LessonLearned`` doc is invisible to
the renamed ``Engram`` KindPort the instant the SDK pin advances, hence the
one-time rewrite. These tests drive the script's importable functions
directly against a scratch directory tree (never touching real ``.dna/``
data) and pin: dry-run reports without writing, ``--apply`` rewrites ONLY the
two envelope fields byte-for-byte elsewhere, cross-reference strings deeper
in the doc are left alone, and re-running is idempotent (no double-rewrite,
no drift).

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
    (lessons / "rem-abc123.yaml").write_text(_OLD_DOC, encoding="utf-8")
    (lessons / "unrelated.yaml").write_text(_UNRELATED_DOC, encoding="utf-8")
    return tmp_path


def test_dry_run_reports_without_writing(tmp_path):
    root = _seed(tmp_path)
    report = mig.migrate([root], apply=False)
    assert report.scanned == 2
    assert len(report.found_old) == 1
    assert report.found_old[0].name == "rem-abc123.yaml"
    assert report.already_new == []
    assert report.migrated == []
    # Nothing written — the file is untouched.
    assert (root / "lessons-learned" / "rem-abc123.yaml").read_text() == _OLD_DOC


def test_apply_rewrites_only_the_two_envelope_fields(tmp_path):
    root = _seed(tmp_path)
    report = mig.migrate([root], apply=True)
    assert len(report.migrated) == 1

    rewritten = (root / "lessons-learned" / "rem-abc123.yaml").read_text()
    assert rewritten.splitlines()[0] == "kind: Engram"
    assert "apiVersion: github.com/ruinosus/dna/v1" in rewritten
    # Everything else byte-for-byte identical, including the cross-reference
    # string deeper in the doc (a ref into ANOTHER doc — deliberately not
    # rewritten by this script; see the module docstring).
    assert "source_refs:\n  - LessonLearned/rem-other\n" in rewritten
    assert "name: rem-abc123" in rewritten
    assert "summary: A test memory." in rewritten

    # The unrelated Story doc is untouched.
    unrelated = (root / "lessons-learned" / "unrelated.yaml").read_text()
    assert unrelated == _UNRELATED_DOC


def test_apply_is_idempotent(tmp_path):
    root = _seed(tmp_path)
    first = mig.migrate([root], apply=True)
    assert len(first.migrated) == 1
    after_first = (root / "lessons-learned" / "rem-abc123.yaml").read_text()

    second = mig.migrate([root], apply=True)
    assert second.found_old == []
    assert second.migrated == []
    assert len(second.already_new) == 1

    after_second = (root / "lessons-learned" / "rem-abc123.yaml").read_text()
    assert after_second == after_first, "re-running must not touch an already-migrated doc"


def test_no_lesson_learned_docs_is_a_clean_zero_report(tmp_path):
    (tmp_path / "unrelated.yaml").write_text(_UNRELATED_DOC, encoding="utf-8")
    report = mig.migrate([tmp_path], apply=True)
    assert report.scanned == 1
    assert report.found_old == []
    assert report.migrated == []
    assert report.errors == []


def test_missing_root_is_reported_as_an_error_not_a_crash(tmp_path):
    missing = tmp_path / "does-not-exist"
    report = mig.migrate([missing], apply=False)
    assert report.scanned == 0
    assert len(report.errors) == 1
    assert report.errors[0][0] == missing
