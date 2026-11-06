# The blueprint file (`kind: ServiceBlueprint`)

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: ServiceBlueprint
metadata:
  name: Travel expense reimbursement
who: The employee                   # who lives the journey
about: From filing the expense to the money in the account. Made from 10 interviews, the accounts payable flow and HR tickets.
phases: [File, Approve, Get paid]   # names, or { id, name }
actors:                             # who acts: roles, areas, partners — never a person's name
  - { id: manager, name: Manager, layer: front }               # front: the employee sees them
  - { id: payables, name: Accounts payable, layer: back }      # back: they do not
systems:                            # names, or { id, name }
  - { id: erp, name: Finance ERP }
moments:                            # in the employee's order
  - id: wait
    phase: Approve
    customer: Waits for news — 6 days of nothing      # what the employee does
    feels: 1                        # 1 (bad) to 5 (good), only when the material says
    marks: [fail]                   # fail · wait
    evidence: []                    # what they see or keep
    front: []                       # on stage: { actor, does } or just what they see («Guided form»)
    back: [{ actor: payables, does: Checks the receipt and posts it to the ERP }]
    support: [erp]
    promise: { says: We let you know when it is approved, owner: payables, within: 1 day }
    pains: [{ says: I thought they had lost my expense, source: 3 of 10 interviews }]
    way: expenses#check             # optional: the stage of a way-of-working way of working behind it
actions:
  - { moment: wait, does: Email «your expense is approved», owner: payables, due: 2026-12 }
```

Rules: ids in `a-z0-9-`; a moment's `phase`, an actor in `front`/`back`/`promise.owner`/`actions.owner`, a system in
`support` and an action's `moment` must exist; `feels` is 1 to 5; a key not shown here is an error (with the key it is
closest to). Errors say their line.
