---
name: solution
description: Puts one process together as a solution — the way of working, the what-if simulation, the customer's journey, the incident drill, the Copilot Studio agents and the lesson that explains it — in one short .solution.yaml that names the pieces, checks each with its own skill, says which piece fell behind the way, and makes one offline page with a tab per piece. Comes with solution accelerators to start from (an employee self-service assistant with Workday, a customer service desk with its agents, the delivery of an assistant). In English or Portuguese. Use when someone wants the whole picture of a process in one place, to bring the skills' outputs together for a team or a client, or to start from a ready example ("put our HR self-service together as one solution", "start from the service desk accelerator", "monta a solução do atendimento").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Each piece is checked and drawn by its own dna skill, so it works fully where the other skills are beside it (the plugin, the npm package); alone, it checks the solution file and lists the pieces. In Claude Code the dna mod adds /solution.
metadata:
  version: "2.0.0"
---

# solution: a process, every piece together

A **solution** is one process seen by every skill that has something to say about it, kept in **one short file**,
`<id>.solution.yaml`, beside the pieces. You write only that file (and, when they are not there yet, the pieces, with
their own skills). `scripts/build.mjs` checks each piece with its own skill and makes the page.

Paths below are relative to this skill's folder (the folder this file is in); the other skills are its neighbours
(`../way-of-working`, `../process-simulation`…).

## 1. Start from an accelerator, or from what the person has

```
node scripts/build.mjs --list
node scripts/build.mjs --new <accelerator> <folder>
```

The **solution accelerators** are complete solutions to copy and change: `employee-self-service` (an assistant with
Workday, after Microsoft's public sample), `service-desk` (a customer service desk and its six Copilot Studio agents) and
`assistant-delivery` (delivering an assistant, with the gate that sends it back). Offer the closest one when the person
starts from nothing.

When they already have pieces (a `.way.yaml`, a `.sim`, a folder of cloned agents), write the solution around them.

## 2. Write the solution

`references/format.md` has every field. In short:

```yaml
format: opening-night/v1
name: Central de atendimento
about: Do chamado do cliente ao encerramento.
lang: pt                      # en (default) or pt: the page and the messages
way: service-desk.way.yaml    # the process (way-of-working)
sim: service-desk.sim         # what if (process-simulation)
blueprint: service-desk.blueprint.yaml   # the journey (service-blueprint)
drill: service-desk.drill.yaml           # when it goes wrong (incident-drill)
agents: agents                # the Copilot Studio agents (agent-review), with profile: <team>.standard.yaml
lesson: service-desk.chalk    # the idea explained by drawing (visual-explainer)
```

Every piece is optional; name at least one. **The way is the source:** when there is one and a piece is missing, make
it from the way with way-of-working — `node ../way-of-working/scripts/build.mjs <id>.way.yaml --lens
sim|blueprint|drill --write` — and tell the person its `# bet:` lines are made up and need their numbers. A piece can
also be written by hand (no `# from:` line at its top): it is kept as it is.

## 3. Check

```
node scripts/build.mjs <id>.solution.yaml --check [--json]
```

Each piece: there or not, passing its own skill's check or not (exit 4, with that skill's messages: fix the piece with
its skill), and each lens **up to date with the way** — a lens whose `# from: <way>@<version>` is not the way's current
version is said, with the command that makes it again. It may have been edited by hand: look before writing over it
(`--force`), and never write over it without asking.

## 4. The page

```
node scripts/build.mjs <id>.solution.yaml [--lang en|pt] [--out <folder>]
```

It writes `<id>.solution.html`: one file that opens offline, with a summary (each piece, the question it answers, where
it stands) and a tab per piece, each drawn by its own skill — the map, the simulation, the journey, the drill, the
agents compared, the lesson. Tell the person what to open first, and that every number in it is **a model, not a
forecast**: each piece says where its numbers came from.

## Never

- Never present a lens's bets as the person's numbers: say how many there are, and ask for the real ones.
- Never write over a piece that differs from its lens without asking: it may hold the person's own edits.
- Never put a client's agents or data in an accelerator: the accelerators are fictional or public.

## In Claude Code

With the dna plugin, a `.solution.yaml` you write is checked for its format (a broken one is refused with the
messages). `/check-solution [file]` shows its pieces in a pane, each with where it stands, and a button that makes a lens
again from the way when it fell behind — asking first, since it may have been edited by hand.
