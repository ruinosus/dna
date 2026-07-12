---
name: review-integrity
description: Keeps code review honest — evidence-based, no rubber-stamping.
severity: warn
scope: output
---

- Never approve a change you did not actually examine; if you cannot verify a claim, say so instead of assuming it holds.
- Ground every finding in the diff — quote the specific line or symbol; never invent code that is not there.
- Distinguish blockers (correctness, security, data loss) from suggestions (clarity, style) — do not inflate preferences into blockers.
- Do not flag a "problem" without stating the concrete fix or the question that would resolve it.
- Acknowledge at least what you verified, so an empty review never reads as a silent pass.
