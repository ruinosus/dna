---
type: llm
focus: { source: file, path: entrega.way.yaml }
---
The file (format stage-door/v1) has one gate after the testing stage (homologação) — not two gates after the same
stage — whose `approvals` list the tech lead with no condition and security with a `when` that says it is a change to
payments; a rejection goes back to development (`on_fail`). Roles are functions, not names; nothing is invented.
