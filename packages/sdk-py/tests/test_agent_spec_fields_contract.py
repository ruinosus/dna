"""Contract test for the AGENT.md frontmatter passthrough.

The helix reader uses ``_SPEC_FIELDS`` (an allowlist) to decide which
top-level frontmatter keys flow into ``raw["spec"]``. Historically the
allowlist was hand-maintained and silently drifted from the
``AgentSpec`` dataclass, dropping new fields at parse time —
2026-05-08 hit this with ``shell_sandbox`` and (separately on the TS
twin) ``codegraph``/``tool_groups``/``tests``.

The reader now derives the allowlist from
``dataclasses.fields(AgentSpec)`` directly, so a new field
opens automatically. These tests pin that contract:

1. The derived set covers every dataclass field except ``instruction``.
2. ``instruction`` is intentionally excluded (it comes from the body
   or via ``instruction_file`` resolution, never from a top-level
   frontmatter key).
3. A round-trip on every field except ``instruction`` lands in
   ``raw["spec"]`` — adding a field to the dataclass without manual
   intervention is enough to make it author-able.
"""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

from dna.extensions.helix import _SPEC_FIELDS, AgentReader
from dna.kernel.bundle_handle import FilesystemBundleHandle
from dna.kernel.models import AgentSpec


def test_spec_fields_covers_dataclass_minus_instruction():
    expected = {
        f.name for f in dataclasses.fields(AgentSpec)
        if f.name != "instruction"
    }
    assert _SPEC_FIELDS == expected, (
        f"_SPEC_FIELDS drifted from AgentSpec dataclass. "
        f"Missing in allowlist: {expected - _SPEC_FIELDS}. "
        f"Extra in allowlist (not in dataclass): {_SPEC_FIELDS - expected}."
    )


def test_instruction_is_intentionally_excluded():
    """``instruction`` comes from AGENT.md body, never from a
    frontmatter top-level key. The reader fills it from the body
    (or via ``instruction_file`` indirection). Allowing it in the
    passthrough would let an authoring mistake silently shadow the
    body."""
    assert "instruction" not in _SPEC_FIELDS


def _build_agent_md(frontmatter: dict) -> str:
    import yaml
    return f"---\n{yaml.dump(frontmatter, sort_keys=False)}---\nbody text\n"


def test_every_passthrough_field_round_trips():
    """For each field in the allowlist, write a frontmatter that
    declares it and confirm the AgentReader puts it in ``spec``."""
    reader = AgentReader()
    # Sample values per type — kept small but type-correct so the
    # YAML dumper produces well-formed input.
    samples: dict[str, object] = {
        "instruction_file": None,  # mutual exclusion with body — covered separately
        "objective": "demo",
        "model": "openai:gpt-4o-mini",
        "type": "agent",
        "soul": "demo-soul",
        "skills": ["s1"],
        "tools": ["t1"],
        "team_members": ["sub-1"],
        "tags": ["demo"],
        "guardrails": ["g1"],
        "promptTemplate": "Hello {{name}}",
        "tool_groups": ["manifest"],
        # s-mcp-servers-on-agent — string shorthand + per-agent override.
        "mcp_servers": [
            "drawio",
            {"ref": "web-search", "allowed_tools": ["search"], "timeout_s": 20},
        ],
        "shell_sandbox": True,
        # Phase 14w / 15.x follow-ups + s-ua-agent-contract-fields.
        "prompt_format": "json",
        "max_turns": 25,
        "agent_kind": "deepagent",
        "mandatory_tool_calls": ["create_status_report"],
        "input_schema": {"type": "object", "properties": {"x": {"type": "string"}}},
        "invoked_by_engine": "oracle-risk-insight",
        "reflect_before_write": True,
        "locale_strings": {"en": {"greeting": "Hello"}, "pt": {"greeting": "Olá"}},
        "target_scopes": ["hr-screening", "open-swe"],
        # Kind-Writer mode (feat/kind-writer-pilot).
        "writes_kind": "StatusReport",
        "creative_slots": ["verdict"],
        "system_slots": {"insight": "input.oracle_id"},
        # Multi-Kind mode (feat/kind-writer-multikind).
        "writes_kinds": {
            "ADR": {
                "creative_slots": ["title", "context", "decision"],
                "system_slots": {"status": "accepted"},
            },
            "Retrospective": {
                "creative_slots": ["title", "what_went_well"],
                "system_slots": {"period_start": "input.period_start"},
            },
        },
        # Declarative reads (feat/scribe-migrate-6).
        "reads": {"oracle_verdicts": {"n": 3}, "engrams": {"n": 5}},
        # Declarative rubric (deepagents RubricMiddleware).
        "rubric": "- the output is valid JSON\n- a doc was created",
        "rubric_max_iterations": 3,
        # Declarative delegation-target opt-in (s-delegation-declarative).
        "delegation_target_for": {
            "agents": ["jarvis"],
            "format": "slug",
            "typical_seconds": 10,
            "use_when": "user asks for an elaborate HTML mockup",
            "purpose": "Generate elaborate HTML mockups",
        },
        # JARVIS — voice-first opt-in block (s-jarvis-voice-persona-schema).
        "voice_persona": {
            "voice": "cedar",
            "style": "concise, dry-wit",
            "archetype": "jarvis",
            "interruption_tolerance": "high",
            "preamble": True,
            "mcp_egress": True,
            "wake_word": "hey jefferson",
            "budget": 5.0,
        },
    }
    # Allowlist must be a strict subset of samples we know how to test.
    untested = _SPEC_FIELDS - samples.keys()
    assert not untested, (
        f"New field(s) added to AgentSpec but the round-trip "
        f"test doesn't have sample values for: {untested}. Add a value "
        f"to the ``samples`` dict above."
    )

    for field_name in _SPEC_FIELDS:
        if field_name == "instruction_file":
            continue  # body is mutually exclusive — covered by other tests
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "AGENT.md").write_text(_build_agent_md({
                "name": "smoke-agent",
                "description": "round-trip test",
                field_name: samples[field_name],
            }))
            handle = FilesystemBundleHandle(d)
            raw = reader.read(handle)
            assert field_name in raw["spec"], (
                f"field {field_name!r} declared in AGENT.md frontmatter "
                f"did not land in raw['spec'] — passthrough is broken"
            )
            assert raw["spec"][field_name] == samples[field_name], (
                f"field {field_name!r} value mutated during read: "
                f"got {raw['spec'][field_name]!r}, expected {samples[field_name]!r}"
            )
