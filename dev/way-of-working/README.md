<h1 align="center">way-of-working</h1>

<p align="center"><b>Give Claude your team's process — the PDF, the slides, what everyone just knows — and get one clear, checkable way of working.</b></p>

<p align="center">
  <img src="https://ruinosus.github.io/dna/way-of-working/images/feature-delivery-map.png" alt="The map of a delivery flow: phases Discovery, Delivery and Operation on top, Product, Engineering and Quality in the rows, the stages in order and two gates with who approves them" width="860">
</p>

<p align="center">
  An <a href="https://agentskills.io">Agent Skill</a> for Claude Code, claude.ai, the Claude API and other tools that load skills.<br>
  <a href="https://ruinosus.github.io/dna/way-of-working/">Open the gallery</a> to click through the maps, play the explainers and download the workbooks.
</p>

---

## What it does

Most teams' way of working lives in a 30-page PDF, a few slides and the head of whoever has been there longest. Ask
"who approves the release?" and you get three answers. way-of-working reads what exists and writes it down as **one file**:

- the **stages** the work goes through, in order, each with its key question and what it delivers;
- the **phases** (milestones), and **who leads** each stage;
- the **gates** — who approves, what must be ready, where the work goes back when it does not pass;
- the **roles** and who takes part where (the RACI comes from it);
- **what each stage receives and from where** — an output of an earlier stage or gate, or something from outside — and
  its **metrics**; what **comes out of each gate** (the decision, what was approved);
- the **number** that says it worked, when there is one.

It **bets, asks, and never invents**: what the material implies becomes a bet you confirm; what it does not say becomes
a question — all of them in one message. It also sorts out the usual mix-ups on its own: an activity written as a stage,
a daily or a planning in the flow, DEV/QA/PRD used as phases, a person's name where a role should be.

**For** whoever leads a team (get the process out of the PDF), whoever joins it (a map or an explainer instead of 30 pages),
whoever decides at the gates (the checklist in hand), and whoever designs processes for others.

## What you get

From the one `<id>.way.yaml`:

| | |
|---|---|
| **The file** (`.way.yaml`) | The source. Plain text you keep in Git; everything else is made from it. A mistake says its line. |
| **The map** (`.html`) | One page that opens offline: phases on top, who leads in the rows, stages in order, gates under the stage they close. Click a stage or a gate for its detail — where each input comes from, who receives each output. A **Stages** tab with the table teams know (comes in, delivers, roles, metrics; the gate as a row); tabs for Roles (RACI), Gates and Outputs; download the workbook, the file or a PNG. «To look at» says what does not hold. |
| **The workbook** (`.xlsx`) | Summary, Stages (with where each input comes from, and metrics), Gates (with what comes out), Roles (RACI), Outputs, KPIs, a **Gate checklist** for the meeting and the **Thread** — who delivers each output and who receives it. Header frozen, filters on, lanes in colour. Opens in Excel, Numbers and LibreOffice. |
| **The explainer** (`.explainer.html`) | The flow drawn stroke by stroke, a chapter per phase, each gate with who approves it and its way back — made with [visual-explainer](https://github.com/ruinosus/dna). |

<table>
  <tr>
    <td width="50%"><img src="https://ruinosus.github.io/dna/way-of-working/images/scrum-explainer.png" alt="A hand-drawn explainer of a Scrum team: Capture, Refine, Build, Accept, Release and Measure, with the Ready and Done gates"></td>
    <td width="50%"><img src="https://ruinosus.github.io/dna/way-of-working/images/service-desk-map.png" alt="The map of a service desk: Customer, first level and specialists in the rows; a gate decides whether the ticket is escalated"></td>
  </tr>
  <tr>
    <td>The explainer of a Scrum team: Definition of Ready and Done as gates, and where each sends the work back.</td>
    <td>A service desk (in Portuguese): solved at first level, or escalated to a specialist.</td>
  </tr>
</table>

### And back

Someone edits the workbook — renames a stage, changes who approves a gate, adds a row. Give it back to Claude: it lists
each change, one by one, flags the ones that remove something or change a gate, and writes into the `.way.yaml` only
the ones you take.

## How a conversation goes

A real run in Claude Code, from a fictional editorial team's process document (translated from Portuguese and
shortened):

> **You:** turn processo-editorial.md into our way of working. Save it as editorial.way.yaml.
>
> **Claude:** The draft is in `editorial.way.yaml` and passes the format: 7 stages, 3 gates, 4 phases, 4 lanes. What I
> already sorted out:
> - The **weekly pitch meeting** is out of the flow — it is a meeting, not a place the content goes through. Its
>   decision became the gate **"Pitch approved?"**, approved by the Editor-in-chief.
> - **Marina Okada** is not a role: the role is Editor-in-chief; her name only appears beside the lane.
> - **Proofreading** and **fact-checking** became required activities of Review; "back to Writing" became the gate
>   **"Facts right?"**, approved by the Reviewer.
>
> 1. **Who approves "Ready to publish?"** The document only says "someone checks text and art together". My bet is
>    the **Section editor**, who schedules and publishes.
> 2. …
> 3. **Is "Staging" a real phase?** The document defines it by the CMS preview environment…
> 4. **Should I add "Share on social media" after publishing?** The Social media role takes part in nothing today.
> 5. **Which audience number says it worked?** The document only says "we track audience", and I won't make it up.
> 6. **When a pitch is rejected, what happens to it?** My bet: it is archived.
>
> **You:** 1 yes. 2 yes. 3 merge it with Publishing, Staging is not a phase. 4 yes. 5 skip, no target yet. 6 archived.
> Go ahead and make everything.
>
> **Claude:** Done — the map, the workbook and the explainer. Still open: no stage measures the result (you skipped the
> target), and the document does not say where "Ready to publish?" sends the work back, so I left it blank.

## Install

way-of-working is one of the six skills of the [dna](../../README.md) plugin. **Claude Code:**

```
/plugin marketplace add ruinosus/dna
/plugin install dna@dna
```

Claude picks the skill by its description; to call it by name, `/dna:way-of-working`. **claude.ai**: upload
`way-of-working.zip` from the [latest release](https://github.com/ruinosus/dna/releases) in Settings › Capabilities ›
Skills (code execution on). **Claude API**: the same zip with the Skills API. **Other tools**: copy
`skills/way-of-working` where the tool reads skills; it needs Node.js 18 or later. **npm**: `npx @ruinosus/dna way-of-working <file>`.

## The file

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: WayOfWorking
metadata:
  name: Scrum team
lanes:
  - { id: product, name: Product, color: prod }
  - { id: team, name: Development team, color: tech }
roles:
  - { id: po, acronym: PO, name: Product Owner, lane: product }
  - { id: dev, acronym: DEV, name: Developers, lane: team }
phases:
  - { id: backlog, name: Backlog }
  - { id: sprint, name: Sprint }
stages:
  - id: refine
    name: Refine
    phase: backlog
    lane: team
    roles: [dev, po]
    question: Do we understand it well enough to size it?
    inputs:
      - from: item                       # an output of an earlier stage, by its id
    outputs:
      - { id: criteria, name: Acceptance criteria }
    metrics: ["% of items ready before planning"]
  # …
gates:
  - id: ready
    after: refine
    name: Ready for a sprint?
    approver: dev
    criteria: [{ kind: outputs, outputs: [criteria] }]
    on_fail: refine
    outputs:                             # what comes out of the gate
      - { id: ready-item, name: Item ready for a sprint }
```

The whole format is [`references/format.schema.json`](../../skills/way-of-working/references/format.schema.json); three complete
examples are in [`skills/way-of-working/examples/`](../../skills/way-of-working/examples) — four, one of them
([`initiative-portfolio`](../../skills/way-of-working/examples/initiative-portfolio.way.yaml)) with the whole thread.

## What is inside

```
skills/way-of-working/
  SKILL.md                  what Claude follows: read, draft, check, ask once, make, and the way back
  references/               the format, what the words mean, what the check points out, how to ask
  examples/                 four fictional ways of working (feature delivery, Scrum, service desk, initiative portfolio)
  scripts/build.mjs         checks a .way.yaml and makes the map, the workbook and the explainer; reads a workbook back
  scripts/engine.mjs        the rules (generated)
  assets/map.html           the map page (generated)
  assets/explainer.html        the explainer page — visual-explainer's player (generated)
```

Node.js 18 or later and nothing else. Chrome, Chromium or Edge, when installed, checks the explainer's drawing.

## Not yet

It maps how the work **should** go. It does not track items moving through the stages, nor decide a gate.


## From an OKF bundle

`node skills/way-of-working/scripts/okf-read.mjs <folder> [--json]` reads an [OKF](https://github.com/GoogleCloudPlatform/open-knowledge-format)
bundle as material: each concept with its type, trust (human-reviewed, machine-confirmed, unverified), staleness and
sources, and its text inside a data fence — someone else's content, never instructions. Nothing in the bundle is run.
The recipe written from it cites the concepts as `okf:<path>`.

## Develop

`tools/` builds the generated files from the way engine and visual-explainer (`tools/sources.json`, see
`sources.example.json`), checks the examples end to end and makes the gallery:

```
npm install       # at the repository root: the six skills are npm workspaces
npm run assets -w dev/way-of-working/tools   # scripts/engine.mjs, assets/map.html, assets/explainer.html
npm run check -w dev/way-of-working/tools    # every example: map, workbook (and back), explainer; a broken file says its line
npm run site -w dev/way-of-working/tools     # docs/: the gallery
npm run zip -w dev/way-of-working/tools      # dist/way-of-working.zip
claude plugin eval . --ablation none --allow-tools Bash Write Edit   # the evals in evals/
```

## License

MIT. The explainer's player is [visual-explainer](https://github.com/ruinosus/dna) (MIT; Rough.js MIT; Caveat and Shantell
Sans, SIL Open Font License).
