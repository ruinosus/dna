# Changelog

## 2.2.0 — 2026-11-05

**The explainer** — words for work, not for school: the *lesson* is now the *explainer* (*explicação*), its *quiz* the
*knowledge check*, several explainers on one page a *collection* (not a *course*), and visual-explainer *explains* by
drawing (it no longer *teaches*). Everything you made before still opens.

- The drawing that explains is `kind explainer` (the default); the skills write `<id>.explainer.html` with
  `--explainer`, the solution's piece is `explainer:`, and the OKF concept is `explainer.md`, `type: Explainer`.
- The question at the end is `knowledge_check` (the field and the text line); several recipes built together make a
  collection, `{ "collection": "Title", "explainers": […] }`, with `--title "The collection"`. When it is for a
  training, a workshop or a talk, visual-explainer asks first.
- What you made before is still read: `kind lesson`, `quiz`, `--lesson`, `lesson:` in a solution, `{ course, lessons }`
  and `?lesson=n`, and `mountLesson` / `stillLesson` from `@ruinosus/visual-explainer/embed`.
- **`explainer.md` draws itself**: the OKF bundle carries the explainer's recipe in a ```` ```visual-explainer ````
  block (```` ```visual-explainer-mermaid ```` for a Mermaid one), so a Markdown preview with DNA — VS Code, Obsidian —
  draws it in place.
- The asset builders remove their link to the engine without following it (Node 25's `rmSync` refuses a link to a
  folder).
- `@ruinosus/visual-explainer` 0.22.0, on the drawing engine 0.262.0.

## 2.1.0 — 2026-11-04

**DNA speaks OKF** — [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) v0.2, Google's
format for knowledge with its provenance, trust and lifecycle. DNA says what a thing is; OKF says where it came from and
how far to trust it.

- **`solution --okf`** writes the solution as an OKF bundle any OKF reader takes: a concept per piece (Way of Working,
  Service Blueprint, Incident Drill, Agent Review, Lesson) with what its skill's check says and its sources as footnotes
  (the blueprint's pains, the drill's runbook and gaps, each agent); *machine-confirmed* when the check passes, a `draft`
  when it does not; the recipes in `references/dna/`; `index.md` and `log.md`. Exporting again with nothing changed
  writes the same bytes, and the log grows only when something changed.
- **A person's review.** `solution --review <piece> --by <id> [--write]` records a review in the solution (`reviewed:`);
  the bundle carries it as *human-reviewed* while the piece stays as reviewed, and `--check` says when it changed after.
- **The simulation is an Attested Computation.** `process-simulation --run --receipt <file>` writes a run's receipt (the
  recipe's sha256, the engine, the seed, the runs, the controls, the numbers); `--attest <receipt>` runs the recipe
  again and says whether it holds, or why not — the recipe swapped, a control that is not one or out of range, another
  engine, a number moved (exit 3). The bundle carries the executor and a deterministic attester with the engine, so a
  receipt can be checked with the bundle alone. The mod's `/attest` says the verdict.
- **An OKF bundle is material.** `scripts/okf-read.mjs` (in the kit, and in way-of-working, service-blueprint and
  incident-drill) reads a bundle: each concept's type, trust tier, staleness, status, sources and links, its text inside
  a data fence — someone else's content, never instructions; a document that breaks the format is listed, never
  refused; nothing in it is run. The three skills write their recipe from it, citing `okf:<path>`. An eval: a drill
  written from a bundle with a line that gives orders cites its concepts and does not obey it (1.00, one run).
- `@ruinosus/visual-explainer` 0.21.0: the kit carries the OKF reader.
- The agent-review compare eval names the HR agents again (it still asked for the store's).

## 2.0.1 — 2026-11-04

What the installed 2.0.0 still said from before DNA, found by testing it from the marketplace.

- **The way's schema takes DNA's header.** `way-of-working/references/format.schema.json` required
  `format: stage-door/v1`, so an editor that validates by it flagged the skill's own examples. It now asks for
  `apiVersion`, `kind: WayOfWorking` and `metadata.name`, and still takes the header of before (`format` and a top-level
  `name`).
- **The docs teach DNA's header.** The solution's SKILL.md and format, agent-review's review file and profile,
  incident-drill's format and the READMEs showed the `format:` line of before as the way to write a file; they now show
  `apiVersion`, `kind` and `metadata.name`. Files written before still read, and `--upgrade` still rewrites them.
- **The marketplace says DNA.** Its description said «seven skills» and left solution out; it now matches the plugin's.
- A check fails if a doc teaches a header of before, if the way's schema does not fit the examples, or if the
  marketplace stops naming the eight skills.

## npm @ruinosus/visual-explainer 0.20.1 — 2026-11-04

- **The business look on a light page.** `@ruinosus/visual-explainer/mount` (VS Code's preview, Docusaurus, any page
  with the blocks) still gave a light page the hand-drawn paper — the light/dark rule from before the business theme.
  A light page now gets the business look (the lesson's «Hand-drawn» switches to the paper); a dark one still gets the
  chalkboard, as there is no dark business look. The plugin is unchanged: the skills' player never passed a theme.

## 2.0.0 — 2026-11-04

**house-lights is now DNA — Domain Notation of Anything** (ruinosus/dna). The same eight skills, with plain names and
one notation.

- **The names.** Plugin `dna@dna`; npm `@ruinosus/dna` (the `dna` command) and `@ruinosus/visual-explainer` (the lesson
  package and the skills kit). Skills: visual-explainer (was chalk-talk), visual-pitch (back-of-napkin), way-of-working
  (gates-and-handoffs), service-blueprint, incident-drill (dress-rehearsal), agent-review (cast-list),
  process-simulation (box-office), solution (opening-night). The mod's commands: `/simulate`, `/simulation-preview`,
  `/compare-agents` and `/check-solution` (were `/sim`, `/sim-preview`, `/cast`, `/solution` — a command named like a
  skill is refused, and `/agents` is Claude Code's own); `/drill`, `/lenses` and the previews stay.
- **apiVersion and kind.** A recipe says what it is under DNA's header — `apiVersion: github.com/ruinosus/dna/v1`,
  `kind: WayOfWorking | ServiceBlueprint | IncidentDrill | AgentStandard | AgentReview | Solution` and the name in
  `metadata.name`. **Every file written before still reads**: the `format:` lines of before are read as they were.
  `--upgrade [--write]` in each skill rewrites a file's header, keeping the rest of the text, and refuses when the file
  would not read the same. New files — lenses, a new cast file, the examples and the accelerators — are written under
  DNA's header.
- **The business look, by default.** visual-explainer and visual-pitch — and every lesson the other skills make —
  draw with straight strokes, IBM Plex Sans, a white page, a sober palette and the props as line icons; the pages around
  them in the same face. `theme paper` (hand-drawn) and `theme chalkboard` stay, and «Hand-drawn» switches any lesson.
  The site follows.
- **Business examples.** agent-review's six example agents are an HR self-service after Microsoft's Employee
  Self-Service sample (Workday, the HR SharePoint, an admission MCP server), one for one with the store they replace;
  an HR help desk instead of the café; an expense claim and joining the company instead of the return and the gym;
  an HR self-service business case and HR tickets instead of the pharmacy and the returns; the reference lessons and
  the gallery of visual-explainer in the same vein. No client's data or names.
- **Fixes on the way:** process-simulation's page had no charset — opened from a file, its accents broke and a
  Portuguese recipe stopped parsing (every page is checked for it now); a card too short for its lines is refused by
  the contract with the height it needs (the page waited for it forever); a mod command named like a skill is refused
  by Claude Code, and took the others with it (they register one by one now).
- **Moving from house-lights:** `/plugin marketplace add ruinosus/dna`, `/plugin install dna@dna`, then
  `/plugin uninstall house-lights@house-lights`. The npm packages `house-lights` and `chalk-talk` point to the new ones.

## 1.17.0 — 2026-11-04

The eighth skill: **opening-night**, a process put together as one solution.

- **`<id>.solution.yaml`** (`opening-night/v1`) names the pieces of one process, beside it: the way of working, the
  simulation, the journey, the drill, the Copilot Studio agents (with the team's profile), the lesson. `--check` checks
  each piece with its own skill (exit 4 with that skill's messages when one fails or is missing) and says which lens
  fell behind the way, by its `# from: <way>@<version>`, with the command that makes it again. A piece with no
  `# from:` is written by hand and kept as it is.
- **The page** (`<id>.solution.html`): one offline file, a summary — each piece, the question it answers, where it
  stands — and a tab per piece, each drawn by its own skill.
- **Solution accelerators** to start from, `--list` and `--new <name> <folder>`: `employee-self-service` (an assistant
  with Workday, after Microsoft's public sample), `service-desk` (a customer service desk with its six fictional
  Copilot Studio agents and the team's profile) and `assistant-delivery` (delivering an assistant, with the gate that
  sends it back to be built again). Their gallery is on the site.
- **`/solution <file>`** in the mod: the pieces in a pane, and a button that makes a lens again from the way — at a
  second press, since it may have been edited by hand. A `.solution.yaml` that breaks its format is refused when
  written.
- **gates-and-handoffs `--lens blueprint`**: the moment after a gate shows what comes out of the gate, so the wait is
  never empty-handed.
- `npx house-lights opening-night`; the mod's tests are 33.

## 1.16.0 — 2026-11-04

One way of working, seen by the other skills.

- **`--lens sim|blueprint|drill`** in gates-and-handoffs writes a `.way.yaml` as another skill's recipe: a box-office
  simulation (the stages and gates in their order, the roles as teams, each gate's «no» going back to its `on_fail`), a
  service blueprint (a moment per stage, the lead on stage, a wait after each gate, each moment pointing at its stage)
  and a dress-rehearsal drill on one gate (`--gate`). What the way does not have is a bet, marked `# bet:` and counted.
  `--write` writes it beside the way and checks it with its own skill; one that differs is written over only with
  `--force`. The first line says the way and its version (`# from: <id>.way.yaml@<sha256 8>`).
- **Loops in box-office.** A route may send an item back to an earlier step — rework, a review that returns it — as
  long as every step can still reach an end (an error says which cannot). The flow counts every visit (it settles to a
  fixed point), a way out with no share is a warning, and the page and the preview draw the return under the flow.
- **`/lenses <file.way.yaml>`** in the mod: the three lenses in a pane, how many bets each has, a button to write each
  beside the way (asking again before writing over one that differs) and the command to see it. When a `.way.yaml` is
  written or edited and a lens beside it came from an earlier version, a toast says so.
- All the examples of gates-and-handoffs pass through the three lenses in the checks; the mod's tests are 31.

## 1.15.0 — 2026-11-04

- **`/cast --profile <file>`** compares the agents with the team's profile, as `--all --profile` does: the rules, the
  roles, the threshold. With none given, the only profile (`format: cast-list/profile-v1`) in the agents' folder or the
  one above it is used, and the reply says which; with two or more, it lists them and asks. An agent edited after
  compares again with the same profile.
- **The `.sim` preview's controls:** a −/+ beside each `knob` runs the recipe again with the new value (a tenth of the
  range, 5 points for a share, never past it) and shows each metric's median and p10 to p90 under the flow; «Back to the
  recipe» runs it with its own values. The numbers stay with the recipe until it is written again.
- `/sim` and the preview share one run (`runMetrics`); the mod's tests are 27.

## 1.14.1 — 2026-11-04

- **The mod's commands take a path typed with `~`** (`/drill ~/drills/checkout.drill.yaml`): no shell expands it for
  a command, so `/drill`, `/cast`, `/way-preview`, `/blueprint-preview`, `/sim` and `/sim-preview` read it as the home
  folder. A file or folder that is not there is said plainly, instead of Node's error.
- **No doubled name** in the commands' replies: Claude Code already says «house-lights:».

## 1.14.0 — 2026-11-04

The incident drill, played beside the chat.

- **`/drill <file.drill.yaml> [--lang pt]`** plays a dress-rehearsal drill in a pane: the clock, the impact, who is in
  the room, the scene and its injects, the choices as buttons (one the room cannot do says what it needs), a button to
  call each role not in the room; at the end the debrief — the numbers, what happened, what the runbook did not say —
  and buttons to save it beside the drill (`<id>.debrief.md`) or play again. The game stays in the session's state:
  `/drill` with no file opens it again where it was.
- **One game, not two:** the pane plays with dress-rehearsal's own `src/play.ts`, built into `hooks/drill/play.js` (pure,
  no Node); the checks play all 15 paths of the example with it and with the skill's engine, to the same debrief.
- **`--check --json`** in dress-rehearsal: the drill as read, what to look at and the runbook's passages, as one JSON
  document.
- The mod's 23 tests run in `npm run check`.

## 1.13.0 — 2026-11-04

The mod shows what was written, beside the chat.

- **The recipes' preview.** A `.way.yaml` or `.blueprint.yaml` that passes the guard opens a pane: a way of working as
  its stages in lanes, phase by phase, each gate under its stage with who approves on a line of its own; a service
  blueprint as its moments — what the customer lives, how they feel (1 to 5), the pains, on stage, backstage and the
  systems. An SVG in the desktop app, VS Code and the phone, text in the terminal, with what to look at and the EN/PT
  switch. `/way-preview <file>` and `/blueprint-preview <file>` show another. Long names wrap instead of being cut.
- **`/cast <agents-folder> [--lang pt]`.** cast-list's comparison (`--check`, nothing written) in a pane: the summary and
  «to look at», a button per group. After it, an agent's `.mcs.yml` written or edited in that folder is compared again
  (about 0.1 s) and a toast says what came to look at or went away. The edit is never refused.
- **`--check --json`** in gates-and-handoffs and service-blueprint: the recipe as read and what to look at, as one JSON
  document — what the preview draws, from the skill's own reading.
- The mod's 20 tests run in `npm run check`.

## 1.12.0 — 2026-11-04

The mod checks every recipe as Claude writes it, and keeps the names of your private list out of what is published.

- **The recipes' guard.** A `.way.yaml`, `.blueprint.yaml`, `.drill.yaml`, `.chalk` or chalk-talk `.json` that Claude
  writes or edits is checked first by its skill's own script (its `--check`, or chalk-talk's build with no review), on
  a copy in a folder of its own, and refused with the script's messages — the line and what to write — when it breaks
  its format. A `.json` is checked only when it is a chalk-talk recipe. If the check cannot run, the write goes through.
- **The names' guard.** In a repository that runs the names audit before it publishes (an `audit` script calling
  `audit.mjs`, as house-lights does), a write whose new text has a name of `~/.config/skill-kit/audit.txt` is refused,
  saying which pattern and on which line — never repeating the text. An edit is checked on what it adds, so removing
  a name is never blocked. With no list, or anywhere else, it does nothing. `/names` says what it watches.
- **The guards fail open in their own code**, box-office's too: a hook that threw would stop the plugin's other
  guards. The mod's 16 tests run in `npm run check` (dev/house-lights).

## 1.11.2 — 2026-11-04

- gates-and-handoffs: **the gate's card no longer spills** in the side panel of a wide screen. Each approval's
  condition («sempre», «se mexe com dado de colaborador») goes on its own line under the role, and long values wrap
  inside the card; checked in a browser at the panel's 300 px.
- Developing: since 1.11.1, after a pull or a branch switch run `npm run assets` (and `npm run site` for docs/): git
  removes the built files it no longer keeps.

## 1.11.1 — 2026-11-04

- **A lighter install.** What Claude Code and the Copilot clone to install the plugin went from 56 MB to about 17 MB:
  the site moved to the `gh-pages` branch (`npm run site`, then `npm run pages`), and the chalk-talk npm package's
  built files are made by `npm run assets` instead of kept in git (its `prepack` checks they are there). The install
  commands do not change.
- The chalk-talk gallery's own recipes and hand-made pictures live in `dev/chalk-talk/gallery/`; the READMEs show the
  pictures from the published site.
- box-office: the preview pane says its own words in Portuguese too («chega», «por hora», «receita válida», «Rode /sim
  para ver os números»), and `--run` no longer ends a recipe with no control in a stray «·».

## 1.11.0 — 2026-11-04

The seventh skill: **box-office**, a process you can watch and ask «what if».

- **A `.sim` recipe of 10 to 25 lines** — what arrives, the steps, who handles them, the routes, the costs, the
  controls, the scenarios and the metrics — becomes `<id>.box-office.html`: one page that opens offline, drawing the
  flow and animating the items, with a slider for every control, the p10 to p90 range of seeded runs in the
  background and the scenarios side by side. In English or Portuguese, with the screen switching between EN and PT.
- **`scripts/build.mjs`** checks a recipe (`--check`: each error with what to do), runs it (`--run`, with `--set`),
  translates it (`--to pt-BR|en`, round trip exact) and makes the page, opening on the recipe given; also
  `npx house-lights box-office`.
- **The example** follows the scenarios of Microsoft's public Employee Self-Service sample with Workday (MIT): the
  vacation balance and profile read from Workday, time off approved by the manager, policy questions answered or sent
  to an HR partner. Its numbers are made up, and the recipe says so.
- **The first mod of house-lights** (Claude Code 2.1.287 or later): every `.sim` Claude writes or edits is checked
  first and refused with the validator's messages when it has errors; `/sim` runs a recipe at once; `/sim-preview`
  opens a pane with its flow. Elsewhere the skill works without it.
- The page carries its fonts (Bricolage Grotesque and IBM Plex, SIL Open Font License) and loads nothing from the
  internet; it says its version.

cast-list, from reading Microsoft's Employee Self-Service sample (`dev/cast-list/tools/prova-ess.mjs`):

- **Workday records with `@` keys** (`@Descriptor`, `@type`, `@Primary`), written by Copilot Studio with no quotes,
  are read: plain YAML refuses them, and 5 of the sample's topics were «not understood». The lines stay the same.
- **A test set of the Evaluate tab** (prompts and expected answers, not yet run) is told as such by `--evals` — import
  it, run it and export the results — instead of «its name says nobody in the folder».

## 1.10.0 — 2026-11-04

cast-list, the diagrams: what was read, in plain Mermaid.

- **`--diagrams`** (also in `--all`) writes `<id>.diagrams.md` and `<id>.diagrams/*.mmd`: the cast as Mermaid, for the
  team's docs — it shows on GitHub, in a wiki, a README or VS Code with nothing of ours. The document has the summary,
  «to look at» in words and each diagram in a ```mermaid block with a sentence on what it shows.
- **The diagrams come from the stage's data**, so the two never disagree: the **topology** (the customer, the
  orchestrators, the specialists by type, the flows and the systems, with what is missing in each call and the topic
  starts), a **sequence per call** of the orchestrator (with ⚠ where it breaks and the routing description quoted), a
  **lens per pattern** (who follows it, who is to look at, who is off, in words and colour) and the **anatomy of each
  type** (its patterns and who is off each one). In Portuguese or English, by `--lang`.
- **They draw in chalk-talk too:** each `.mmd` carries `%% title`, `%% # chapter` and `%% > narration`, so chalk-talk
  and back-of-napkin draw it as a lesson or present it.
- The checks render every diagram of the example with Mermaid itself (the official package, only in the checks; it is
  not in the skill nor in the npm package) and build the topology and a scene with chalk-talk.

## 1.9.6 — 2026-11-03

- **What a run makes says its version:** the foot of the map, the RH and the stage («cast-list 1.9.6»), their
  generator tag, and the cast file (`# Written by cast-list 1.9.6.`, renewed on every run), so two runs can be told
  apart.
- **A topic that begins a connected agent** (`<schema>.InvokeConnectedAgentTaskAction.<Name>`) is checked against
  the agent's actions — in `actions/`, `topics/`, or a file of `agents/`, where the extension clones them — and not
  reported as a topic not found. Any `<schema>.<type>.<Name>` other than a topic is read the same way.

## 1.9.5 — 2026-11-03

cast-list, the second run on a real cast (22 files «not understood», down from 96).

- **Flows whose `jsonFileName` is a path** (`workflows/<folder>/workflow.json`, as the extension writes it) are read: the
  file was looked for by the whole path. The rest of those flows' names, connectors and callers come back with them.
- **A topic that begins an action** (`<schema>.action.<Name>`) is checked against the agent's actions, not its topics.
  One not found is named in full, so an action of another agent's prefix (copied from another agent) shows as such:
  «Chama a ação (não encontrada) …».
- **A call without a prefix keeps its whole name:** it showed only its last letter («Chama o tópico (não encontrado) s»).
- **The cast cards no longer spill:** a long path or a GUID wraps inside its card, and a file «not understood» twice
  for the same reason shows once, with ×2.

## 1.9.4 — 2026-11-03

cast-list on agents cloned by the VS Code extension on Windows, after a run on a real cast left 96 files «not
understood».

- **Flows are read again:** a `workflow.json` saved with a byte-order mark (Windows) did not parse, so every flow was
  lost — its name, its connectors and operations, who calls it. Every file now drops the mark before it is read. The
  name comes from `name` in `metadata.yml`, and a folder ending in a whole GUID gives the flow's short name.
- **Uploaded knowledge counts:** each `knowledge/files/*.mcs.yml` (only its metadata) is a knowledge source
  («Conhecimento em arquivo enviado»); the document beside it and the agent's `icon.png` are not read and no longer
  show as «not understood».
- **`connectionreferences.mcs.yml` without a kind** is known by its name, as cloned, so the access review has its
  connections.
- **«Not understood» says why** in the cast card too, as the sheet does (`a telemetry event whose name is a formula`).
- The example agents are cloned the same way: flows with a byte-order mark and a GUID folder, a real `metadata.yml`,
  connection references without a kind, an icon each.

## 1.9.3 — 2026-11-03

- **The résumé says where each fact came from:** team, owner, hiring, publishing and environment carry their source
  (`inventario.csv › linha 6`) in small letters under the value, as the sheet does beside it.
- **The stage's arrow labels never sit on a node,** with a lens or without; with a lens, only the arrows that touch
  someone it lights say something.
- **Short names in the follow spot too:** its buttons and its steps say «O orquestrador encaminha para Frete». One rule
  for the shared part of the names (`shortNames`) serves the stage, its scenes and the RH.

## 1.9.2 — 2026-11-03

- **The RH's résumé has two views:** as a résumé — the paper one of the prototype, with a face, the name, the post and
  the stamp on top, the facts in two columns and the sources at its foot — and as the sheet, every field with its
  source beside it. It opens as a résumé; one click turns it.

## 1.9.1 — 2026-11-03

cast-list's RH and stage, after a test in claude.ai.

- **The RH's org chart** shows one of two types once, in its first, with «also orientação»; the staff board, the org
  chart and the stage leave out the part of the names every one shares («Bodega Azul - »), and the one not in the
  folder is no longer cut.
- **The stage:** a lens closes the scene and a scene turns the lens off; the follow spot is the size of the node; the
  caption sits below the stage, never over it; knowledge sources are on stage and in the scenes («Consulta
  «Conhecimento no SharePoint»»).
- **Connectors by name:** when the files give none (a flow's connection names only the API), a common Microsoft
  connector goes by Microsoft's name — `shared_commondataserviceforapps` is «Microsoft Dataverse».
- **The post's requirements:** a fact whose name is already a sentence is said as it is («Recebe «X» do
  orquestrador»), not inside «Tem «…»».
- **The example evaluations** are named in kebab-case (`evaluate-bodega-azul-pedidos-2026-10-30.csv`); the name the
  Evaluate tab gives, with spaces, reads the same.

## 1.9.0 — 2026-11-03

cast-list reads the evaluations and reviews the access.

- **`--evals <folder>`** reads the exports of Copilot Studio's Evaluate tab («Evaluate <name> <date>.csv»): who is
  named by the file, a row passes when every method passes, each method counted. **The counts only:** what was asked,
  answered and explained is the client's conversation and never reaches an output. The résumé gets «Certifications»,
  the staff board «with no evaluation», and who has one gets `eval:run`, so a rule `has: "eval:*"` asks for it. A file
  that names nobody, or is not an export, is told and left out.
- **The review of access:** within each type of two or more, a connector, an MCP server or what a flow reaches that
  only one has is asked about on the résumé and the stage's card — does the post need it? With a decision `rejected`
  on that key in the type's scope, it becomes a cleanup item of the plan.
- The examples get two exports of the Evaluate tab (`examples/avaliacoes/`), written by the fixtures' generator.

## 1.8.0 — 2026-11-03

cast-list puts the cast on a stage.

- **`--plot` (in `--all` too) writes `<id>.plot.html`:** the light plot, to show in a meeting. The customer, the
  orchestrators, the specialists by type, the flows (one node however many share one) and the systems they reach, in
  columns; the same run gives the same stage.
  - **The traffic:** dots along the arrows, as many as the log of each one's topic starts in the export; the arrows
    into flows and systems are structure, never a measured volume; one with no line in the telemetry has a dashed
    arrow and «no telemetry». With reduced motion, nothing moves.
  - **The arrows say what is wrong:** «NO history · NO «Category»» in red, «routed by «Coupons.»» in amber, «returns
    nothing», «calls it, but it is not in the folder»; a flow nobody calls, and what only it reaches, dashed.
  - **Lenses:** the accepted patterns and the first ones someone is off, then Contract, Telemetry and Unused — who
    follows lights green, who is off blinks red, what is to decide shows amber.
  - **The follow spot:** one scene per call of the orchestrator; ← → walk it, space plays it, Esc leaves; it stops
    where the call breaks.
  - **The actor's card:** the fingerprint of its instructions (shared blocks, a variation, its own text) and what it
    meets of its post, with its résumé a link away (the RH opens at `#<id>`).
- **The map** links to the stage when the same run wrote it.

## 1.7.0 — 2026-11-03

cast-list writes the RH of the cast.

- **`--playbill` (in `--all` too) writes `<id>.playbill.html`:** the same cast as people, for whoever thinks in HR
  terms. Everything comes from the files, the telemetry and the tables people gave; a field nothing says stays empty.
  - **The staff board:** on the staff, being hired (called and not in the folder, or in another environment), with no
    owner and never published (with the inventory), with a development plan, in good standing — each with the names.
  - **The org chart** by type, and **the post** of each role and type: the accepted patterns and the profile's rules,
    as requirements; with no decision yet, a proposal.
  - **A résumé each:** the first sentence of its instructions, its manager, team, owner, hiring and publishing dates,
    tools, conduct, goal, and the performance from the telemetry (topic starts, errors logged, what did not fire).
  - **The development plan (PDI):** what «to look at» says about that one alone, as actions — one item per fact, the
    inputs the orchestrator does not pass in one call as one. A solo, a type with one and a marker set in ways across
    the cast are the team's call, not anyone's plan. `references/playbill.md` says how each part is read.
- **The workbook** gets the Staff and PDI sheets; **the map** links to the RH when the same run wrote it.
- **Two keys for who answers for it:** the team spreadsheet's «Dono», «Equipe», «Squad» give `declared:team`; only
  the inventory's `Owner` gives `declared:owner` (until 1.6, «Dono» was the owner).

## 1.6.0 — 2026-11-03

cast-list's «to look at» comes in groups.

- **Groups, each with how many:** Contradictions · Contract and telemetry · Off pattern · Rules · Only one has it ·
  Unused · Not understood — in the command's output (a `▸` line per group; every finding keeps its `!` line), at the
  top of the map and in the workbook's summary. One list decides them, so the three always agree.
- **The map folds «Only one has it» and «Unused» at first:** they are many and rarely urgent; a click opens them. A rule
  not met now comes after what is off a pattern, with its own group.

## 1.5.1 — 2026-11-03

- **cast-list's description fits claude.ai.** It had 1156 characters and claude.ai keeps 1024, so the plugin synced
  with a warning and a cut description. It now has 1017, with the same uses and examples.
- **Every skill's check reads its SKILL.md.** The name, the 1024 characters of the description and the 500 lines were
  checked only for chalk-talk and back-of-napkin; cast-list, dress-rehearsal, gates-and-handoffs and service-blueprint
  check them too.

## 1.5.0 — 2026-11-03

cast-list reads the telemetry by name, what really fires, and what a spreadsheet says about the agents.

- **The telemetry by name.** Each `LogCustomTelemetryEvent` is a fact by its **form** — the name with the agent's own
  name taken out, so «BodegaPedidos_OnError» and «BodegaFrete_OnError» are one event — and each field of its record is
  a fact too. The event is part of logging telemetry and the field part of the event: a field missing is told
  («logs «‹name›_OnError» without «ConversationId»»), and neither is ever a solo. Two spellings that differ only in case
  or separators count as the most common one, and the other is asked about: «the same event?». A name or a record made
  by a formula is not guessed.
- **What fires.** `--telemetry <export>` reads the result of one query in Application Insights
  (`references/telemetry.md`, ready to copy): an event in the YAML that did not fire in the period, and an agent with no
  line at all (is it connected?). Nothing goes over the network; only the agent, the event and the times are read.
- **Declared from a spreadsheet, with no model.** `--declared <table>` reads the Power Platform admin center's
  inventory download or the team's own list (`.csv` with `,` or `;`, or `.xlsx`): the agent's column is found by its
  values, every other column becomes a declared fact with the file and the line, listed with keys and written with
  `--take`. `Dono`/`Owner` is the owner, `KPI`/`Indicador` the KPI; the inventory's apps and flows are left out, and a
  row of an agent not in the folder is listed.
- A **Telemetry** sheet; each card of the map lists its events and the times they fired; the lesson puts a spelling in
  «what to decide» and what did not fire in «what is missing». An eval (`cast-list-telemetry-pt`, 2/2). The example agents
  and three example tables show all of it.

## 1.4.0 — 2026-11-02

cast-list reads what the orchestrator passes each agent, what each flow calls, and what nobody uses.

- **The orchestrator's contract.** What each connected-agent action passes — the conversation history, the inputs,
  the routing description — is a fact of the agent it calls, so «1 specialist does not receive the conversation
  history from the orchestrator» is an ordinary off-pattern. Its own findings: a call to an agent not in the folder, a
  specialist no orchestrator calls, a routing description under 80 characters. The map's orchestrator card and the
  workbook's **Routing** sheet have a row per call.
- **Inside the flows.** `workflows/<Name>-<id>/` (`metadata.yml` and `workflow.json`, the definition in
  `properties.definition` or `definition`) is read, scopes, conditions, switches and loops included: the connectors,
  operations and HTTP hosts a flow calls, another flow, and whether it answers the agent. A flow that returns nothing
  is told; the Cast tab draws each chain, agent → flow → system. A JSON that does not read goes to «not understood».
  Neither the flow's logic nor its secrets are read.
- **What nobody uses, and what is switched off.** A topic nobody can reach, a tool the model cannot choose, a global
  variable no file names, a flow no node calls, a node with `disabled: true`, a component with `state: Inactive`:
  «remove or switch on?», in a new **Unused** tab and sheet, never a pattern nor a solo. A switched-off node is not a
  fact: a disabled telemetry node is no telemetry.
- The lesson says the contract in «what is missing» and what nobody uses in «what to decide». An eval
  (`cast-list-contract-pt`, 2/2). The example agents show all of it, and the earlier ones are unchanged.

## 1.3.0 — 2026-11-02

cast-list reads the text of the instructions, and compares by type of agent.

- **The text.** The instructions and the descriptions the model reads are cut into blocks. A block two agents or more
  share is a fact; a copy that lost a line is a **variation** (half of the smaller one in the other), and the map
  shows the words that went and came. A block keeps its id across small edits (the cast file keeps it). It compares
  text, not meaning; copied, test and per-language topics are left out.
- **What the team looks for**, in the profile: **markers** — a regular expression and the value it captures («at most
  3 bullets») — so a rule written in different ways by a role («unify?») or twice in one agent («which one holds?»)
  is told; the domain of each link and an e-mail are found with no marker; and the **official blocks** the team pastes
  everywhere, checked on every agent with or without a majority.
- **Types** of specialist (transaction, guidance, triage…), from what each one's YAML and text show — one may be of
  two: patterns are also found within each type (scope `type:<id>`), a pattern of a type never blames who is not of
  it, and a type with one agent is told. The matrix groups its columns by type (a type filter; one of two types in
  both), the workbook has the types and a Text sheet, the lesson draws the cast by type.
- **The text against the setup:** a rule with `when` and `not` — «asks for the knowledge alone» with the model's
  general knowledge on. Four settings are read now: general knowledge, content moderation, semantic search, web
  browsing.
- An eval for the text (`cast-list-text-pt`, 2/2). The example agents and profile show all of it.

## 1.2.1 — 2026-11-02

cast-list, finished after its first run in the cloud.

- **One fact, asked once.** A topic that calls another (the fallback leading to escalation) is now known by what the
  called topic is for — `reaches:OnEscalate` — and is a part of that fact, not a pattern of its own: an agent with no
  escalation is off once (not also for «its fallback does not lead there»), the fact's decision covers its part, and an
  agent that has the escalation topic but whose fallback never reaches it is still found, as the part. The map shows
  the part right under its fact and in its detail.
- **Readable names.** Connectors, their operations, MCP servers and the agents an orchestrator calls are named as the
  files name them — «Conector Office 365 Outlook», «Chama Bodega Azul - Cupons» — on the map, the workbook, the lesson
  and «to look at»; the technical key stays in the Key column and the detail.
- **A lesson you can read from the back of the room.** What repeats and what to decide show the five that matter most
  in bigger letters, and «and N more on the map» for the rest; contradictions come first in what to decide.

## 1.2.0 — 2026-11-02

- **cast-list, the sixth skill: Copilot Studio agents compared.** Point it at the folders the VS Code extension clones
  and it says what most agents do (a pattern — the platform's when the orchestrator has it too, the specialists'
  otherwise), who is off a pattern, what only one has (innovation or debt), the team's rules not met, and what a
  handoff or the backlog says that the YAML does not — with the file and line behind each finding. A map that opens
  offline (filters by role and focus area, a click shows the evidence), a workbook to decide in (Decision column,
  Declared sheet, read back with `--from` / `--take`), a lesson that draws the cast, and a cast file that keeps what
  was decided, so the next run checks every agent against the accepted patterns. It runs on Node alone — no model, no
  install, no network — so it fits a client's locked-down machine; with a model, `--facts` is the way in. A child
  agent's facts are the child's; a file it cannot read is told and never stops it. The Copilot Studio schema and its
  reader are inside (`vendor/microsoft`, MIT), to tell a real kind from a made-up one; 8 of Microsoft's 15 reference
  patterns are recognised in the YAML. `npx house-lights cast-list agents/ --all`.

## 1.1.0 — 2026-11-02

- **gates-and-handoffs: more than one approves, or only sometimes.** A gate lists its `approvals` —
  `[{ by: tl }, { by: seg, when: change to payments }]` — all of them needed; `when` is the condition as people say it.
  `approver: tl` stays the shorthand of one, so every file made before reads and writes back the same. A second gate
  after the same stage is still refused, and now says to use `approvals`. The map shows «+ SEG if change to payments»
  under the gate and lists who approves in its detail; the workbook has a row per approval, a «When» column (only when
  some approval has a condition), «A (if …)» in the RACI and a checklist item that may not apply; the lesson says it.
  As the market does it (Azure DevOps, GitLab, ServiceNow, ITIL): one decision, a list of approvals, the condition on
  the approval.
- The engine is the hubs Ways engine 0.259.0.

## 1.0.1 — 2026-11-02

What the first run of all five in the cloud found.

- **PowerPoint (back-of-napkin, chalk-talk):** a slide's title is at the title placeholder's index 0, as PowerPoint
  numbers it: python-pptx's `slide.shapes.title`, the outline and screen readers find it (pptxgenjs numbered it 100).
  The build checks it the same way.
- **The words on screen:** the list of a course's lessons is labelled in the recipe's language too (it said
  «Lessons»); a check makes sure a pt lesson has no English word on screen.
- **dress-rehearsal:** «escalar a instância» is scaling up, not escalating: only «escalar» to someone (para, ao, à…),
  «escalar o incidente» or «escalar» alone asks «escalar para quem?». A choice can cite a numbered step under a
  heading («Passos 4»), and the game shows that step; citing only the heading of a list of steps asks which one.
- **service-blueprint:** with no `feels` at all, the «Sente» lane says «ninguém disse como o cliente se sente» instead of a
  flat red line; a moment nobody said it of gets no point on the line.
- The npm package `chalk-talk` 0.19.1 carries the player and PowerPoint fixes.

## 1.0.0 — 2026-11-01

The five skills become one plugin, **house-lights**, in one repository.

- **One install:** `/plugin install house-lights@house-lights` brings chalk-talk, back-of-napkin, dress-rehearsal,
  gates-and-handoffs and service-blueprint.
- **Two new names:** stage-door is **gates-and-handoffs**, front-of-house is **service-blueprint**. The file formats
  keep their ids (`stage-door/v1`, `front-of-house/v1`): every file made before still opens.
- **One command:** `npx house-lights <skill> <file>`, with each skill's own options and exit codes. The packages
  `back-of-napkin`, `stage-door`, `front-of-house` and `dress-rehearsal` move to it; `chalk-talk` stays the engine's
  package.
- **The engine of chalk-talk 0.18.1 everywhere:** dress-rehearsal, gates-and-handoffs and service-blueprint drew
  their lessons with the engine of 0.14.1; now every skill takes it from this repository, in the same commit.
- One gallery: https://ruinosus.github.io/house-lights/, with a page per skill.
- The npm package `chalk-talk` 0.19.0: the same engine as 0.18.1, now built in this repository.

Before 1.0.0, each skill's history is in `dev/<skill>/CHANGELOG.md` and its tags are `<skill>-v<version>`.
