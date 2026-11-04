// The GitHub Pages gallery (docs/opening-night/): every solution accelerator made into its page
// (docs/opening-night/examples/<accelerator>.solution.html), a picture of its summary (docs/opening-night/images/, a
// headless browser) and docs/opening-night/index.html. Run after npm run assets.
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { browser, runPages } from 'chalk-talk/kit/browser.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../../..')
const docs = join(repo, 'docs/opening-night')
const examples = join(repo, 'skills/opening-night/examples')
if (!browser()) throw new Error('No Chrome, Chromium or Edge: the pictures need one (set CHROME_PATH).')
rmSync(docs, { recursive: true, force: true })
mkdirSync(join(docs, 'examples'), { recursive: true })
mkdirSync(join(docs, 'images'), { recursive: true })
const field = (text, k) => (new RegExp(`^${k}:\\s*(.+)$`, 'm').exec(text)?.[1] ?? '').trim()
const items = readdirSync(examples).filter((d) => existsSync(join(examples, d, `${d}.solution.yaml`))).map((id) => {
  const text = readFileSync(join(examples, id, `${id}.solution.yaml`), 'utf8')
  execFileSync(process.execPath, [join(repo, 'skills/opening-night/scripts/build.mjs'), join(examples, id, `${id}.solution.yaml`), '--out', join(docs, 'examples')], { stdio: 'ignore' })
  const pieces = (text.match(/^(way|sim|blueprint|drill|agents|lesson):/gm) ?? []).map((k) => k.slice(0, -1))
  return { id, name: field(text, 'name'), about: field(text, 'about'), lang: field(text, 'lang') || 'en', pieces, page: `examples/${id}.solution.html` }
})
const shots = items.map((d) => ({ file: join(docs, d.page), mode: '', shot: { width: 1300, height: 820, scheme: 'light', settle: 300 }, png: join(docs, 'images', `${d.id}.png`) }))
const { results } = await runPages(shots, { timeout: 60 })
shots.forEach(({ png }, k) => {
  if (!results[k]?.png) throw new Error(`${png}: the picture failed (${results[k]?.error ?? 'no picture'})`)
  writeFileSync(png, Buffer.from(results[k].png.split(',')[1], 'base64'))
})
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>opening-night — solution accelerators</title>
<meta name="description" content="A process seen by every skill, in one page: the way of working, the simulation, the journey, the drill and the agents.">
<style>
:root { --bg: #f6f5f2; --paper: #fff; --ink: #1d232a; --muted: #5d6670; --line: #dcdad4; --accent: #2f5d8a; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --bg: #15181c; --paper: #1e2228; --ink: #e9ecef; --muted: #a3acb6; --line: #333a42; --accent: #8db8e6; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 40px 16px 64px; display: grid; gap: 28px; }
h1 { margin: 0; font-size: 34px; letter-spacing: -0.01em; }
p { margin: 0; max-width: 76ch; }
a { color: var(--accent); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 18px; }
.card { display: grid; gap: 8px; padding: 12px; border-radius: 12px; background: var(--paper); border: 1px solid var(--line); color: var(--ink); text-decoration: none; }
.card:hover { border-color: var(--ink); }
.card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card img { width: 100%; aspect-ratio: 13 / 8.2; object-fit: cover; object-position: top; border-radius: 8px; border: 1px solid var(--line); }
.card b { font-size: 19px; }
.meta { font-size: 13px; color: var(--muted); }
pre { margin: 0; padding: 12px 14px; border-radius: 10px; background: var(--paper); border: 1px solid var(--line); overflow-x: auto; font-size: 14px; }
</style>
</head>
<body>
<main>
  <p><a href="../">← house-lights</a></p>
  <h1>opening-night</h1>
  <p>A solution is one process seen by every skill: the way of working, the «what if» simulation, the customer's journey, the incident drill, the Copilot Studio agents. One short <code>.solution.yaml</code> names the pieces; one page shows them all, each drawn by its own skill. Start from one of these accelerators — every number in them is made up, to be replaced with yours.</p>
  <div class="grid">${items.map((d) => `
    <a class="card" href="${d.page}">
      <img src="images/${d.id}.png" alt="" loading="lazy">
      <b>${esc(d.name)}</b>
      <span>${esc(d.about)}</span>
      <span class="meta">${esc(d.id)} · ${d.pieces.join(', ')} · ${d.lang === 'pt' ? 'português' : 'English'}</span>
    </a>`).join('')}
  </div>
  <pre>npx house-lights opening-night --new service-desk my-desk
npx house-lights opening-night my-desk/service-desk.solution.yaml</pre>
</main>
</body>
</html>
`)
for (const { id } of items) console.log(`✓ ${id}`)
console.log(`✓ docs/opening-night/index.html with ${items.length} accelerators`)
