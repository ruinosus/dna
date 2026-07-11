"""s-dx-named-layouts — author picks composition ORDER by name.

Before this story, ordering the Soul (persona) before the task instruction
meant hand-writing a raw ``promptTemplate`` full of internal section names
(``{{{soul_content}}}``, ``{{#guardrails-guardrail}}``). A named ``layout:``
field resolves to an embedded preset via the Kind — the common case never
authors Mustache.

Contract locked here:

- ``layout: persona-first`` puts the Soul before the instruction.
- ``layout: instruction-first`` / ``default`` (or absent) keeps the historic
  order — byte-identical to the pre-layouts kind default.
- A raw ``promptTemplate`` still WINS over ``layout`` (poweruser escape hatch).
- An unknown layout name fails LOUD (``UnknownLayout``) — never a silent
  fall-through to the default order.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna import UnknownLayout
from dna.kernel import Kernel

AGENT_BODY = "# Task\n\nDo the task."
SOUL_BODY = "## Persona\n\nCalm, precise, direct."


def _mk_scope(tmp_path: Path, *, layout: str | None, prompt_template: str | None = None,
              scope: str = "layout-scope") -> Path:
    root = tmp_path / scope
    (root / "agents" / "a1").mkdir(parents=True)
    (root / "souls" / "s1").mkdir(parents=True)
    (root / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n"
        f"  name: {scope}\n"
        "spec:\n"
        "  default_agent: a1\n",
        encoding="utf-8",
    )
    fm = ["name: a1", "description: demo", "soul: s1"]
    if layout is not None:
        fm.append(f"layout: {layout}")
    if prompt_template is not None:
        fm.append(f"promptTemplate: {prompt_template!r}")
    (root / "agents" / "a1" / "AGENT.md").write_text(
        "---\n" + "\n".join(fm) + "\n---\n" + AGENT_BODY,
        encoding="utf-8",
    )
    (root / "souls" / "s1" / "SOUL.md").write_text(
        "---\nname: s1\n---\n" + SOUL_BODY,
        encoding="utf-8",
    )
    return root


def _build(tmp_path, **kw) -> str:
    _mk_scope(tmp_path, **kw)
    mi = Kernel.quick("layout-scope", base_dir=str(tmp_path))
    _ = mi.documents
    return mi.build_prompt(agent="a1")


class TestNamedLayouts:
    def test_default_absent_is_instruction_first(self, tmp_path):
        prompt = _build(tmp_path, layout=None)
        # instruction body precedes the soul persona
        assert prompt.index("Do the task.") < prompt.index("Calm, precise, direct.")

    def test_instruction_first_matches_default(self, tmp_path):
        default = _build(tmp_path / "a", layout=None)
        explicit = _build(tmp_path / "b", layout="instruction-first")
        alias = _build(tmp_path / "c", layout="default")
        assert explicit == default == alias

    def test_persona_first_puts_soul_before_instruction(self, tmp_path):
        prompt = _build(tmp_path, layout="persona-first")
        assert "Calm, precise, direct." in prompt
        assert "Do the task." in prompt
        assert prompt.index("Calm, precise, direct.") < prompt.index("Do the task."), (
            "persona-first must render the Soul before the instruction"
        )

    def test_no_raw_mustache_authored(self, tmp_path):
        """The whole point: authoring persona-first needs NO Mustache — the
        AGENT.md carries only ``layout: persona-first``, never a template."""
        root = _mk_scope(tmp_path, layout="persona-first")
        agent_md = (root / "agents" / "a1" / "AGENT.md").read_text()
        assert "{{" not in agent_md and "promptTemplate" not in agent_md

    def test_raw_prompt_template_wins_over_layout(self, tmp_path):
        prompt = _build(
            tmp_path, layout="persona-first",
            prompt_template="RAW-ONLY {{agent.name}}",
        )
        assert prompt.strip() == "RAW-ONLY a1"

    def test_unknown_layout_fails_loud(self, tmp_path):
        with pytest.raises(UnknownLayout) as ei:
            _build(tmp_path, layout="persona_first")  # typo: underscore
        assert ei.value.layout == "persona_first"
        assert ei.value.agent == "a1"
        assert "persona-first" in ei.value.available


class TestKindLayoutSurface:
    def test_agent_kind_exposes_named_layouts(self):
        from dna.extensions.helix import AgentKind
        kp = AgentKind()
        assert set(kp.layout_names()) >= {"default", "instruction-first", "persona-first"}
        assert kp.layout_template("persona-first") is not None
        assert kp.layout_template("nope") is None

    def test_default_layout_is_the_kind_default_template(self):
        """``default`` layout string == kind default template — an agent with
        no layout composes exactly as before the feature existed."""
        from dna.extensions.helix import AgentKind
        kp = AgentKind()
        assert kp.layout_template("default") == kp.prompt_template()
        assert kp.layout_template("instruction-first") == kp.prompt_template()
