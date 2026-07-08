"""Tests for GuardrailExtension — registration, kind properties, generic reader/writer."""
from __future__ import annotations

import pytest
from pathlib import Path

from dna.kernel import Kernel
from dna.kernel.generic_rw import GenericBundleReader, GenericBundleWriter
from dna.kernel.bundle_handle import FilesystemBundleHandle
from dna.extensions.guardrails import GuardrailKind


# ---------------------------------------------------------------------------
# TestGuardrailRegistration
# ---------------------------------------------------------------------------

class TestGuardrailRegistration:
    def test_registers_kind_only(self):
        """GuardrailExtension now registers only a kind; reader/writer are auto-generated."""
        k = Kernel()
        from dna.extensions.guardrails import GuardrailExtension
        k.load(GuardrailExtension())
        assert ("github.com/ruinosus/dna/v1", "Guardrail") in k._kinds
        # No custom readers/writers — the generic machinery handles them
        assert len(k._readers) == 0
        assert len(k._writers) == 0

    def test_kind_properties(self):
        k = Kernel()
        from dna.extensions.guardrails import GuardrailExtension
        k.load(GuardrailExtension())
        kp = k._kinds[("github.com/ruinosus/dna/v1", "Guardrail")]
        assert kp.is_root is False
        assert kp.is_prompt_target is False
        assert kp.flatten_in_context is False
        assert kp.alias == "guardrails-guardrail"
        assert kp.origin == "github.com/ruinosus/dna/guardrails"
        assert kp.dep_filters() is None
        assert kp.prompt_target_priority == 0

    def test_parse_returns_typed(self):
        from dna.kernel.models import TypedGuardrail
        kp = GuardrailKind()
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Guardrail",
            "metadata": {"name": "no-pii"},
            "spec": {"rules": ["No PII allowed"], "severity": "error", "scope": "output"},
        }
        typed = kp.parse(raw)
        assert isinstance(typed, TypedGuardrail)
        assert typed.metadata.name == "no-pii"
        assert typed.spec.rules == ["No PII allowed"]
        assert typed.spec.severity == "error"
        assert typed.spec.scope == "output"

    def test_parse_defaults(self):
        kp = GuardrailKind()
        raw = {
            "apiVersion": "github.com/ruinosus/dna/v1",
            "kind": "Guardrail",
            "metadata": {"name": "empty"},
            "spec": {},
        }
        typed = kp.parse(raw)
        assert typed.spec.rules == []
        assert typed.spec.severity == "warn"
        assert typed.spec.scope == "both"

    def test_describe_returns_none(self):
        kp = GuardrailKind()
        assert kp.describe(None) is None

    def test_summary_returns_severity_scope_rules(self):
        from dataclasses import dataclass

        @dataclass
        class FakeDoc:
            kind: str = "Guardrail"
            name: str = "no-pii"
            spec: dict = None  # type: ignore
            def __post_init__(self):
                if self.spec is None:
                    self.spec = {"severity": "hard", "scope": "both", "rules": ["a", "b"]}

        kp = GuardrailKind()
        result = kp.summary(FakeDoc())
        assert result is not None
        assert result["severity"] == "hard"
        assert result["scope"] == "both"
        assert result["rules"] == 2

    def test_prompt_template_returns_none(self):
        kp = GuardrailKind()
        assert kp.prompt_template() is None


# ---------------------------------------------------------------------------
# TestGuardrailGenericReader  (replaces TestGuardrailReader)
# ---------------------------------------------------------------------------

def _make_reader() -> GenericBundleReader:
    return GenericBundleReader(GuardrailKind.storage, GuardrailKind.api_version, GuardrailKind.kind)


def _make_writer() -> GenericBundleWriter:
    return GenericBundleWriter(GuardrailKind.storage, GuardrailKind.kind)


class TestGuardrailGenericReader:
    def test_detect_no_file(self, tmp_path):
        r = _make_reader()
        assert r.detect(FilesystemBundleHandle(tmp_path)) is False

    def test_detect_with_file(self, tmp_path):
        r = _make_reader()
        (tmp_path / "GUARDRAIL.md").write_text("---\nname: test\n---\n- Rule one")
        assert r.detect(FilesystemBundleHandle(tmp_path)) is True

    def test_reads_frontmatter_and_rules(self, tmp_path):
        r = _make_reader()
        content = (
            "---\n"
            "name: no-pii\n"
            'description: "Prevent PII leakage"\n'
            "severity: error\n"
            "scope: output\n"
            "---\n\n"
            "- No names in responses\n"
            "- No email addresses\n"
        )
        (tmp_path / "GUARDRAIL.md").write_text(content)
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert result["apiVersion"] == "github.com/ruinosus/dna/v1"
        assert result["kind"] == "Guardrail"
        assert result["metadata"]["name"] == "no-pii"
        assert result["metadata"]["description"] == "Prevent PII leakage"
        assert result["spec"]["severity"] == "error"
        assert result["spec"]["scope"] == "output"
        assert result["spec"]["rules"] == ["No names in responses", "No email addresses"]

    def test_reads_defaults_when_missing(self, tmp_path):
        r = _make_reader()
        (tmp_path / "GUARDRAIL.md").write_text("---\nname: basic\n---\n- Keep it clean\n")
        result = r.read(FilesystemBundleHandle(tmp_path))
        # Defaults are applied by GuardrailKind.parse(), not the reader
        assert result["spec"]["rules"] == ["Keep it clean"]

    def test_reads_name_from_dirname_fallback(self, tmp_path):
        r = _make_reader()
        # No name in frontmatter — falls back to directory name
        (tmp_path / "GUARDRAIL.md").write_text("---\n---\n- A rule\n")
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert result["metadata"]["name"] == tmp_path.name

    def test_ignores_non_list_lines(self, tmp_path):
        r = _make_reader()
        content = (
            "---\nname: mixed\n---\n\n"
            "# Rules\n\n"
            "- Valid rule\n"
            "Not a list item\n"
            "  indented line\n"
            "- Another valid rule\n"
        )
        (tmp_path / "GUARDRAIL.md").write_text(content)
        result = r.read(FilesystemBundleHandle(tmp_path))
        assert result["spec"]["rules"] == ["Valid rule", "Another valid rule"]


# ---------------------------------------------------------------------------
# TestGuardrailGenericWriter  (replaces TestGuardrailWriter)
# ---------------------------------------------------------------------------

class TestGuardrailGenericWriter:
    def test_can_write_guardrail(self):
        w = _make_writer()
        assert w.can_write({"kind": "Guardrail"}) is True
        assert w.can_write({"kind": "Skill"}) is False
        assert w.can_write({}) is False

    def test_roundtrip(self, tmp_path):
        r = _make_reader()
        w = _make_writer()

        raw = {
            "kind": "Guardrail",
            "metadata": {"name": "no-pii", "description": "Prevent PII leakage"},
            "spec": {
                "rules": ["No names in responses", "No email addresses"],
                "severity": "error",
                "scope": "output",
            },
        }
        assert w.can_write(raw) is True
        out = tmp_path / "no-pii"
        w.write(FilesystemBundleHandle(out), raw)

        assert (out / "GUARDRAIL.md").exists()
        result = r.read(FilesystemBundleHandle(out))
        assert result["metadata"]["name"] == "no-pii"
        assert result["spec"]["rules"] == ["No names in responses", "No email addresses"]
        assert result["spec"]["severity"] == "error"
        assert result["spec"]["scope"] == "output"

    def test_roundtrip_defaults(self, tmp_path):
        r = _make_reader()
        w = _make_writer()

        raw = {
            "kind": "Guardrail",
            "metadata": {"name": "basic"},
            "spec": {
                "rules": ["Keep it clean"],
                "severity": "warn",
                "scope": "both",
            },
        }
        out = tmp_path / "basic"
        w.write(FilesystemBundleHandle(out), raw)

        result = r.read(FilesystemBundleHandle(out))
        assert result["spec"]["rules"] == ["Keep it clean"]
        # severity/scope are spec fields — they should roundtrip correctly
        assert result["spec"]["severity"] == "warn"
        assert result["spec"]["scope"] == "both"
