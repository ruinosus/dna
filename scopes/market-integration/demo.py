"""Market-fidelity demo (Python): the SDK reads REAL marketplace content
without modification.

- 17 skills from the Anthropic marketplace (agentskills.io)
- 14 skills from the Superpowers collection (agentskills.io)
- 1 soul (soulspec.org)
- 1 AGENTS.md (agents.md)

Run (from the repo root):

    cd packages/sdk-py && uv sync
    uv run python ../../scopes/market-integration/demo.py
"""
import sys
from pathlib import Path

# Fallback for running without an installed package (deps must be present).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk-py"))

from dna import Kernel

mi = Kernel.quick("market-demo", base_dir=str(Path(__file__).resolve().parent / ".dna"))

print("=" * 60)
print("MARKET INTEGRATION DEMO — REAL CONTENT")
print("=" * 60)

ANTHROPIC = {
    "algorithmic-art", "brand-guidelines", "canvas-design", "claude-api",
    "doc-coauthoring", "docx", "frontend-design", "internal-comms",
    "mcp-builder", "pdf", "pptx", "skill-creator", "slack-gif-creator",
    "theme-factory", "web-artifacts-builder", "webapp-testing", "xlsx",
}
SUPERPOWERS = {
    "brainstorming", "dispatching-parallel-agents", "executing-plans",
    "finishing-a-development-branch", "receiving-code-review",
    "requesting-code-review", "subagent-driven-development",
    "systematic-debugging", "test-driven-development", "using-git-worktrees",
    "using-superpowers", "verification-before-completion", "writing-plans",
    "writing-skills",
}

skills = [d for d in mi.documents if d.kind == "Skill"]
print(f"\nTotal Skills loaded: {len(skills)}")


def _sidecars(s) -> str:
    extras = []
    for label, field in (("refs", "references"), ("scripts", "scripts"), ("assets", "assets")):
        n = len(s.spec.get(field) or [])
        if n:
            extras.append(f"{n} {label}")
    return f" ({', '.join(extras)})" if extras else ""


for title, names in (("Anthropic (agentskills.io)", ANTHROPIC), ("Superpowers", SUPERPOWERS)):
    found = sorted((s for s in skills if s.name in names), key=lambda s: s.name)
    print(f"\n  {title}: {len(found)}/{len(names)}")
    for s in found:
        print(f"    {s.name}{_sidecars(s)}")

other = [s for s in skills if s.name not in ANTHROPIC | SUPERPOWERS]
if other:
    print(f"\n  Other: {[s.name for s in other]}")

souls = [d for d in mi.documents if d.kind == "Soul"]
print(f"\nSouls: {len(souls)}")
for soul in souls:
    files = [
        label
        for label, field in (
            ("SOUL.md", "soul_content"), ("IDENTITY.md", "identity_content"),
            ("STYLE.md", "style_content"), ("AGENTS.md", "agents_content"),
            ("HEARTBEAT.md", "heartbeat_content"),
        )
        if soul.spec.get(field)
    ]
    display = soul.spec.get("display_name")
    label = f"{soul.name} ({display})" if display else soul.name
    print(f"  {label} — {', '.join(files)}")

contexts = [d for d in mi.documents if d.kind == "AgentDefinition"]
print(f"\nAgent definitions (AGENTS.md): {len(contexts)}")

print(f"\n{'=' * 60}")
print(f"TOTAL: {len(skills)} skills + {len(souls)} souls + {len(contexts)} agent definitions")
print("ALL LOADED FROM REAL MARKET SOURCES — ZERO MODIFICATION")
print("=" * 60)

if mi.composition_result:
    cr = mi.composition_result
    print(f"\nMissing dependencies: {cr.missing}" if cr.missing
          else "\nAll declared dependencies resolved")
