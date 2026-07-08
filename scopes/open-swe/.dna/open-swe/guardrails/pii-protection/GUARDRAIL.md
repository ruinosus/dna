---
name: pii-protection
description: Prevent the agent from leaking or mishandling personally identifiable information
severity: error
scope: output
---

- Never include real email addresses, phone numbers, or physical addresses in code, comments, or commit messages
- Never log PII fields (name, email, SSN, credit card) at INFO level or above — use DEBUG with redaction
- Never store PII in plain text — always encrypt at rest
- Never include PII in error messages or stack traces returned to users
- Never use real user data in test fixtures — use synthetic or anonymized data
- Never expose PII through API responses unless explicitly required and documented
