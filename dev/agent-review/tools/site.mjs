// The GitHub Pages gallery (docs/agent-review/): the example agents of a made-up shop compared — the map, the workbook,
// the lesson and the cast file (with the demo's declared facts and decision) in docs/agent-review/examples/; pictures of
// the map and the lesson (docs/agent-review/images/, a headless browser in the light theme); and its index.html. The
// example runs with the example export of Application Insights, so the map shows what fired. Run
// after npm run assets.
import { execFileSync } from 'node:child_process'
import { copyFileSync, cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { browser, runPages } from '../../../skills/agent-review/scripts/browser.mjs'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..') // the dna repository
const skill = join(repo, 'skills/agent-review')
const docs = join(repo, 'docs/agent-review')
if (!browser()) throw new Error('No Chrome, Chromium or Edge: the pictures need one (set CHROME_PATH).')
const ID = 'bodega-azul'
for (const d of ['examples', 'images']) rmSync(join(docs, d), { recursive: true, force: true })
mkdirSync(join(docs, 'examples'), { recursive: true })
mkdirSync(join(docs, 'images'), { recursive: true })
// the folder's name is the files' name: the example agents, copied under it
const work = mkdtempSync(join(tmpdir(), 'agent-review-site-'))
cpSync(join(skill, 'examples/agents'), join(work, ID), { recursive: true })
copyFileSync(join(skill, 'examples/demo.cast.yaml'), join(docs, 'examples', `${ID}.cast.yaml`))
// the inventory and the team spreadsheet taken, so the RH has owners, teams and goals
execFileSync(process.execPath, [join(skill, 'scripts/build.mjs'), join(work, ID), '--declared', join(skill, 'examples/inventario.csv'), '--declared', join(skill, 'examples/equipe.csv'), '--take', 'all', '--lang', 'pt', '--out', join(docs, 'examples')], { stdio: 'ignore' })
execFileSync(process.execPath, [join(skill, 'scripts/build.mjs'), join(work, ID), '--all', '--lang', 'pt', '--profile', join(skill, 'examples/profile.cast.yaml'), '--telemetry', join(skill, 'examples/telemetria.csv'), '--evals', join(skill, 'examples/avaliacoes'), '--out', join(docs, 'examples')], { stdio: 'ignore' })
rmSync(work, { recursive: true, force: true })
// The pictures, in the light theme, taken by the kit's browser over the DevTools pipe.
const shots = [
  { file: join(docs, 'examples', `${ID}.html`), mode: '', shot: { width: 1440, height: 900, scheme: 'light' }, png: join(docs, 'images', `${ID}-map.png`) },
  { file: join(docs, 'examples', `${ID}.plot.html`), mode: '', shot: { width: 1500, height: 860, scheme: 'light' }, png: join(docs, 'images', `${ID}-stage.png`) },
  { file: join(docs, 'examples', `${ID}.playbill.html`), mode: '', shot: { width: 1400, height: 1000, scheme: 'light' }, png: join(docs, 'images', `${ID}-rh.png`) },
  { file: join(docs, 'examples', `${ID}.lesson.html`), mode: 'still', shot: { width: 1100, height: 640, scheme: 'light' }, png: join(docs, 'images', `${ID}-lesson.png`) },
]
const { results } = await runPages(shots, { timeout: 60 })
shots.forEach(({ png }, k) => {
  if (!results[k]?.png) throw new Error(`${png}: the picture failed (${results[k]?.error ?? 'no picture'})`)
  writeFileSync(png, Buffer.from(results[k].png.split(',')[1], 'base64'))
})
writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>agent-review</title>
<meta name="description" content="Copilot Studio agents compared: what repeats, who is off the pattern, the orchestrator's contract, the telemetry and what nobody uses — with the file behind each finding. Node alone, no model.">
<style>
:root { --ink: #1d2330; --muted: #5f6878; --line: #e2e4e8; --page: #f6f6f3; --card: #fff; --accent: #2f5bea; --warm: #e3f3ea; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e8ebf0; --muted: #9aa3b2; --line: #313744; --page: #14171c; --card: #1d2129; --accent: #8fb0ff; --warm: #1c3328; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 36px; }
h1 { margin: 0; font-size: clamp(38px, 7vw, 60px); line-height: 1; letter-spacing: -0.02em; }
h1 span { background: var(--warm); padding: 0 .15em; border-radius: 6px; }
h2 { margin: 0 0 12px; font-size: 22px; }
p { margin: 0; }
a { color: var(--accent); }
.lead { font-size: 19px; max-width: 780px; }
.hero { display: grid; gap: 16px; }
.hero img, .card img { width: 100%; border-radius: 12px; border: 1px solid var(--line); }
.actions { display: flex; gap: 10px; flex-wrap: wrap; }
.button { display: inline-block; padding: 10px 18px; border-radius: 10px; border: 1px solid var(--line); background: var(--card); color: var(--ink); text-decoration: none; font-weight: 600; }
.button.primary { background: var(--ink); color: var(--page); border-color: var(--ink); }
.card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: 12px; background: var(--card); border: 1px solid var(--line); max-width: 640px; }
.meta { font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.links { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 14px; font-weight: 600; }
ul { margin: 0; padding-left: 20px; }
footer { color: var(--muted); font-size: 14px; text-align: center; }
a:focus-visible, .button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1><span>cast</span>-list</h1>
    <p class="lead">Point it at your Copilot Studio agents, cloned. See what they all do — in their YAML and in the text of their instructions — who is off it, what only one has, what the orchestrator passes on, which events they log and whether they fire, and what nobody uses: with the file and line behind every finding. Decide in Excel; the next run checks what you decided. Node alone: no model, no install, no network.</p>
    <img src="images/${ID}-map.png" alt="Six agents of a made-up shop compared: a matrix of who has what, a red × where the shipping specialist does not escalate and the store specialist logs no telemetry">
    <div class="actions"><a class="button primary" href="https://github.com/ruinosus/dna#install">Install the skill</a><a class="button" href="https://github.com/ruinosus/dna">GitHub</a></div>
  </section>
  <section>
    <h2>The example — open the map, play the lesson, download the workbook</h2>
    <article class="card">
      <a href="examples/${ID}.lesson.html"><img src="images/${ID}-lesson.png" alt="The lesson: the orchestrator calls five specialists; two carry a red ×" loading="lazy"></a>
      <span class="meta">Português · fictional agents</span>
      <b>Bodega Azul — atendimento</b>
      <span>An orchestrator and five specialists of a made-up online shop, run with a made-up export of Application Insights. On purpose: shipping does not escalate to a person and gets no conversation history, the store logs no telemetry, coupons spells its error event another way and calls a flow that returns nothing, shipping's event did not fire in 30 days, and a few things nobody uses.</span>
      <span class="links"><a href="examples/${ID}.html">Map</a><a href="examples/${ID}.plot.html">Stage</a><a href="examples/${ID}.playbill.html">RH</a><a href="https://github.com/ruinosus/dna/blob/gh-pages/agent-review/examples/${ID}.diagrams.md">Diagrams (Mermaid)</a><a href="examples/${ID}.lesson.html">Lesson</a><a href="examples/${ID}.xlsx" download>Workbook (.xlsx)</a><a href="examples/${ID}.cast.yaml" download>Cast file (.yaml)</a></span>
    </article>
  </section>
  <section>
    <h2>What it finds — «to look at», in groups</h2>
    <ul>
      <li><b>Contradictions</b> — what people say and the YAML does not agree; a rule that confronts the text with the setup: «has “Only the knowledge”, but also “The model's general knowledge on”».</li>
      <li><b>Contract and telemetry</b> — the orchestrator calling one not in the folder, a routing description of 7 characters, a flow that returns nothing, an event spelt another way («the same event?»), an event that did not fire in 30 days, one with no line in the telemetry.</li>
      <li><b>Off pattern</b> — «1 specialist does not escalate to a person (shipping): on purpose?»; a variation of an official block, a text rule set in two ways or twice in one agent. Patterns are found per role and per type of specialist.</li>
      <li><b>Rules</b> — from the team's profile («every specialist has a KPI»).</li>
      <li><b>Only one has it</b> — innovation to spread, or debt to remove. Folded at first in the map.</li>
      <li><b>Unused</b> — a topic nobody can reach, a variable nobody names, a flow nobody calls, a node switched off. Folded at first too.</li>
      <li><b>Not understood</b> — a file it could not read is told; the rest is read anyway.</li>
    </ul>
  </section>
  <section>
    <h2>The stage — show it in a meeting</h2>
    <article class="card">
      <a href="examples/${ID}.plot.html"><img src="images/${ID}-stage.png" alt="The cast on a stage: the orchestrator, the specialists by type, the flows and the systems, with a red arrow into shipping" loading="lazy"></a>
      <span>The traffic moving along the arrows (each one's topic starts, from the export), lenses that light who follows a pattern and who is off, and a follow spot that walks each call of the orchestrator and stops where it breaks. Click someone for its card.</span>
    </article>
  </section>
  <section>
    <h2>The diagrams — the cast in Mermaid, for the team's docs</h2>
    <article class="card">
      <span><code>--diagrams</code> writes what was read as plain Mermaid: the topology, a sequence per call of the orchestrator, a lens per pattern and the anatomy of each type, in one Markdown document and one <code>.mmd</code> each. It shows on GitHub, in a wiki or in VS Code with nothing of ours, and draws in visual-explainer too.</span>
      <span class="links"><a href="https://github.com/ruinosus/dna/blob/gh-pages/agent-review/examples/${ID}.diagrams.md">The example's diagrams, on GitHub</a></span>
    </article>
  </section>
  <section>
    <h2>The cast as people — the RH</h2>
    <article class="card">
      <a href="examples/${ID}.playbill.html"><img src="images/${ID}-rh.png" alt="The RH of the cast: the staff board, the org chart by type, and a résumé with its development plan" loading="lazy"></a>
      <span>The same cast for whoever thinks in HR terms: who is being hired, who has no owner, who was never published, the post of each role and type, and a résumé each — with the development plan made of what «to look at» says about that one alone. Nothing invented: no goal, owner or number the files do not have.</span>
    </article>
  </section>
  <section>
    <h2>Bring what you already have</h2>
    <ul>
      <li><b>The admin center's inventory</b> or <b>the team's own spreadsheet</b> (<code>--declared</code>, CSV or .xlsx, no template): the column of the agent is found by its values, and every other column becomes what people declared — owner, KPI — with the file and line.</li>
      <li><b>An export of Application Insights</b> (<code>--telemetry</code>): one query, ready to copy, says which events fired and how many times. Nothing goes over the network.</li>
    </ul>
  </section>
  <footer>agent-review is one of the six skills of <a href="../">dna</a>. MIT. The Copilot Studio schema inside is Microsoft's (MIT).</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/agent-review: ${ID} (map, workbook, lesson, cast file) and its pictures`)
