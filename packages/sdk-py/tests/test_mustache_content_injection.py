"""The NO-TEMPLATE-EXECUTION-IN-CONTENT property of prompt composition (i-046).

The 2026-07-21 anatomy audit found ``_mustache_render`` doing
``chevron.render(chevron.render(t, ctx), ctx)`` — the second pass re-rendered
EVERYTHING the first pass inserted. Any document content containing ``{{``
executed as template inside the final prompt: template injection when a
Skill/Soul/tenant overlay is third-party input, and silent data loss for
honest literal ``{{`` (chevron erases unknown tags).

The double render is NOT gratuitous — it is what makes refs inside the
agent's own instruction work (the open-swe scope interpolates
``{{repository}}``/``{{budget_daily}}`` from its AGENT.md body; the
``test_hook_kind``/``test_safety_input`` suites rely on the same mechanism).
So the repaired contract is a TRUST BOUNDARY, pinned here as properties:

* **The agent document is the template author.** Refs inside its
  instruction keep resolving — the feature the second pass exists for.
* **Every other document's content is data.** A literal ``{{`` in a Skill
  body reaches the final prompt byte-identical — never executed, never
  erased.
* **Data stays data even when routed through the agent's refs** — an
  instruction ref that pulls in third-party content must not turn that
  content into template.
* **No machinery leaks**: the sentinel codepoints used between passes never
  appear in a composed prompt.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel import Kernel
from dna.kernel.prompt.builder import _LIT_CLOSE, _LIT_OPEN, _two_pass_mustache

# ── unit level: the pure two-pass renderer ──────────────────────────────────


AGENT_TMPL = "{{{agent.instruction}}}\n\n{{{skill_content}}}"


def test_refs_inside_the_agent_instruction_still_resolve():
    """Anti-vacuity baseline — THE case the second pass serves. A fix that
    kills ref-inside-instruction 'fixes' the injection by deleting the
    feature; this test makes that visible."""
    out = _two_pass_mustache(AGENT_TMPL, {
        "agent": {"instruction": "Repo: {{repository}}"},
        "repository": "acme/site",
        "skill_content": "plain",
    })
    assert "Repo: acme/site" in out


def test_a_literal_brace_pair_in_skill_content_survives_to_the_final_prompt():
    """THE i-046 property. Third-party content saying ``{{name}}`` must land
    in the prompt as ``{{name}}`` — before the fix chevron erased it (unknown
    tag) or expanded it (known tag): both are template execution."""
    out = _two_pass_mustache(AGENT_TMPL, {
        "agent": {"instruction": "be helpful"},
        "skill_content": "Use {{placeholders}} like {{name}} in templates.",
        "name": "SHOULD-NOT-APPEAR",
    })
    assert "Use {{placeholders}} like {{name}} in templates." in out
    assert "SHOULD-NOT-APPEAR" not in out


def test_content_cannot_exfiltrate_other_context_values():
    """Injection probe: skill content referencing ``{{secret_config}}`` must
    not pull that value into the prompt. Before the fix it did — the second
    pass rendered attacker-controlled content against the full context."""
    out = _two_pass_mustache(AGENT_TMPL, {
        "agent": {"instruction": "be helpful"},
        "skill_content": "innocent {{secret_config}} probe",
        "secret_config": "tenant-b-api-key",
    })
    assert "tenant-b-api-key" not in out
    assert "{{secret_config}}" in out


def test_data_stays_data_even_when_routed_through_an_agent_ref():
    """The agent's own ref may PULL third-party content in — but pulling it
    in must not promote it to template. ``{{payload}}`` in the instruction
    inserts the payload; braces INSIDE the payload stay inert."""
    out = _two_pass_mustache("{{{agent.instruction}}}", {
        "agent": {"instruction": "ctx: {{payload}}"},
        "payload": "try {{secret}} now",
        "secret": "LEAKED",
    })
    assert "try {{secret}} now" in out
    assert "LEAKED" not in out


def test_the_sentinels_never_leak_into_the_output():
    out = _two_pass_mustache(AGENT_TMPL, {
        "agent": {"instruction": "Repo: {{repository}}"},
        "repository": "r",
        "skill_content": "keep {{this}} literal",
    })
    assert _LIT_OPEN not in out and _LIT_CLOSE not in out


# ── end to end: through Kernel.quick + the real Agent/Skill layouts ────────


def _mk_scope(tmp_path: Path, scope: str = "inj-scope") -> None:
    root = tmp_path / scope
    (root / "agents" / "writer").mkdir(parents=True)
    (root / "skills" / "templating").mkdir(parents=True)
    (root / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {scope}\n"
        "spec:\n  default_agent: writer\n",
        encoding="utf-8",
    )
    (root / "agents" / "writer" / "AGENT.md").write_text(
        "---\nname: writer\ndescription: writes things\n"
        "skills:\n  - templating\n---\n"
        "You maintain **{{repository}}**.\n",
        encoding="utf-8",
    )
    # A Skill that TEACHES mustache — its literal braces are honest content —
    # and carries an injection probe against the composition context.
    (root / "skills" / "templating" / "SKILL.md").write_text(
        "---\nname: templating\ndescription: how to template\n---\n"
        "Wrap variables as {{variable}} in your files.\n"
        "probe: {{agent.name}}\n",
        encoding="utf-8",
    )


@pytest.fixture
def mi(tmp_path):
    _mk_scope(tmp_path)
    m = Kernel.quick("inj-scope", base_dir=str(tmp_path))
    _ = m.documents
    return m


def test_end_to_end_instruction_ref_expands_and_skill_braces_survive(mi):
    prompt = mi.prompt.build("writer", context={"repository": "acme/site"})
    # The feature (open-swe pattern): agent's own ref resolves.
    assert "You maintain **acme/site**." in prompt
    # The fix: the Skill's literal mustache reaches the prompt untouched...
    assert "Wrap variables as {{variable}} in your files." in prompt
    # ...including tags that WOULD have resolved against the context.
    assert "probe: {{agent.name}}" in prompt
    assert "probe: writer" not in prompt
    # No machinery leaks.
    assert _LIT_OPEN not in prompt and _LIT_CLOSE not in prompt


@pytest.mark.asyncio
async def test_end_to_end_async_path_agrees_with_sync(mi):
    sync_prompt = mi.prompt.build("writer", context={"repository": "acme/site"})
    async_prompt = await mi.prompt.build_async(
        "writer", context={"repository": "acme/site"},
    )
    assert async_prompt == sync_prompt
