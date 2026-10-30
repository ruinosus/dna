# What the words mean

The way of working is written in the words Jira, Azure DevOps, ServiceNow and stage-gate use. Teams' documents mix them
up; sorting them out is most of the job. Be critical on your own: when the material breaks one of these, say so (first,
with your bet), never copy the mistake into the file.

- **The work item** goes through the flow: a feature, a request, a ticket, an opportunity. The stages are where *it*
  stands — not what people do.
- **A stage** is the item's state: where it stands, with a **key question** it answers and what it **delivers**.
  4 to 8 is usual; more than 10 usually means activities became stages.
- **An activity** is what is done inside a stage (write test cases, code review, call the client, update the docs).
  Never a stage of its own: it goes in that stage's `activities` (`required: true` when a gate checks it).
- **A ritual** (planning, refinement, daily, sprint review, retrospective) has a cadence, not a place in the flow.
  Leave it out of the file — not a stage, not an activity; mention it in your summary if the team cares.
- **A phase** is a milestone that ends in a deliverable, usually at a gate (Discovery, Delivery, Operation). **An
  environment or a system** (DEV, QA, UAT, PRD, "the portal") is never a phase: it is a stage's `where`.
- **A lane** is who *leads* a stage: a role, a team or an area. The stage sits in that lane on the map.
- **A role** is a function (PO, Tech Lead, QA, Legal, a partner team) — **never a person's name**. A person the
  material names is who holds a role: the lane or role stays the function, and the person may go in the lane's `sub`.
  Who **takes part** in a stage is its `roles` (role ids); the lane says only who leads.
- **A gate** is where someone decides the work goes on. It needs **who approves** (a role), **what must be ready**
  (`criteria`: outputs, a stage's required activities, numbers) and **where it goes back** when it does not pass
  (`on_fail`). A "gate" no one approves is a stage, or a wish.
- **An output** is something that exists after the stage (a document, a build, a signed form, a number) — not an
  activity ("testing" is an activity; "test report" is an output).
- **A number** that says it worked: a starting point, a target and how it is measured; mark that output `kpi: true`,
  and let the flow close in a stage that measures it. Never make one up: ask.
- **A limit** (`wip`, items at once) is the team's to say: write it only when the material or the person says it.

## RACI, as the workbook writes it

From the file, never asked separately: **R** — the roles of the stage's lane that take part; **C** — the other roles
that take part; **A** — who approves the gate after the stage. Someone only informed (**I**) is not modelled.
