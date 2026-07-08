"""testkit extension — TestGuide + TestRun artifact Kinds (s-decompose-jarvis
follow-up: TESTS as dedicated kinds/extensions). Identity + schema + dogfood."""
from __future__ import annotations

import glob
from pathlib import Path

import pytest
import yaml

from dna.extensions.testkit import (
    TestGuideKind,
    TestRunKind,
    TestkitExtension,
)

_TEST_GUIDES_DIR = (
    Path(__file__).resolve().parents[3]
    / "scopes" / "dna-development" / ".dna" / "dna-development" / "test-guides"
)


def _guide_doc_paths() -> list[str]:
    return sorted(glob.glob(str(_TEST_GUIDES_DIR / "*.yaml")))


def test_testguide_kind_identity():
    k = TestGuideKind()
    assert k.kind == "TestGuide"
    assert k.alias == "testkit-test-guide"
    assert k.api_version == "github.com/ruinosus/dna/testkit/v1"
    assert k.storage.container == "test-guides"


def test_testrun_kind_identity():
    k = TestRunKind()
    assert k.kind == "TestRun"
    assert k.alias == "testkit-test-run"
    assert k.api_version == "github.com/ruinosus/dna/testkit/v1"
    assert k.storage.container == "test-runs"


def test_kind_of_test_enum_excludes_unit():
    enum = TestGuideKind().schema()["properties"]["kind_of_test"]["enum"]
    assert set(enum) == {"manual", "smoke", "e2e", "regression", "integration"}
    assert "unit" not in enum


def test_run_outcome_enum():
    enum = TestRunKind().schema()["properties"]["outcome"]["enum"]
    assert set(enum) == {"pass", "fail", "partial", "blocked"}


def test_testguide_requires_description_kind_steps():
    assert set(TestGuideKind().schema()["required"]) == {"description", "kind_of_test", "steps"}


def test_testrun_requires_guide_ref_outcome():
    assert set(TestRunKind().schema()["required"]) == {"guide_ref", "outcome"}


def test_extension_registers_both_kinds():
    aliases = [k.alias for k in TestkitExtension().kinds()]
    assert aliases == ["testkit-test-guide", "testkit-test-run"]


def test_kinds_are_global_and_inheritable_artifacts():
    for k in (TestGuideKind(), TestRunKind()):
        # GLOBAL (not tenant-scoped) but inheritable by DEFAULT — these are
        # artifacts (like HtmlArtifact/Research), NOT work-items, so they must
        # NOT land in the non-inheritable denylist (Story/Issue/Feature/...).
        assert k.scope.name == "GLOBAL"
        assert getattr(k, "scope_inheritable", True) is True


def test_summary_projects_key_fields():
    class _D:
        spec = {"kind_of_test": "smoke", "status": "active", "steps": [{"action": "a", "expected": "b"}],
                "verifies": ["Story/s-x"], "owner": "jefferson"}
    s = TestGuideKind().summary(_D())
    assert s == {"kind_of_test": "smoke", "status": "active", "steps_count": 1,
                 "verifies": ["Story/s-x"], "owner": "jefferson"}


@pytest.mark.parametrize("path", _guide_doc_paths())
def test_dogfood_guides_valid(path):
    import jsonschema
    doc = yaml.safe_load(open(path))
    jsonschema.validate(doc["spec"], TestGuideKind().schema())


# ── s-testkit-perstep-runresults: per-step screenshot, step.where, derive ─────
import jsonschema
from dna.extensions.testkit import (
    derive_overall_outcome,
    PRODUCT_TEST_KINDS,
)


def test_derive_overall_outcome_precedence():
    assert derive_overall_outcome([]) == "blocked"
    assert derive_overall_outcome(None) == "blocked"
    assert derive_overall_outcome([{"result": "pass"}, {"result": "pass"}]) == "pass"
    assert derive_overall_outcome([{"result": "pass"}, {"result": "fail"}]) == "fail"
    assert derive_overall_outcome([{"result": "pass"}, {"result": "skip"}]) == "partial"
    # fail dominates a skip
    assert derive_overall_outcome([{"result": "skip"}, {"result": "fail"}]) == "fail"


def test_product_test_kinds_are_human_lanes():
    assert PRODUCT_TEST_KINDS == frozenset({"manual", "smoke"})


def test_testguide_schema_accepts_step_where():
    schema = TestGuideKind().schema()
    spec = {
        "description": "d", "kind_of_test": "smoke",
        "steps": [{"action": "abra X", "expected": "vê Y", "where": "/scopes/:scope/sdlc/v2"}],
    }
    jsonschema.validate(spec, schema)  # must not raise


def test_testrun_schema_accepts_step_screenshot():
    schema = TestRunKind().schema()
    spec = {
        "guide_ref": "tg-x", "outcome": "pass",
        "step_results": [{"step_index": 0, "result": "pass", "notes": "ok", "screenshot": "data:image/png;base64,AAA"}],
    }
    jsonschema.validate(spec, schema)  # must not raise


# ── s-testrun-cli-screenshot: run-level Asset-backed screenshots[] ────────────
def test_testrun_schema_accepts_run_level_screenshots():
    """A TestRun raw WITH screenshots[] must pass validation. The schema is
    additionalProperties:false, so an undeclared field would FAIL — this guards
    that the property is actually declared."""
    schema = TestRunKind().schema()
    spec = {
        "guide_ref": "tg-x", "outcome": "pass",
        "screenshots": [
            {"asset": "ast-x-1234", "mime": "image/png", "blob": "blob.png"},
            {"asset": "ast-y-5678"},  # only `asset` is required
        ],
    }
    jsonschema.validate(spec, schema)  # must not raise


def test_testrun_schema_rejects_screenshot_without_asset():
    schema = TestRunKind().schema()
    spec = {
        "guide_ref": "tg-x", "outcome": "pass",
        "screenshots": [{"mime": "image/png", "blob": "blob.png"}],  # missing asset
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spec, schema)
