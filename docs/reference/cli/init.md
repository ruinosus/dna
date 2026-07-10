# `dna init`

Make a project agent-ready: board + skill + AGENTS.md + git hooks.

One command bootstraps everything an AI coding agent needs to work
DNA-style in this project:


  .dna/<scope>/               SDLC board (Genome via the kernel)
  <tool>/skills/dna-sdlc-cli/ the SDLC workflow skill (agentskills.io),
                              projected per --tools (.claude/skills,
                              .github/skills, .cursor/skills, ...)
  AGENTS.md                   the canonical instruction surface
                              (agents.md/v1 — read by 28+ agent tools)
  git hooks                   Work-Item commit trailers

The assets ship inside dna-cli as an embedded onboarding scope of real
Kinds and are materialized by the SDK's own byte-faithful
readers/writers — one Kind, N regenerable projections. AGENTS.md serves
every tool at once; Gemini CLI users can point GEMINI.md at it.

With --from, the skills + AGENTS.md come from a DISTRIBUTED onboarding
pack (your team's own conventions) instead of the embedded scope. The
pack is fetched and validated with the same machinery as `dna install`
(untrusted-input defenses included) but only PROJECTED into tool
directories — nothing from the pack is written to the .dna/ source.
Review the projected files before committing: a skill is agent
instructions; treat a third-party pack like a dependency.

Idempotent: re-running never overwrites an existing file unless
--force is given; the summary reports what was created vs skipped.

Examples:


  dna init                              # here, board '<dirname>-dev'
  dna init --scope acme-dev             # explicit board scope
  dna init --tools all                  # every supported tool dir
  dna init --tools claude,cursor        # explicit projection set
  dna init --dir ../other-project       # initialize another directory
  dna init --from github:acme/onboarding-pack@v1   # your team's pack
  dna init --from local:../onboarding-pack         # offline authoring loop

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna init --help`.

## `dna init`

Make a project agent-ready: board + skill + AGENTS.md + git hooks.

One command bootstraps everything an AI coding agent needs to work
DNA-style in this project:


  .dna/<scope>/               SDLC board (Genome via the kernel)
  <tool>/skills/dna-sdlc-cli/ the SDLC workflow skill (agentskills.io),
                              projected per --tools (.claude/skills,
                              .github/skills, .cursor/skills, ...)
  AGENTS.md                   the canonical instruction surface
                              (agents.md/v1 — read by 28+ agent tools)
  git hooks                   Work-Item commit trailers

The assets ship inside dna-cli as an embedded onboarding scope of real
Kinds and are materialized by the SDK's own byte-faithful
readers/writers — one Kind, N regenerable projections. AGENTS.md serves
every tool at once; Gemini CLI users can point GEMINI.md at it.

With --from, the skills + AGENTS.md come from a DISTRIBUTED onboarding
pack (your team's own conventions) instead of the embedded scope. The
pack is fetched and validated with the same machinery as `dna install`
(untrusted-input defenses included) but only PROJECTED into tool
directories — nothing from the pack is written to the .dna/ source.
Review the projected files before committing: a skill is agent
instructions; treat a third-party pack like a dependency.

Idempotent: re-running never overwrites an existing file unless
--force is given; the summary reports what was created vs skipped.

Examples:


  dna init                              # here, board '<dirname>-dev'
  dna init --scope acme-dev             # explicit board scope
  dna init --tools all                  # every supported tool dir
  dna init --tools claude,cursor        # explicit projection set
  dna init --dir ../other-project       # initialize another directory
  dna init --from github:acme/onboarding-pack@v1   # your team's pack
  dna init --from local:../onboarding-pack         # offline authoring loop

```text
dna init [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--dir` | Project directory to initialize (default: current directory). _(default: `.`)_ |
| `--force` | Overwrite existing onboarding files (skill projections, AGENTS.md). The board Genome is never rewritten — an existing board is verified and kept. |
| `--from` | Project a DISTRIBUTED onboarding pack instead of the embedded one: `github:owner/repo[/subdir][@ref]`, `local:<path>`, or a bare directory path. The pack must carry at least one agentskills.io Skill bundle; a root AGENTS.md replaces the embedded instruction surface (absent: the embedded one is used, with a note). Pack content is validated with the same defenses as `dna install` and only PROJECTED into tool directories — combine with `dna install <same-uri>` when you also want it on the board. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable summary. |
| `--scope` | Board scope name (default: '<dirname>-dev', slugified — the pilot convention for a dev-time SDLC board). |
| `--tools` | Comma-separated agent tools to project the SDLC skill for (claude, copilot, cursor, opencode — or 'all'). The SKILL.md format is identical across tools; only the directory differs. _(default: `claude,copilot`)_ |

