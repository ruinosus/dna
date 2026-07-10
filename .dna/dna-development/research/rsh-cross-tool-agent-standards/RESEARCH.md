---
apiVersion: github.com/ruinosus/dna/research/v1
kind: Research
metadata:
  name: rsh-cross-tool-agent-standards
spec:
  title: Cross-tool standards for agent instructions (AGENTS.md) and skills (SKILL.md)
  objective: Determine which market standards centralize AI-coding-agent instructions and skills across
    tools, to decide the canonical surfaces and projection targets for `dna init` (multi-tool agent onboarding).
  methodology: web-search-curated
  overall_confidence: high
  conducted_by: claude-code
  conducted_at: '2026-07-10T00:00:00+00:00'
  scope_ref: dna-development
  status: published
  visibility: shared
  owner: claude-code
  tags:
  - cli
  - onboarding
  - agents-md
  - agentskills
  - market-fidelity
  key_takeaways:
  - AGENTS.md is THE centralizing standard for agent instructions — stewarded under the Linux Foundation
    / Agentic AI Foundation, adopted by 28+ tools (Codex CLI, GitHub Copilot, Cursor, Windsurf, Amp, Devin,
    Aider, Zed, Jules, VS Code, JetBrains Junie); Claude Code also READS AGENTS.md, so a thin CLAUDE.md
    pointer is optional, not required
  - SKILL.md (agentskills.io) is THE centralizing standard for skills — ~40 tools (Claude Code, Codex,
    Copilot/VS Code, Cursor, Gemini CLI, Goose, OpenCode). The FORMAT is identical everywhere; only the
    DIRECTORY differs per tool
  - 'Per-tool skill directories: .claude/skills/ (Claude Code), .github/skills/ (Copilot), .cursor/skills/
    (Cursor), .opencode/skills/ (OpenCode); convention is lowercase-hyphen folder + a file named exactly
    SKILL.md'
  - Gemini CLI still uses GEMINI.md — do not generate it by default; document how to point Gemini at AGENTS.md
    instead
  - 'Design consequence for dna init: one Skill Kind as source of truth, N regenerable per-tool projections
    materialized by the byte-faithful agentskills writer; AGENTS.md is the canonical instruction surface,
    not a Claude-specific extra'
  executive_summary: 'The market has converged on two centralizing standards for making a repository legible
    to AI coding agents. For instructions, AGENTS.md (agents.md, now stewarded under the Linux Foundation
    / Agentic AI Foundation) is read by 28+ tools including Codex CLI, GitHub Copilot, Cursor, Windsurf,
    Amp, Devin, Aider, Zed, Jules, VS Code and JetBrains Junie — and Claude Code reads it too, which makes
    a consumer CLAUDE.md at most a thin optional pointer, never a duplicate. Gemini CLI is the notable
    holdout (GEMINI.md), best handled by documentation rather than default generation. For skills, the
    agentskills.io SKILL.md specification is adopted by roughly 40 tools (Claude Code, Codex, Copilot/VS
    Code, Cursor, Gemini CLI, Goose, OpenCode among them); the format — lowercase-hyphen bundle directory
    containing a file named exactly SKILL.md with name/description frontmatter and a markdown body — is
    identical across tools, and only the target directory differs (.claude/skills/, .github/skills/, .cursor/skills/,
    .opencode/skills/). The design consequence for `dna init` is direct: AGENTS.md is the canonical instruction
    surface serving every tool at once; the SDLC skill is ONE Kind in the embedded onboarding scope, projected
    once per selected tool directory by the SDK''s byte-faithful agentskills writer; and all generated
    content must be tool-agnostic (core spec fields only, no proprietary frontmatter, no tool-specific
    personas). DNA can centralize this because it already speaks both standards natively as Kinds.'
  findings:
  - id: f-agents-md-centralizing
    title: AGENTS.md is the cross-tool instruction standard (28+ tools, LF stewardship)
    evidence_rating: evidence-based
    summary: 'The agents.md standard is stewarded under the Linux Foundation / Agentic AI Foundation and
      adopted by 28+ tools: Codex CLI, GitHub Copilot, Cursor, Windsurf, Amp, Devin, Aider, Zed, Jules,
      VS Code, JetBrains Junie, and others. Claude Code also reads AGENTS.md, so tool-specific instruction
      files reduce to optional thin pointers. Source: https://agents.md/'
    source_refs: []
    tags:
    - agents-md
    - adoption
  - id: f-skill-md-centralizing
    title: SKILL.md (agentskills.io) is the cross-tool skill standard (~40 tools)
    evidence_rating: evidence-based
    summary: 'The agentskills.io specification defines a skill as a lowercase-hyphen bundle directory
      containing a file named exactly SKILL.md (frontmatter name/description + markdown body). Adopted
      by ~40 tools including Claude Code, Codex, Copilot/VS Code, Cursor, Gemini CLI, Goose and OpenCode.
      The format is identical across tools; only the discovery directory differs. Source: https://agentskills.io/specification'
    source_refs: []
    tags:
    - agentskills
    - adoption
  - id: f-per-tool-skill-dirs
    title: Only the skill DIRECTORY is tool-specific
    evidence_rating: evidence-based
    summary: 'Per-tool skill discovery directories: .claude/skills/ (Claude Code), .github/skills/ (GitHub
      Copilot), .cursor/skills/ (Cursor), .opencode/skills/ (OpenCode). Therefore one Skill Kind can be
      projected byte-identically into N directories — the projections are regenerable artifacts, the Kind
      is the source of truth. Sources: https://agentskills.io/specification + per-tool docs.'
    source_refs: []
    tags:
    - agentskills
    - design
  - id: f-gemini-holdout
    title: Gemini CLI still uses GEMINI.md
    evidence_rating: evidence-based
    summary: 'Gemini CLI reads GEMINI.md rather than AGENTS.md. Rather than generating another instruction
      file by default, document the pointer pattern (a one-line GEMINI.md referring to AGENTS.md, or Gemini''s
      contextFileName setting). Source: Gemini CLI documentation.'
    source_refs: []
    tags:
    - gemini
    - edge-case
  created_at: '2026-07-10T19:25:31+00:00'
  updated_at: '2026-07-10T19:25:31+00:00'
---

# Research — Cross-tool standards for agent instructions (AGENTS.md) and skills (SKILL.md)

Methodology: web-search-curated · 0 sources · 4 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
