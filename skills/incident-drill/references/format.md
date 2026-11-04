# The drill file (`kind: IncidentDrill`)

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: IncidentDrill
metadata:
  name: Checkout down at 3 a.m.
from: runbooks/checkout.md          # the runbook, beside the drill: its passages show in the game
about: Payments start failing at night, right after a deploy.
clock: "03:12"                      # when the player comes in (HH:MM)
impact: lost orders                 # what `lost` counts
call_minutes: 3                     # what calling someone in from the room panel costs (3 by default)
roles:
  - { id: oncall, name: On-call, you: true }          # the player; `in: true` = in the room from the start
  - { id: release, name: Release, can: [revert-deploy] }
  - { id: comms, name: Communications, can: [status-page] }
start: alert                        # the first scene (the first one when left out)
scenes:
  - id: panel
    says: The dashboard shows 42% of payments failing since 03:09…
    draw: |                         # optional: visual-explainer's text syntax (or JSON)
      title Errors
      size 600x300
      …
    injects:                        # what comes in while they look
      - { at: "03:16", says: Support — three customers complaining on Twitter. }
    choices:
      - label: Revert the 02:58 deploy
        go: reverted                # the scene it leads to
        runbook: §2                 # the runbook's mark it follows (a heading, a mark in the text, or a numbered
                                    # step under a heading: «Steps 4» is the 4th step under «## Steps»)
        minutes: 4
        lost: 150                   # impact added
        needs: revert-deploy        # someone in the room must `can` this; otherwise the game asks to call them
      - label: Tell the customers first
        go: told
        needs: status-page
        notifies: true              # tells the people affected (the debrief times it)
      - label: Escalate to the incident lead
        go: lead-joins
        calls: lead                 # brings that role into the room
        then: The lead joins and asks why the deploy is still out.   # said after choosing (optional)
  - id: done
    says: Checkout is back.
    end: resolved                   # or `worse`: the game ends here
gaps:                               # what the runbook does not say — the drill's real product
  - { says: Nobody says who tells the customers, or when., source: whole runbook }
```

Rules: ids in `a-z0-9-`; every `go` is a scene; every scene that is not an end has a choice; some end can be reached
from the start; `calls` names a role. A choice that `needs` what nobody in the room `can` is shown as blocked until the
players call someone who can — say who can in `roles`.
