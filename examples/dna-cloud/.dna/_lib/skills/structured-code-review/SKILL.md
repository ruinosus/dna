---
name: structured-code-review
description: A structured checklist + output format for reviewing a change.
---

When reviewing a diff or a pull request, work the change in this order and
report findings in this shape.

## What to check (in priority order)

1. **Correctness** — Does it do what it claims? Off-by-one, null/None handling,
   error paths, race conditions, wrong boundary conditions, broken invariants.
2. **Security** — Injection, unsanitized input, secrets in code, missing
   authz/authn, unsafe deserialization, path traversal.
3. **Tests** — Is the new behavior covered? Are error cases tested? Does any
   change silently weaken or skip an existing test?
4. **Clarity** — Names that mislead, functions doing two things, duplicated
   logic, comments that lie about the code.
5. **Style** — Only if it obscures intent; never litigate taste over substance.

## How to report

For each finding, use one prefix and always name the location and the fix:

- `[BLOCKER]` — must fix before merge (correctness / security / data loss).
- `[SUGGESTION]` — worth improving, does not block.
- `[QUESTION]` — needs the author's intent before you can judge.
- `[PRAISE]` — something genuinely well done.

Close with exactly one verdict:

- **APPROVE** — ready to merge (say what you verified).
- **REQUEST_CHANGES** — list the blockers.
- **COMMENT** — observations only, no blockers.
