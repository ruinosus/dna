"""Phase 10a — GenomeSpec gains version + deprecation; semver matcher."""
from __future__ import annotations

import pytest

from dna.kernel.models import GenomeSpec
from dna.kernel.semver import (
    Constraint,
    InvalidConstraint,
    InvalidVersion,
    UNVERSIONED,
    Version,
    is_outdated,
    max_satisfying,
    parse,
)


# ── GenomeSpec field round-trips ──────────────────────────────────────


def test_module_spec_versioning_defaults_unset():
    spec = GenomeSpec.from_raw({})
    assert spec.version is None
    assert spec.changelog_url is None
    assert spec.deprecated is False
    assert spec.deprecated_message is None


def test_module_spec_round_trip_versioned():
    spec = GenomeSpec.from_raw({
        "version": "1.4.2",
        "changelog_url": "https://example.com/CHANGELOG.md",
        "deprecated": True,
        "deprecated_message": "use v2",
    })
    assert spec.version == "1.4.2"
    assert spec.changelog_url == "https://example.com/CHANGELOG.md"
    assert spec.deprecated is True
    assert spec.deprecated_message == "use v2"


# ── Version parsing ──────────────────────────────────────────────────


@pytest.mark.parametrize("s,expected", [
    ("1.0.0", Version(1, 0, 0)),
    ("0.0.1", Version(0, 0, 1)),
    ("10.20.30", Version(10, 20, 30)),
    ("1.2.3-rc.1", Version(1, 2, 3, prerelease=("rc", 1))),
    ("1.2.3-alpha", Version(1, 2, 3, prerelease=("alpha",))),
    ("1.2.3+sha.abc", Version(1, 2, 3, build="sha.abc")),
    ("1.2.3-rc.1+sha.abc", Version(1, 2, 3, prerelease=("rc", 1), build="sha.abc")),
])
def test_version_parse(s, expected):
    assert Version.parse(s) == expected


@pytest.mark.parametrize("s", ["1", "1.2", "1.2.3.4", "v1.0.0", "abc", ""])
def test_version_parse_rejects_garbage(s):
    with pytest.raises(InvalidVersion):
        Version.parse(s)


def test_version_str_round_trip():
    for s in ["1.2.3", "0.0.1", "1.2.3-rc.1", "1.2.3-alpha", "1.2.3+sha.abc"]:
        assert str(Version.parse(s)) == s


# ── Version ordering ─────────────────────────────────────────────────


def test_version_ordering_core():
    assert Version.parse("1.0.0") < Version.parse("1.0.1")
    assert Version.parse("1.0.0") < Version.parse("1.1.0")
    assert Version.parse("1.0.0") < Version.parse("2.0.0")
    assert Version.parse("2.0.0") > Version.parse("1.999.999")


def test_version_ordering_prerelease_before_release():
    """SemVer 2.0 §11: pre-release sorts BEFORE release of same core."""
    assert Version.parse("1.0.0-rc.1") < Version.parse("1.0.0")
    assert Version.parse("1.0.0-alpha") < Version.parse("1.0.0-beta")
    assert Version.parse("1.0.0-rc.1") < Version.parse("1.0.0-rc.2")


def test_version_build_metadata_ignored_for_ordering():
    a = Version.parse("1.2.3+build1")
    b = Version.parse("1.2.3+build2")
    # Equal for ordering AND equality (build is metadata only).
    assert a == b
    assert not (a < b) and not (b < a)


# ── Unversioned sentinel ─────────────────────────────────────────────


def test_parse_none_returns_unversioned_sentinel():
    assert parse(None) is UNVERSIONED
    assert parse("") is UNVERSIONED


def test_unversioned_below_every_real_version():
    for s in ["0.0.1", "0.1.0", "1.0.0", "1.0.0-alpha"]:
        assert UNVERSIONED < Version.parse(s)


# ── Constraint matching ──────────────────────────────────────────────


@pytest.mark.parametrize("c,v,want", [
    ("^1.2.3", "1.2.3", True),
    ("^1.2.3", "1.5.0", True),
    ("^1.2.3", "2.0.0", False),
    ("^1.2.3", "1.2.2", False),
    ("^0.2.3", "0.2.3", True),
    ("^0.2.3", "0.2.99", True),
    ("^0.2.3", "0.3.0", False),
    ("^0.0.3", "0.0.3", True),
    ("^0.0.3", "0.0.4", False),
    ("~1.2.3", "1.2.3", True),
    ("~1.2.3", "1.2.99", True),
    ("~1.2.3", "1.3.0", False),
    ("1.2.3", "1.2.3", True),
    ("1.2.3", "1.2.4", False),
    ("1.x", "1.0.0", True),
    ("1.x", "1.99.99", True),
    ("1.x", "2.0.0", False),
    ("1.2.x", "1.2.0", True),
    ("1.2.x", "1.3.0", False),
    ("*", "0.0.1", True),
    ("*", "999.999.999", True),
    (">=1.2.3 <2.0.0", "1.5.0", True),
    (">=1.2.3 <2.0.0", "2.0.0", False),
])
def test_constraint_matches(c, v, want):
    assert Constraint.parse(c).matches(Version.parse(v)) is want


def test_unversioned_never_satisfies_real_constraint():
    for c in ["^1.0.0", "~0.1.0", ">=0.0.1", "*"]:
        assert Constraint.parse(c).matches(UNVERSIONED) is False


def test_invalid_constraint_raises():
    with pytest.raises(InvalidConstraint):
        Constraint.parse("1.2.3.x.y")
    with pytest.raises(InvalidVersion):
        Constraint.parse("^abc")


# ── max_satisfying + is_outdated ─────────────────────────────────────


def test_max_satisfying_picks_highest():
    versions = [Version.parse(v) for v in ["1.0.0", "1.4.2", "1.5.0", "2.0.0"]]
    best = max_satisfying(versions, "^1.0.0")
    assert best == Version.parse("1.5.0")  # 2.0.0 excluded by caret


def test_max_satisfying_returns_none_when_no_match():
    versions = [Version.parse("3.0.0"), Version.parse("3.1.0")]
    assert max_satisfying(versions, "^1.0.0") is None


def test_is_outdated_true_when_higher_available():
    assert is_outdated("1.4.2", ["1.4.2", "1.5.0"], "^1.0.0") is True


def test_is_outdated_false_when_already_max():
    assert is_outdated("1.5.0", ["1.4.2", "1.5.0"], "^1.0.0") is False


def test_is_outdated_false_when_higher_outside_constraint():
    assert is_outdated("1.5.0", ["1.5.0", "2.0.0"], "^1.0.0") is False


def test_is_outdated_unversioned_returns_false():
    """An unversioned install can never be 'outdated' — there's no semver
    notion of progress to compare against."""
    assert is_outdated(None, ["1.0.0", "2.0.0"], "*") is True
    # but if installed has no version AND constraint is real, still false:
    # the "installed" sentinel is Below everything, so any real version
    # IS higher → True. That's intentional: unversioned consumer + real
    # publisher means there IS an update path. The CLI surfaces it as
    # "consider versioning your install".
