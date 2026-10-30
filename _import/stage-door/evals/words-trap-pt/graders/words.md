---
type: llm
focus: { source: file, path: squad.way.yaml }
---
The file sorts the words out: DEV, QA and PRD are not phases (they appear as a stage's `where`, and the phases are milestones); Sprint Planning is not a stage (a ritual); Code Review is an activity inside the development stage, not a stage; Carla Mendes and Rafael are not roles or lanes (the roles are PO and Tech Lead; a name may only appear as a lane's `sub`). The gate after the tests is approved by the Tech Lead role and goes back to development. The person allowed small decisions, so phase names, outputs and a lane for quality decided by Claude are fine; what fails is a fact the request contradicts. Sprint Planning appearing as an activity also fails (a ritual is neither a stage nor an activity).
