// The GitHub Pages gallery (docs/process-simulation/): every example made into its page (docs/process-simulation/examples/), a picture of
// each running (docs/process-simulation/images/, a headless browser) and docs/process-simulation/index.html. Run after npm run assets.
import { execFileSync } from 'node:child_process'
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { browser, runPages } from '@ruinosus/visual-explainer/kit/browser.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../../..') // the dna repository
const docs = join(repo, 'docs/process-simulation')
const examples = join(repo, 'skills/process-simulation/examples')
if (!browser()) throw new Error('No Chrome, Chromium or Edge: the pictures need one (set CHROME_PATH).')
const ABOUT = {
  'employee-self-service': ['en', 'Employee Self-Service with Workday, after the scenarios of Microsoft’s public sample: vacation balance and profile read from Workday, time off approved by the manager, policy questions answered or sent to an HR partner. Move «Policy questions answered» and watch the HR queue. The numbers are made up.'],
  'admission-documents': ['en', 'Admission documents read by an extraction step and reviewed by people when its confidence is low: how many reviewers the confidence asks for.'],
  'hr-help-desk': ['en', 'An HR help desk on payroll close, 8 to 17, three analysts, a morning peak, people who give up after 30 minutes: what one more analyst buys.'],
  'atendimento-rh.pt-BR': ['pt', 'O mesmo atendimento, com a receita em português: a tela também troca para PT.'],
}
for (const d of ['examples', 'images']) rmSync(join(docs, d), { recursive: true, force: true })
mkdirSync(join(docs, 'examples'), { recursive: true })
mkdirSync(join(docs, 'images'), { recursive: true })
const items = JSON.parse(readFileSync(join(examples, 'index.json'), 'utf8')).map(({ file }) => {
  const id = file.replace(/\.sim$/, '')
  const [lang, about] = ABOUT[id] ?? ['en', '']
  copyFileSync(join(examples, file), join(docs, 'examples', file))
  execFileSync(process.execPath, [join(repo, 'skills/process-simulation/scripts/build.mjs'), join(docs, 'examples', file), '--lang', lang, '--out', join(docs, 'examples')], { stdio: 'ignore' })
  const page = `${id.replace(/\.pt-BR$/i, '')}.process-simulation.html`
  const name = (readFileSync(join(examples, file), 'utf8').match(/^sim\s+"([^"]*)"/m) ?? [])[1] ?? id
  return { id, file, lang, about, name, page }
})
// the pictures, a few seconds into each run, in the light theme
const shots = items.map((d) => ({ file: join(docs, 'examples', d.page), mode: '', shot: { width: 1440, height: 1000, scheme: 'light', settle: 4000 }, png: join(docs, 'images', `${d.id}.png`) }))
const { results } = await runPages(shots, { timeout: 60 })
shots.forEach(({ png }, k) => {
  if (!results[k]?.png) throw new Error(`${png}: the picture failed (${results[k]?.error ?? 'no picture'})`)
  writeFileSync(png, Buffer.from(results[k].png.split(',')[1], 'base64'))
})
for (const { id } of items) console.log(`✓ ${id}`)
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const [first] = items
writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>process-simulation</title>
<meta name="description" content="A process you can watch, and ask «what if»: a short .sim recipe becomes an animated simulation with sliders, ranges and scenarios side by side — written by Claude.">
<style>
:root { --ink: #17211f; --muted: #5b6965; --line: #cdd6d3; --page: #e9eeec; --card: #fff; --accent: #b86a0e; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e6ecea; --muted: #9fb0ab; --line: #34403d; --page: #141a19; --card: #1d2523; --accent: #f0a24a; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 36px; }
h1 { margin: 0; font-size: clamp(38px, 7vw, 60px); line-height: 1; letter-spacing: -0.02em; }
h2 { margin: 0 0 12px; font-size: 22px; }
p { margin: 0; }
a { color: var(--accent); }
.lead { font-size: 19px; max-width: 760px; }
.hero { display: grid; gap: 16px; }
.hero img, .card img { width: 100%; border-radius: 12px; border: 1px solid var(--line); }
.actions { display: flex; gap: 10px; flex-wrap: wrap; }
.button { display: inline-block; padding: 10px 18px; border-radius: 10px; border: 1px solid var(--line); background: var(--card); color: var(--ink); text-decoration: none; font-weight: 600; }
.button.primary { background: var(--ink); color: var(--page); border-color: var(--ink); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 18px; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: 12px; background: var(--card); border: 1px solid var(--line); }
.meta { font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.links { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 14px; font-weight: 600; }
pre { margin: 0; padding: 14px 16px; border-radius: 10px; background: var(--card); border: 1px solid var(--line); overflow-x: auto; font-size: 14px; }
footer { color: var(--muted); font-size: 14px; text-align: center; }
a:focus-visible, .button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1>process-simulation</h1>
    <p class="lead">Describe a process to Claude — what arrives, who handles it, what it costs. Get a simulation you can watch: the items arriving, the queues forming, a slider for every «what if», the ranges of many seeded runs and the scenarios side by side. One HTML file that opens offline.</p>
    <a href="examples/${first.page}"><img src="images/${first.id}.png" alt="${esc(first.name)} running: the recipe on the left, the flow with its queues on the right, the controls and metrics below"></a>
    <div class="actions"><a class="button primary" href="https://github.com/ruinosus/dna#install">Install the skill</a><a class="button" href="https://github.com/ruinosus/dna">GitHub</a></div>
  </section>
  <section>
    <h2>Examples — open one and move the sliders</h2>
    <div class="grid">${items.map((d) => `
      <article class="card">
        <a href="examples/${d.page}"><img src="images/${d.id}.png" alt="${esc(d.name)} running" loading="lazy"></a>
        <span class="meta">${d.lang === 'pt' ? 'Português' : 'English'}</span>
        <b>${esc(d.name)}</b><span>${esc(d.about)}</span>
        <span class="links"><a href="examples/${d.page}">Simulation</a><a href="examples/${d.file}" download>Recipe (.sim)</a></span>
      </article>`).join('')}
    </div>
  </section>
  <section>
    <h2>In Claude Code, the recipe is checked as it is written</h2>
    <p>The dna plugin carries a mod: a <code>.sim</code> with errors is refused with the validator's messages, so Claude fixes it; <code>/simulate</code> runs it and prints each metric's median and range; <code>/simulation-preview</code> opens a pane with the flow.</p>
  </section>
  <footer>process-simulation is MIT licensed. The examples are illustrative; the self-service one follows the scenarios of <a href="https://github.com/microsoft/CopilotStudioSamples/tree/main/EmployeeSelfServiceAgent">Microsoft's Employee Self-Service sample</a> (MIT). Fonts Bricolage Grotesque and IBM Plex (SIL Open Font License).</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/process-simulation/index.html with ${items.length} simulations`)
