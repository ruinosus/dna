// The GitHub Pages gallery (docs/): every example built into its game (docs/examples/), pictures of a scene and of a
// debrief (docs/images/, taken by a headless browser in the light theme) and docs/index.html. Run after npm run assets.
import { execFileSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { browser, runPages } from '@ruinosus/visual-explainer/kit/browser.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the dna repository
const docs = join(repo, 'docs/incident-drill')
const examples = join(repo, 'skills/incident-drill/examples')
if (!browser()) throw new Error('No Chrome, Chromium or Edge: the pictures need one (set CHROME_PATH).')
const ABOUT = {
  checkout: ['pt', 'Checkout down at 3 a.m., right after a deploy — the on-call cannot revert alone, and nobody owns telling the customers.'],
  'database-disk': ['en', 'The orders database disk is almost full at lunchtime — and the biggest files are the ones you must never delete.'],
}
for (const d of ['examples', 'images']) rmSync(join(docs, d), { recursive: true, force: true })
mkdirSync(join(docs, 'examples/runbooks'), { recursive: true })
mkdirSync(join(docs, 'images'), { recursive: true })
// The pages to picture (a scene after the first choice, the debrief after playing it through) go in a folder of their
// own; the pictures, in the light theme, are taken by the kit's browser over the DevTools pipe, all at the end.
const profile = mkdtempSync(join(tmpdir(), 'incident-drill-site-'))
const shots = []
const shot = (page, png) => shots.push({ file: page, shot: { width: 1280, height: 760, scheme: 'light', settle: 800 }, png })
const drills = []
for (const f of readdirSync(examples).filter((x) => x.endsWith('.drill.yaml')).sort()) {
  const id = f.replace('.drill.yaml', '')
  const [lang, about] = ABOUT[id] ?? ['en', '']
  copyFileSync(join(examples, f), join(docs, 'examples', f))
  for (const r of readdirSync(join(examples, 'runbooks'))) copyFileSync(join(examples, 'runbooks', r), join(docs, 'examples/runbooks', r))
  execFileSync(process.execPath, [join(repo, 'skills/incident-drill/scripts/build.mjs'), join(docs, 'examples', f), '--all', '--lang', lang], { stdio: 'ignore' })
  const game = readFileSync(join(docs, 'examples', `${id}.drill.html`), 'utf8')
  // a scene: the first choice taken; the debrief: played to the end the way check.mjs plays it
  const scene = join(profile, `${id}-scene.html`)
  writeFileSync(scene, game.replace('</body>', `<script>setTimeout(() => document.querySelector('.dr-choice:not(.blocked)').click(), 200)</script></body>`))
  shot(scene, join(docs, 'images', `${id}-scene.png`))
  const end = join(profile, `${id}-debrief.html`)
  writeFileSync(end, game.replace('</body>', `<script>setTimeout(() => { let n = 0; while (!document.querySelector('.dr-nums') && n++ < 40) (document.querySelector('.dr-choice:not(.blocked)') ?? document.querySelector('[data-call]'))?.click() }, 200)</script></body>`))
  shot(end, join(docs, 'images', `${id}-debrief.png`))
  drills.push({ id, lang, about, name: (readFileSync(join(examples, f), 'utf8').match(/^name:\s*(.+)$/m) ?? [])[1] ?? id })
}
const { results } = await runPages(shots, { timeout: 60 })
shots.forEach(({ png }, k) => {
  if (!results[k]?.png) throw new Error(`${png}: the picture failed (${results[k]?.error ?? 'no picture'})`)
  writeFileSync(png, Buffer.from(results[k].png.split(',')[1], 'base64'))
})
for (const { id } of drills) console.log(`✓ ${id}`)
rmSync(profile, { recursive: true, force: true })
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>incident-drill</title>
<meta name="description" content="Test your incident runbook by playing it: a drill with a clock, choices and consequences, made from the runbook by Claude.">
<style>
:root { --ink: #1d2330; --muted: #5f6878; --line: #dfe3ea; --page: #f5f6f8; --card: #fff; --red: #c8442c; --accent: #2f5bea; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e8ebf0; --muted: #9aa3b2; --line: #313744; --page: #14171c; --card: #1d2129; --red: #ff8a70; --accent: #8fb0ff; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1120px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 36px; }
h1 { margin: 0; font: 700 clamp(38px, 7vw, 60px)/1 ui-monospace, Menlo, monospace; color: var(--red); }
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
.steps { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
.steps div { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }
footer { color: var(--muted); font-size: 14px; text-align: center; }
a:focus-visible, .button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1>incident-drill</h1>
    <p class="lead">Give Claude your incident runbook. Get a drill your team can play — a clock, choices, consequences, who is in the room — and, at the end, what the runbook does not say.</p>
    <img src="images/checkout-scene.png" alt="A drill in play: the clock at 03:14, a graph of payment errors, a message from support, three choices — one blocked until the Release team is called">
    <div class="actions"><a class="button primary" href="https://github.com/ruinosus/dna#install">Install the skill</a><a class="button" href="examples/checkout.drill.html">Play an example</a><a class="button" href="https://github.com/ruinosus/dna">GitHub</a></div>
  </section>
  <section>
    <h2>How it goes</h2>
    <div class="steps">
      <div><b>1 · Point it at the runbook.</b><br>«Make a drill from our checkout runbook.» Claude reads it and drafts the incident as scenes.</div>
      <div><b>2 · It asks what the runbook does not say.</b><br>Who can revert? Who tells the customers? Escalate to whom? Each question with its bet.</div>
      <div><b>3 · Play it.</b><br>Alone in ten minutes, or projected for the team on a Friday. No score: the clock is the score.</div>
      <div><b>4 · Fix the runbook.</b><br>The debrief lists what was missing — download it, and the improvements as a CSV.</div>
    </div>
  </section>
  <section>
    <h2>Examples — play them here</h2>
    <div class="grid">${drills.map((d) => `
      <article class="card">
        <a href="examples/${d.id}.drill.html"><img src="images/${d.id}-debrief.png" alt="The debrief of «${esc(d.name)}»: the numbers, the timeline and what the runbook did not say" loading="lazy"></a>
        <span class="meta">${d.lang === 'pt' ? 'Português' : 'English'}</span>
        <b>${esc(d.name)}</b><span>${esc(d.about)}</span>
        <span class="links"><a href="examples/${d.id}.drill.html">Play</a><a href="examples/${d.id}.facilitator.md">Facilitator’s script</a><a href="examples/${d.id}.drill.yaml">The drill file</a><a href="examples/runbooks/${d.id}.md">The runbook</a></span>
      </article>`).join('')}
    </div>
  </section>
  <footer>incident-drill is MIT licensed. All examples are fictional. Drawings by <a href="../visual-explainer/">visual-explainer</a>.</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/index.html with ${drills.length} drills`)
