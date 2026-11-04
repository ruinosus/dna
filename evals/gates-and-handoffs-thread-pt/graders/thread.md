---
type: llm
focus: { source: file, path: compras.way.yaml }
---
The file (kind WayOfWorking) keeps the thread of the table: each input that is an output of an earlier step points to it with `from:` and that output's id (the quotation step receives the purchase request; contracting receives the approved purchase, an output of the approval gate; receiving receives the signed contract); the inputs that come from outside (the area's need, the supplier catalog) use `name:`. "Aprovação" is a gate after the quotation step (not a stage), approved by the manager role, going back to the quotation step on failure, with its outputs (approved purchase, reason for refusal) under the gate's `outputs`. Each step keeps its metrics in `metrics`. Roles are functions. Nothing is invented beyond small decisions.
