"""Tests for evidence builder — SHA-256 hashing and document assembly."""
from dna.extensions.evidence.builder import compute_content_hash, build_evidence


# ─── compute_content_hash ────────────────────────────────────────────

class TestComputeContentHash:
    def test_deterministic(self):
        content = {"a": 1, "b": 2}
        h1 = compute_content_hash(content)
        h2 = compute_content_hash(content)
        assert h1 == h2

    def test_key_order_independence(self):
        """Logically identical dicts with different insertion order produce the same hash."""
        d1 = {"z": 1, "a": 2, "m": 3}
        d2 = {"a": 2, "m": 3, "z": 1}
        assert compute_content_hash(d1) == compute_content_hash(d2)

    def test_returns_hex_string(self):
        h = compute_content_hash({"x": 1})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 = 64 hex chars

    def test_different_content_different_hash(self):
        h1 = compute_content_hash({"a": 1})
        h2 = compute_content_hash({"a": 2})
        assert h1 != h2

    def test_handles_nested_objects(self):
        content = {"outer": {"inner": [1, 2, 3]}}
        h = compute_content_hash(content)
        assert isinstance(h, str) and len(h) == 64

    def test_handles_non_dict(self):
        """Should also work for lists, strings, etc."""
        h = compute_content_hash([1, 2, 3])
        assert isinstance(h, str) and len(h) == 64


# ─── build_evidence ──────────────────────────────────────────────────

class TestBuildEvidence:
    def test_produces_valid_structure(self):
        doc = build_evidence("eval_run_completed", "eval-evalrun/my-run", {"passed": 10})
        assert doc["api_version"] == "github.com/ruinosus/dna/evidence/v1"
        assert doc["kind"] == "Evidence"
        assert "metadata" in doc
        assert "spec" in doc

    def test_spec_has_required_fields(self):
        doc = build_evidence("document_created", "some-ref", {"key": "val"})
        spec = doc["spec"]
        assert spec["event_type"] == "document_created"
        assert isinstance(spec["sha256"], str) and len(spec["sha256"]) == 64
        assert "captured_at" in spec

    def test_default_author(self):
        doc = build_evidence("custom", "ref", {})
        assert doc["spec"]["author"] == "system"

    def test_custom_author(self):
        doc = build_evidence("custom", "ref", {}, author="alice")
        assert doc["spec"]["author"] == "alice"

    def test_notes_absent_when_none(self):
        doc = build_evidence("custom", "ref", {})
        assert "notes" not in doc["spec"]

    def test_notes_present_when_given(self):
        doc = build_evidence("custom", "ref", {}, notes="important")
        assert doc["spec"]["notes"] == "important"

    def test_snapshot_is_content_dict(self):
        content = {"foo": "bar"}
        doc = build_evidence("custom", "ref", content)
        assert doc["spec"]["snapshot"] == content

    def test_snapshot_wraps_non_dict(self):
        doc = build_evidence("custom", "ref", "hello")
        assert doc["spec"]["snapshot"] == {"value": "hello"}

    def test_metadata_name(self):
        doc = build_evidence("finding_created", "ref", {"x": 1})
        name = doc["metadata"]["name"]
        assert name.startswith("ev-finding_created-")
        # 12 hex chars of sha256
        suffix = name.split("-", 2)[-1]
        assert len(suffix) == 12

    def test_sha256_matches_content(self):
        content = {"important": "data"}
        doc = build_evidence("custom", "ref", content)
        assert doc["spec"]["sha256"] == compute_content_hash(content)
