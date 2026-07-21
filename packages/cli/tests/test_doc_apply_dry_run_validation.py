"""`dna doc apply --dry-run` must VALIDATE, not just report the verb.

i-validation-shallow (axis 2): the sp-exp-value-comparison spike found that a
schema-violating doc (e.g. a Guardrail ``severity: critical``) was ACCEPTED on
the read / ``--dry-run`` / compose paths — validation only fired on the real
write. ``--dry-run``'s help even says "Validate without writing". These tests
pin that a bad guardrail is now REJECTED (non-zero exit + didactic message) on
``--dry-run``, while a valid one passes — without ever touching the write path.

Offline: the session is stubbed with a REAL ``Kernel.auto()`` (so the live
GuardrailKind schema drives validation) but ``get_doc`` is stubbed and no write
is performed.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli.doc_cmd import doc


@pytest.fixture
def runner():
    return CliRunner()


def _guardrail_yaml(tmp_path, severity: str):
    content = (
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Guardrail\n"
        "metadata:\n"
        "  name: no-pii\n"
        "spec:\n"
        "  rules: ['No PII']\n"
        f"  severity: {severity}\n"
        "  scope: both\n"
    )
    f = tmp_path / "g.yaml"
    f.write_text(content, encoding="utf-8")
    return str(f)


def _stub_session():
    """Session with a REAL kernel (live GuardrailKind schema), stubbed get_doc."""
    from dna.kernel import Kernel

    kernel = Kernel.auto()
    mock_session = MagicMock()
    mock_session.kernel = kernel
    mock_session.scope = "demo"
    mock_session.get_doc.return_value = None  # CREATED path, no source read

    @contextmanager
    def _fake_dna_session(scope=None):
        yield mock_session

    return mock_session, {SESSION_PROVIDER_KEY: _fake_dna_session}


def test_dry_run_rejects_bad_severity(runner, tmp_path, monkeypatch):
    _mock, obj = _stub_session()
    path = _guardrail_yaml(tmp_path, "critical")
    result = runner.invoke(doc, ["apply", path, "--dry-run"], obj=obj)
    assert result.exit_code != 0, (
        f"--dry-run must reject an enum-violating severity. Output:\n{result.output}"
    )
    assert "critical" in result.output
    assert "severity" in result.output


def test_dry_run_rejects_garbage_severity(runner, tmp_path, monkeypatch):
    _mock, obj = _stub_session()
    path = _guardrail_yaml(tmp_path, "garbage")
    result = runner.invoke(doc, ["apply", path, "--dry-run"], obj=obj)
    assert result.exit_code != 0, result.output


def test_dry_run_accepts_valid_severity(runner, tmp_path, monkeypatch):
    _mock, obj = _stub_session()
    path = _guardrail_yaml(tmp_path, "hard")
    result = runner.invoke(doc, ["apply", path, "--dry-run"], obj=obj)
    assert result.exit_code == 0, (
        f"--dry-run must accept a documented severity. Output:\n{result.output}"
    )
    assert '"dry_run": true' in result.output
