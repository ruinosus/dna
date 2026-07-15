---
description: Execute the implementation planning workflow using the plan template to generate design artifacts.
scripts:
  sh: scripts/bash/setup-plan.sh --json
  ps: scripts/powershell/setup-plan.ps1 -Json
---

The user input to you can be provided directly by the agent or as a command argument — you **MUST** consider it before proceeding.

User input:

$ARGUMENTS

1. Run `{SCRIPT}` from the repo root and parse JSON for FEATURE_SPEC, IMPL_PLAN, SPECS_DIR, BRANCH.
2. Read the feature spec and the constitution at `.specify/memory/constitution.md`.
3. Execute the plan template, generating `plan.md`, `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`.
4. Verify the Constitution Check gate passes before proceeding.
