"""
Prova de conceito: SDK lê 31+ skills REAIS do mercado sem modificação.

- 17 skills da Anthropic (agentskills.io)
- 14 skills do Superpowers (agentskills.io)
- 1 soul do SoulSpec (soulspec.org)
- 1 AGENTS.md (agents.md)

To install external dependencies declared in manifest.yaml:
    from dna.extensions.helix.installer import dna_install
    result = dna_install(".dna", "market-demo")
    # Downloads skills from github:anthropics/skills and github:jbaruch/superpowers
    # into .dna-cache/, generates dna.lock
"""

import sys
from pathlib import Path

# Ensure the Python SDK is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))

from dna import Kernel

mi = Kernel.quick("market-demo", base_dir=str(Path(__file__).resolve().parent / ".dna"))

print("=" * 60)
print("MARKET INTEGRATION DEMO — REAL CONTENT")
print("=" * 60)

# Skills
skills = mi.all("Skill")
print(f"\n📦 Total Skills loaded: {len(skills)}")

anthropic_skills = {
    "algorithmic-art", "brand-guidelines", "canvas-design", "claude-api",
    "doc-coauthoring", "docx", "frontend-design", "internal-comms",
    "mcp-builder", "pdf", "pptx", "skill-creator", "slack-gif-creator",
    "theme-factory", "web-artifacts-builder", "webapp-testing", "xlsx",
}

superpowers_skills = {
    "brainstorming", "dispatching-parallel-agents", "executing-plans",
    "finishing-a-development-branch", "receiving-code-review",
    "requesting-code-review", "subagent-driven-development",
    "systematic-debugging", "test-driven-development", "using-git-worktrees",
    "using-superpowers", "verification-before-completion", "writing-plans",
    "writing-skills",
}

found_anthropic = []
found_superpowers = []
found_other = []

for s in skills:
    if s.metadata.name in anthropic_skills:
        found_anthropic.append(s)
    elif s.metadata.name in superpowers_skills:
        found_superpowers.append(s)
    else:
        found_other.append(s)

print(f"\n  🔶 Anthropic (agentskills.io): {len(found_anthropic)}/{len(anthropic_skills)}")
for s in sorted(found_anthropic, key=lambda x: x.metadata.name):
    refs = len(s.spec.references)
    scripts = len(s.spec.scripts)
    assets = len(s.spec.assets)
    extras = []
    if refs:
        extras.append(f"{refs} refs")
    if scripts:
        extras.append(f"{scripts} scripts")
    if assets:
        extras.append(f"{assets} assets")
    extra_str = f" ({', '.join(extras)})" if extras else ""
    print(f"    {s.metadata.name}{extra_str}")

print(f"\n  ⚡ Superpowers: {len(found_superpowers)}/{len(superpowers_skills)}")
for s in sorted(found_superpowers, key=lambda x: x.metadata.name):
    refs = len(s.spec.references)
    scripts = len(s.spec.scripts)
    assets = len(s.spec.assets)
    extras = []
    if refs:
        extras.append(f"{refs} refs")
    if scripts:
        extras.append(f"{scripts} scripts")
    if assets:
        extras.append(f"{assets} assets")
    extra_str = f" ({', '.join(extras)})" if extras else ""
    print(f"    {s.metadata.name}{extra_str}")

if found_other:
    print(f"\n  ❓ Other: {len(found_other)}")
    for s in found_other:
        print(f"    {s.metadata.name}")

# Souls
souls = mi.all("Soul")
print(f"\n🧠 Souls: {len(souls)}")
for soul in souls:
    files = []
    if soul.spec.get("soul_content"):
        files.append("SOUL.md")
    if soul.spec.get("identity_content", ""):
        files.append("IDENTITY.md")
    if soul.spec.style_content:
        files.append("STYLE.md")
    if soul.spec.agents_content:
        files.append("AGENTS.md")
    if soul.spec.heartbeat_content:
        files.append("HEARTBEAT.md")
    print(f"  {soul.metadata.name} ({soul.spec.display_name}) — {', '.join(files)}")

# AGENTS.md
contexts = mi.all("AgentContext")
print(f"\n📋 Agent Contexts: {len(contexts)}")

# Summary
print(f"\n{'=' * 60}")
print(f"TOTAL: {len(skills)} skills + {len(souls)} souls + {len(contexts)} agent contexts")
print(f"ALL LOADED FROM REAL MARKET SOURCES — ZERO MODIFICATION")
print(f"{'=' * 60}")

# Composition validation
if mi.composition_result:
    cr = mi.composition_result
    if cr.missing:
        print(f"\n⚠️  Missing dependencies: {cr.missing}")
    else:
        print(f"\n✅ All declared dependencies resolved")
