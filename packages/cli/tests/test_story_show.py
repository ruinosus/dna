"""Tests for `dna sdlc story show` (i-070).

The command reads a Story via the API client (source-agnostic — no local
Postgres / direct DB), and renders header + description + AC + DoD + timeline,
with --json. Before this, agents fell back to raw YAML or SQL to read a Story.
"""
from contextlib import contextmanager

from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli import sdlc_cmd


class _Doc:
    def __init__(self, name, spec):
        self.name = name
        self.spec = spec


_SPEC = {
    "title": "Pin gpt-realtime-2",
    "status": "todo",
    "priority": "medium",
    "feature": "f-jarvis-realtime2-adoption",
    "reporter": "claude-code",
    "description": "Confirm /voice/sessions doesn't override the default model.",
    "acceptance_criteria": ["model is verifiably gpt-realtime-2"],
    "definition_of_done": [
        {"text": "regression test on the SDP URL", "done": False},
        {"text": "docs note", "done": True},
    ],
    "plan_ref": "Plan/plan-s-x",
    "timeline": [{"at": "2026-05-29T08:02:48Z", "type": "status_change", "summary": "created"}],
}


def _run(found=True, *args):
    class _FakeSession:
        scope = "dna-development"

        def get_doc(self, kind, name, *, tenant=None):
            return _Doc(name, dict(_SPEC)) if found else None

    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession()

    return CliRunner().invoke(
        sdlc_cmd.sdlc, ["story", "show", "s-x", *args],
        obj={SESSION_PROVIDER_KEY: _fake},
    )


def test_show_renders_header_ac_dod():
    r = _run(True)
    assert r.exit_code == 0, r.output
    assert "Story: s-x" in r.output
    assert "Pin gpt-realtime-2" in r.output
    assert "status: todo" in r.output and "priority: medium" in r.output
    assert "f-jarvis-realtime2-adoption" in r.output
    # AC + DoD both rendered, DoD checkboxes reflect done flags.
    assert "model is verifiably gpt-realtime-2" in r.output
    assert "[ ] regression test on the SDP URL" in r.output
    assert "[x] docs note" in r.output
    assert "Plan/plan-s-x" in r.output


def test_show_json():
    import json
    r = _run(True, "--json")
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["status"] == "todo"
    assert data["feature"] == "f-jarvis-realtime2-adoption"


def test_show_not_found_errors():
    r = _run(False)
    assert r.exit_code != 0
    assert "not found" in r.output.lower()
