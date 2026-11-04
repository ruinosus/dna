<h1 align="center">dress-rehearsal</h1>

<p align="center"><b>Give Claude your incident runbook. Get a drill your team can play — and, at the end, what the runbook does not say.</b></p>

<p align="center">
  <img src="https://ruinosus.github.io/house-lights/dress-rehearsal/images/checkout-scene.png" alt="A drill in play: the clock at 03:14, a graph of payment errors, a message from support, three choices — one blocked until the Release team is called" width="860">
</p>

<p align="center">
  An <a href="https://agentskills.io">Agent Skill</a> for Claude Code, claude.ai, the Claude API and other tools that load skills.<br>
  <a href="https://ruinosus.github.io/house-lights/dress-rehearsal/">Play the examples</a> in your browser.
</p>

---

## What it does

Most runbooks have never been run. They say «revert the deploy» and forget that the on-call cannot; they say
«escalate» and not to whom; nobody wrote down who tells the customers. You find out at 3 a.m.

dress-rehearsal reads the runbook (or a post-mortem) and turns it into a **drill**: the incident as scenes, with a clock
that runs, things that come in while you look (a message from support), choices with consequences — the runbook's step,
and the tempting wrong ones — who is in the room, and the impact growing. A choice that needs an access nobody in the
room has stays blocked until someone who can is called in.

At the end, a **debrief**: the timeline, how long it took to resolve and to tell the people affected, and **what the
runbook did not say** — the gaps Claude found while reading it, and the ones this game showed. Download it as Markdown
for the post-mortem, and the improvements as a CSV for your tracker. Then fix the runbook.

<p align="center"><img src="https://ruinosus.github.io/house-lights/dress-rehearsal/images/database-disk-debrief.png" alt="The debrief: 25 minutes to resolve, customers never told, the timeline, and what the runbook did not say" width="760"></p>

**For** tech leads and SREs preparing people for on-call, teams that want a «wheel of misfortune» without a game master,
and anyone who suspects their runbook would not survive a real night.

## How a conversation goes

A real run, from the evals (translated from Portuguese and shortened). The runbook had three lines: check the
authentication dashboard; if the identity provider has a problem, turn on contingency mode; if it is not solved in 20
minutes, escalate.

> **You:** make an incident drill from our login runbook
>
> **Claude:** The drill is drafted and passes the check — 13 scenes, two ends that resolve and two that get worse. The
> scenario's numbers are made up for the exercise (38% of logins failing since 09:02). In each scene there is the
> runbook's step and tempting ones that make it worse: «it's probably someone's network», «wait for the provider».
>
> 1. **Who can turn on contingency mode?** My bet: the incident lead, not the on-call — so in the game the on-call is
>    blocked and has to call someone in.
> 2. **How do you confirm the identity provider is the problem?** My bet: timeouts on the dashboard and the provider's
>    status page — the runbook says nothing about it.
> 3. **Escalate to whom?** My bet: the incident lead — only a guess.
> 4. **When do the 20 minutes start?** My bet: when the failures start on the dashboard, not when someone looked.
> 5. **Who tells the users and support?** My bet: communications, right after contingency is on. The runbook mentions
>    no warning at all.
> 6. **What happens if contingency is turned off too early?** My bet: the failures come back while the provider is
>    still unstable.
>
> What you skip stays as a gap in the debrief.

## Install

dress-rehearsal is one of the six skills of the [house-lights](../../README.md) plugin. **Claude Code:**

```
/plugin marketplace add ruinosus/house-lights
/plugin install house-lights@house-lights
```

Claude picks the skill by its description; to call it by name, `/house-lights:dress-rehearsal`. **claude.ai**: upload
`dress-rehearsal.zip` from the [latest release](https://github.com/ruinosus/house-lights/releases) in Settings › Capabilities ›
Skills (code execution on). **Claude API**: the same zip with the Skills API. **Other tools**: copy
`skills/dress-rehearsal` where the tool reads skills; it needs Node.js 18 or later. **npm**: `npx house-lights dress-rehearsal <file>`.

## The file

```yaml
format: dress-rehearsal/v1
name: Checkout down at 3 a.m.
from: runbooks/checkout.md          # the game shows each passage a choice follows
clock: "03:12"
impact: lost orders
roles:
  - { id: oncall, name: On-call, you: true }
  - { id: release, name: Release, can: [revert-deploy] }
start: alert
scenes:
  - id: panel
    says: The dashboard shows 42% of payments failing since 03:09…
    choices:
      - { label: Revert the 02:58 deploy, go: reverted, runbook: §2, minutes: 4, lost: 150, needs: revert-deploy }
      - { label: Investigate first, go: digging, minutes: 14, lost: 900 }
  - { id: reverted, says: Errors fall to 0%., end: resolved }
gaps:
  - { says: The runbook does not say who reverts., source: §2 }
```

The whole format is [`references/format.md`](../../skills/dress-rehearsal/references/format.md); two complete drills, with
their runbooks, are in [`skills/dress-rehearsal/examples/`](../../skills/dress-rehearsal/examples). The check is on the
graph: a choice to no scene or a scene with no way on says its line; a scene nobody reaches, an access nobody has,
nobody ever told, «escalate» to nobody and a mark the runbook does not have are printed «to look at».

## Develop

```
npm install       # at the repository root: the six skills are npm workspaces
npm run assets -w dev/dress-rehearsal/tools   # scripts/engine.mjs and assets/drill.html, from src/
npm run check -w dev/dress-rehearsal/tools    # the engine's checks, every example built, broken files and drawings, every example played in Chrome
npm run site -w dev/dress-rehearsal/tools     # docs/: the gallery
npm run zip -w dev/dress-rehearsal/tools      # dist/dress-rehearsal.zip
claude plugin eval . --ablation none --allow-tools Bash Write Edit --case <name>   # the evals in evals/
```

## License

MIT. Drawings by [chalk-talk](https://github.com/ruinosus/house-lights) (MIT; Rough.js MIT; Caveat and Shantell Sans,
SIL Open Font License).
