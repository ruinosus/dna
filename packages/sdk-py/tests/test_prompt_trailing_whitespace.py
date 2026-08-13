"""i-013 — trailing newline in bundle bodies must not leak into prompts.

Pilot phase-2 finding: a SOUL.md saved with a trailing newline (every
editor re-adds one) leaked ``\\n\\n\\n`` into the composed prompt — the
body's own trailing newline stacked on the template's ``\\n\\n`` joiner.
The pilot worked around it by stripping the file's final newline, which
is fragile.

Contract locked here:

- Composition (prompt build) normalizes trailing whitespace of the
  flattened bodies (``soul_content``, ``agents_content``, ...) and of
  ``agent.instruction`` (the AGENT.md body).
- Storage stays byte-faithful: the strip lives ONLY at the composition
  boundary — the raw doc read back from the kernel keeps the trailing
  newline (the rw conformance kit enforces byte-fidelity on WRITE).

Sweep (issue asks): LESSON.md is not a prompt target and not flattened
(``is_prompt_target=False``, ``flatten_in_context=False``) — it has no
composition vector, so no leak is possible there.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna.kernel import Kernel


AGENT_BODY = "# Pilot agent\n\nDo the pilot things.\n"
SOUL_BODY = "## Personality\n\nCalm, precise, direct.\n"


def _mk_scope(tmp_path: Path, scope: str = "pilot-scope") -> Path:
    """Minimal scope: Genome + one AGENT.md + one SOUL.md, every body
    ending in a trailing newline (the editor-default that leaked)."""
    root = tmp_path / scope
    (root / "agents" / "pilot-agent").mkdir(parents=True)
    (root / "souls" / "pilot-soul").mkdir(parents=True)
    (root / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n"
        f"  name: {scope}\n"
        "spec:\n"
        "  default_agent: pilot-agent\n",
        encoding="utf-8",
    )
    (root / "agents" / "pilot-agent" / "AGENT.md").write_text(
        "---\nname: pilot-agent\ndescription: pilot agent\n---\n" + AGENT_BODY,
        encoding="utf-8",
    )
    (root / "souls" / "pilot-soul" / "SOUL.md").write_text(
        "---\nname: pilot-soul\n---\n" + SOUL_BODY,
        encoding="utf-8",
    )
    return root


@pytest.fixture
def mi(tmp_path):
    _mk_scope(tmp_path)
    m = Kernel.quick("pilot-scope", base_dir=str(tmp_path))
    _ = m.instances  # materialize on the sync path (async tests reuse the cache)
    return m


class TestTrailingNewlineLeak:
    def test_soul_trailing_newline_does_not_leak(self, mi):
        prompt = mi.build_prompt(agent="pilot-agent")
        assert "Calm, precise, direct." in prompt  # soul flattened in
        assert "\n\n\n" not in prompt, (
            "trailing newline from SOUL.md/AGENT.md leaked into the "
            f"composed prompt: {prompt!r}"
        )

    def test_agent_instruction_trailing_newline_normalized(self, mi):
        ctx = mi._build_context(mi._find_agent("pilot-agent"), None)
        assert ctx["agent"]["instruction"] == AGENT_BODY.rstrip()

    def test_soul_content_flatten_normalized(self, mi):
        ctx = mi._build_context(mi._find_agent("pilot-agent"), None)
        assert ctx["soul_content"] == SOUL_BODY.rstrip()

    @pytest.mark.asyncio
    async def test_async_context_matches_sync(self, mi):
        agent = mi._find_agent("pilot-agent")
        ctx = await mi.prompt._build_context_async(agent, None)
        assert ctx["agent"]["instruction"] == AGENT_BODY.rstrip()
        assert ctx["soul_content"] == SOUL_BODY.rstrip()

    def test_storage_byte_fidelity_untouched(self, mi):
        """The strip is composition-only: the raw doc read from the
        kernel keeps the trailing newline exactly as stored on disk."""
        doc = next(d for d in mi.instances if d.kind == "Soul")
        assert doc.spec["soul_content"] == SOUL_BODY  # trailing \n intact


class TestAsyncBuildPath:
    """Same contract on the ASYNC build path.

    ⚠️ This class used to be ``TestPromptKernelLazyPath`` and drove
    ``prompt/engine.py`` through a hand-built ``SimpleNamespace`` fake
    kernel. That module had zero production callers and was deleted in
    s-dna-shrink-faixa-1, so the class proved the contract on a path
    nobody ran — and, worse, the fake supplied its OWN
    ``prompt_template``, so even the template cascade under test was the
    test's, not the kernel's. It now drives the live
    ``PromptBuilder.build_async`` over the same real fixture scope the
    sync class uses, which is what makes the two comparable at all.
    """

    @pytest.mark.asyncio
    async def test_async_build_prompt_no_leak(self, mi):
        prompt = await mi.build_prompt_async(agent="pilot-agent")
        assert "Calm, precise, direct." in prompt
        assert "\n\n\n" not in prompt, repr(prompt)

    @pytest.mark.asyncio
    async def test_async_build_is_byte_identical_to_sync(self, mi):
        """The two paths differ only in how they await refs — never in
        what they compose. A divergence here is the defect that a dead
        divergent twin (i-048) hid for months."""
        assert await mi.build_prompt_async(agent="pilot-agent") == mi.build_prompt(
            agent="pilot-agent"
        )
