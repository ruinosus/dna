// The GitHub Pages gallery (docs/): every example made into its map, workbook and lesson (docs/examples/), pictures of
// each map and lesson (docs/images/, a headless browser in the light theme) and docs/index.html. Run after npm run assets.
import { execFileSync } from 'node:child_process'
import { copyFileSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { browser, runPages } from '../../../skills/service-blueprint/scripts/browser.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the house-lights repository
const docs = join(repo, 'docs/service-blueprint')
const examples = join(repo, 'skills/service-blueprint/examples')
if (!browser()) throw new Error('No Chrome, Chromium or Edge: the pictures need one (set CHROME_PATH).')
const ABOUT = {
  devolucao: ['pt', 'Returning an online purchase: six days with no news is the worst moment — and, on purpose, nobody owns it yet. Four things to look at.'],
  'gym-signup': ['en', 'Joining a neighbourhood gym: twenty minutes of paperwork while the class starts — with an action and an owner.'],
}
for (const d of ['examples', 'images']) rmSync(join(docs, d), { recursive: true, force: true })
mkdirSync(join(docs, 'examples'), { recursive: true })
mkdirSync(join(docs, 'images'), { recursive: true })
// The pictures, in the light theme, taken by the kit's browser over the DevTools pipe — all in one opening at the end.
const shots = []
const shot = (page, png, [width, height], mode = '') => shots.push({ file: page, mode, shot: { width, height, scheme: 'light' }, png })
const items = []
for (const f of readdirSync(examples).filter((x) => x.endsWith('.blueprint.yaml')).sort()) {
  const id = f.replace('.blueprint.yaml', '')
  const [lang, about] = ABOUT[id] ?? ['en', '']
  copyFileSync(join(examples, f), join(docs, 'examples', f))
  execFileSync(process.execPath, [join(repo, 'skills/service-blueprint/scripts/build.mjs'), join(docs, 'examples', f), '--all', '--lang', lang], { stdio: 'ignore' })
  shot(join(docs, 'examples', `${id}.html`), join(docs, 'images', `${id}-map.png`), [1440, 860])
  shot(join(docs, 'examples', `${id}.lesson.html`), join(docs, 'images', `${id}-lesson.png`), [1100, 640], 'still')
  items.push({ id, lang, about, name: (readFileSync(join(examples, f), 'utf8').match(/^name:\s*(.+)$/m) ?? [])[1] ?? id })
}
const { results } = await runPages(shots, { timeout: 60 })
shots.forEach(({ png }, k) => {
  if (!results[k]?.png) throw new Error(`${png}: the picture failed (${results[k]?.error ?? 'no picture'})`)
  writeFileSync(png, Buffer.from(results[k].png.split(',')[1], 'base64'))
})
for (const { id } of items) console.log(`✓ ${id}`)
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>service-blueprint</title>
<meta name="description" content="A service blueprint, clear and checkable: what the customer lives at each moment and who makes it happen behind — made by Claude from interviews and tickets.">
<style>
:root { --ink: #1d2330; --muted: #5f6878; --line: #dfe3ea; --page: #f5f6f8; --card: #fff; --accent: #2f5bea; --warm: #fff4d6; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e8ebf0; --muted: #9aa3b2; --line: #313744; --page: #14171c; --card: #1d2129; --accent: #8fb0ff; --warm: #3a3220; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 36px; }
h1 { margin: 0; font-size: clamp(38px, 7vw, 60px); line-height: 1; letter-spacing: -0.02em; }
h1 span { background: var(--warm); padding: 0 .15em; border-radius: 6px; }
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
footer { color: var(--muted); font-size: 14px; text-align: center; }
a:focus-visible, .button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1><span>front</span>-of-house</h1>
    <p class="lead">Give Claude your interviews, tickets and process notes. Get a service blueprint: each moment the customer lives and how it feels — and who, on stage and behind, makes it happen. With the worst moment, and whether anyone owns it, in plain sight.</p>
    <img src="images/devolucao-map.png" alt="A service blueprint of a return: the line of how the customer feels dips at «waits for news — 6 days», and under it the stage, backstage and systems">
    <div class="actions"><a class="button primary" href="https://github.com/ruinosus/house-lights#install">Install the skill</a><a class="button" href="https://github.com/ruinosus/house-lights">GitHub</a></div>
  </section>
  <section>
    <h2>Examples — open a map, play a lesson, download the workbook</h2>
    <div class="grid">${items.map((d) => `
      <article class="card">
        <a href="examples/${d.id}.html"><img src="images/${d.id}-lesson.png" alt="The lesson of «${esc(d.name)}»: the customer at each moment, higher when they feel better" loading="lazy"></a>
        <span class="meta">${d.lang === 'pt' ? 'Português' : 'English'}</span>
        <b>${esc(d.name)}</b><span>${esc(d.about)}</span>
        <span class="links"><a href="examples/${d.id}.html">Map</a><a href="examples/${d.id}.lesson.html">Lesson</a><a href="examples/${d.id}.xlsx" download>Workbook (.xlsx)</a><a href="examples/${d.id}.blueprint.yaml" download>File (.blueprint.yaml)</a></span>
      </article>`).join('')}
    </div>
  </section>
  <footer>service-blueprint is MIT licensed. All examples are fictional. Lessons by <a href="https://github.com/ruinosus/house-lights">chalk-talk</a>; its sibling <a href="https://github.com/ruinosus/house-lights">gates-and-handoffs</a> maps how the work goes inside.</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/index.html with ${items.length} blueprints`)
