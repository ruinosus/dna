---
description: Break the plan down into an executable, dependency-ordered tasks.md.
scripts:
  sh: scripts/bash/check-prerequisites.sh --json
  ps: scripts/powershell/check-prerequisites.ps1 -Json
---

The user input to you can be provided directly by the agent or as a command argument — you **MUST** consider it before proceeding.

User input:

$ARGUMENTS

1. Run `{SCRIPT}` from the repo root to verify plan.md exists and collect the feature paths.
2. Load `.specify/templates/tasks-template.md` and the design docs (plan, data-model, contracts).
3. Generate `tasks.md` with dependency-ordered tasks; mark independent tasks `[P]` for parallel execution.
