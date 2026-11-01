---
type: tool_used
tool: Bash
input_match: 'build\.mjs(?![^\n]*--no-present)[^\n]*\.chalk'
min: 1
---
A drawing to present to a client is built to open presenting: the build presents by default, so it is never called
with --no-present.
