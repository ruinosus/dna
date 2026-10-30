---
name: drill-en
tags: [build, en]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Skill, Read, Write, Edit, Bash]
---
Make an incident drill from this runbook, save it as queue.drill.yaml and build the game. Decide small things yourself; don't ask me anything.

"# Runbook — order queue backing up
## A. Check the queue
Look at the queue dashboard: how many messages wait and how fast it grows.
## B. Scale the workers
If the queue grows for more than 10 minutes, scale the workers to 10. Only the platform team can scale.
## C. Pause the marketing emails
If scaling is not enough, pause the marketing emails, which flood the queue. Marketing must agree."
