---
name: code-quality
description: Code quality standards that the SWE agent must follow when writing code
severity: warn
scope: output
---

- Never commit code without corresponding tests
- Never disable or skip existing tests to make new code pass
- Never introduce TODO or FIXME comments without linking to a tracking issue
- Never hardcode secrets, API keys, or credentials — use environment variables
- Never use wildcard imports (e.g., from module import *)
- Never suppress linter warnings without a justifying inline comment
- Always follow the repository's existing naming conventions and code style
- Always handle errors explicitly — never use bare except or empty catch blocks
