---
description: Create or update the feature specification from a natural language feature description.
scripts:
  sh: scripts/bash/create-new-feature.sh --json "{ARGS}"
  ps: scripts/powershell/create-new-feature.ps1 -Json "{ARGS}"
---

The user input to you can be provided directly by the agent or as a command argument — you **MUST** consider it before proceeding.

User input:

$ARGUMENTS

Given that feature description, do this:

1. Run the script `{SCRIPT}` from the repo root and parse its JSON output for BRANCH_NAME and SPEC_FILE.
2. Load `.specify/templates/spec-template.md` to understand required sections.
3. Write the specification to SPEC_FILE using the template structure, replacing placeholders with concrete details derived from the feature description.
4. Report completion with the branch name, spec file path, and readiness for the next phase.

Focus on WHAT and WHY, never HOW. Write for business stakeholders, not developers.
