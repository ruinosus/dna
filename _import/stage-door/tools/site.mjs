// The GitHub Pages gallery (docs/): every example made into its map, workbook and lesson (docs/examples/), a picture of
// each map and lesson (docs/images/, taken by a headless browser) and docs/index.html listing them. Run after
// `npm run assets`: npm run site.
import { execFileSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { browser } from '../skills/stage-door/scripts/browser.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const docs = join(root, 'docs')
const examples = join(root, 'skills/stage-door/examples')
const exe = browser()
if (!exe) throw new Error('No Chrome, Chromium or Edge: the pictures need one (set CHROME_PATH).')
// The language each example is written in, and one line on what it shows.
const ABOUT = {
  'feature-delivery': ['pt', 'From an idea to a measured result: discovery, delivery and operation, with a prototype gate and a production gate.'],
  scrum: ['en', 'A Scrum team: a backlog item refined, built in a sprint and accepted, with Definition of Ready and Done as gates.'],
  'service-desk': ['pt', 'A service desk: a ticket triaged, solved at first level or escalated, and closed only when the customer confirms.'],
  'initiative-portfolio': ['pt', 'An initiative portfolio: from an idea to a committee decision, each stage receiving what the one before delivers — the thread, in the Stages tab.'],
}

for (const dir of ['examples', 'images']) {
  rmSync(join(docs, dir), { recursive: true, force: true })
  mkdirSync(join(docs, dir), { recursive: true })
}
const profile = mkdtempSync(join(tmpdir(), 'stage-door-site-'))
const shot = (page, png, [w, h], hash = '') =>
  execFileSync(exe, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', `--user-data-dir=${profile}`, `--window-size=${w},${h}`, '--virtual-time-budget=20000', `--screenshot=${png}`, `${pathToFileURL(page).href}${hash}`], { stdio: 'ignore', timeout: 90000 })

const ways = []
for (const f of readdirSync(examples).filter((x) => x.endsWith('.way.yaml')).sort()) {
  const id = f.replace('.way.yaml', '')
  const [lang, about] = ABOUT[id] ?? ['en', '']
  copyFileSync(join(examples, f), join(docs, 'examples', f))
  execFileSync(process.execPath, [join(root, 'skills/stage-door/scripts/build.mjs'), join(docs, 'examples', f), '--all', '--lang', lang], { stdio: 'ignore' })
  shot(join(docs, 'examples', `${id}.html`), join(docs, 'images', `${id}-map.png`), [1440, 620])
  shot(join(docs, 'examples', `${id}.lesson.html`), join(docs, 'images', `${id}-lesson.png`), [1200, 760], '#still')
  const name = readFileSync(join(examples, f), 'utf8').match(/^name:\s*(.+)$/m)?.[1] ?? id
  ways.push({ id, name, lang, about })
  console.log(`✓ ${id}`)
}
rmSync(profile, { recursive: true, force: true })

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const card = ({ id, name, lang, about }) => `
      <article class="card">
        <a href="examples/${id}.html"><img src="images/${id}-map.png" alt="The map of «${esc(name)}»: phases on top, who leads in the rows, the stages and gates" loading="lazy"></a>
        <span class="meta">${lang === 'pt' ? 'Português' : 'English'}</span>
        <b>${esc(name)}</b>
        <span class="about">${esc(about)}</span>
        <span class="links"><a href="examples/${id}.html">Map</a><a href="examples/${id}.lesson.html">Lesson</a><a href="examples/${id}.xlsx" download>Workbook (.xlsx)</a><a href="examples/${id}.way.yaml" download>File (.way.yaml)</a></span>
      </article>`

writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>stage-door</title>
<meta name="description" content="A skill that turns a team's process documents into one clear, checkable way of working: a file, an offline map, an Excel workbook and a drawn lesson.">
<style>
:root { --ink: #1d2330; --muted: #5f6878; --line: #dfe3ea; --page: #f5f6f8; --card: #fff; --accent: #2f5bea; --gate: #c8442c; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e8ebf0; --muted: #9aa3b2; --line: #313744; --page: #14171c; --card: #1d2129; --accent: #8fb0ff; --gate: #ff8a70; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 40px; }
h1 { margin: 0; font-size: clamp(40px, 7vw, 64px); line-height: 1; letter-spacing: -0.02em; }
h1 i { font-style: normal; color: var(--gate); }
h2 { margin: 0 0 12px; font-size: 24px; }
p { margin: 0; }
a { color: var(--accent); }
.hero { display: grid; gap: 16px; }
.hero .lead { font-size: 20px; max-width: 760px; }
.hero img { width: 100%; border-radius: 12px; border: 1px solid var(--line); }
.actions { display: flex; gap: 10px; flex-wrap: wrap; }
.button { display: inline-block; padding: 10px 18px; border-radius: 10px; border: 1px solid var(--line); background: var(--card); color: var(--ink); text-decoration: none; font-weight: 600; }
.button.primary { background: var(--ink); color: var(--page); border-color: var(--ink); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 18px; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: 12px; background: var(--card); border: 1px solid var(--line); }
.card img { width: 100%; aspect-ratio: 1440 / 620; object-fit: cover; object-position: top left; border-radius: 8px; border: 1px solid var(--line); }
.meta { font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.card b { font-size: 20px; }
.about { font-size: 14px; color: var(--muted); }
.links { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 14px; font-weight: 600; }
.four { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
.four div { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px; }
.four b { display: block; }
code { font-size: 14px; background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px; }
footer { color: var(--muted); font-size: 14px; text-align: center; }
a:focus-visible, .button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1>stage<i>-</i>door</h1>
    <p class="lead">Give Claude your team's process — the PDF, the slides, what everyone just knows — and get one clear way of working: the stages, the gates and who approves them, the roles and what each step delivers. Checked, not invented.</p>
    <img src="images/feature-delivery-map.png" alt="The map of a delivery flow: phases Discovery, Delivery and Operation on top, Product, Engineering and Quality in the rows, the stages in order and two gates">
    <div class="actions">
      <a class="button primary" href="https://github.com/ruinosus/stage-door#install">Install the skill</a>
      <a class="button" href="https://github.com/ruinosus/stage-door">GitHub</a>
    </div>
  </section>
  <section>
    <h2>Four files from one</h2>
    <div class="four">
      <div><b><code>&lt;id&gt;.way.yaml</code></b>The source: plain text you keep in Git. Every other file is made from it.</div>
      <div><b>The map (.html)</b>One page that opens offline: click a stage or a gate, see roles (RACI), gates and outputs, download a PNG.</div>
      <div><b>The workbook (.xlsx)</b>Summary, Stages, Gates, Roles (RACI), Outputs, KPIs and a checklist for the gate meeting. Edit it and Claude proposes the changes back.</div>
      <div><b>The lesson (.html)</b>The flow drawn stroke by stroke, a chapter per phase — made with <a href="https://github.com/ruinosus/chalk-talk">chalk-talk</a>.</div>
    </div>
  </section>
  <section>
    <h2>Examples — open a map, play a lesson, download the workbook</h2>
    <div class="grid">${ways.map(card).join('')}
    </div>
  </section>
  <footer>stage-door is MIT licensed. All examples are fictional.</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/index.html with ${ways.length} ways`)
