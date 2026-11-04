# The blueprint file (front-of-house/v1)

```yaml
format: front-of-house/v1
name: Returning an online purchase
who: The shop's customer            # who lives the journey
about: From asking for a return to the money back. Made from 10 interviews, the logistics flow and support tickets.
phases: [Ask, Send, Get back]       # names, or { id, name }
actors:                             # who acts: roles, areas, partners — never a person's name
  - { id: support, name: Support, layer: front }     # front: the customer sees them
  - { id: logistics, name: Logistics, layer: back }  # back: they do not
systems:                            # names, or { id, name }
  - { id: warehouse, name: Warehouse system }
moments:                            # in the customer's order
  - id: wait
    phase: Send
    customer: Waits for news — 6 days of nothing     # what the customer does
    feels: 1                        # 1 (bad) to 5 (good), only when the material says
    marks: [fail]                   # fail · wait
    evidence: []                    # what they see or keep
    front: []                       # on stage: { actor, does } or just what they see («Guided form»)
    back: [{ actor: logistics, does: The warehouse receives and checks the parcel }]
    support: [warehouse]
    promise: { says: We let you know when it arrives, owner: logistics, within: 1 day }
    pains: [{ says: I thought they had lost my parcel, source: 3 of 10 interviews }]
    way: returns#check              # optional: the stage of a way-of-working way of working behind it
actions:
  - { moment: wait, does: Email «we received your parcel», owner: logistics, due: 2026-12 }
```

Rules: ids in `a-z0-9-`; a moment's `phase`, an actor in `front`/`back`/`promise.owner`/`actions.owner`, a system in
`support` and an action's `moment` must exist; `feels` is 1 to 5. Errors say their line.
