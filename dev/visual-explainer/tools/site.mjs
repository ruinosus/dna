// The GitHub Pages gallery (docs/): every example built into a lesson you can open and play (docs/lessons/), a picture
// of each (docs/thumbs/: the whole drawing, from the page's #snapshots mode in a headless browser) and docs/index.html
// listing them.
// Run after `npm run assets`: npm run site.
import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from '../../../kit/browser.mjs'
import { fill, inline } from '../../../kit/page.mjs'
import { gallery } from '../../../kit/tools/gallery.mjs'
import { recipesIn } from './recipes.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the dna repository
const docs = join(repo, 'docs/visual-explainer')
const player = readFileSync(join(repo, 'skills/visual-explainer/assets/player.html'), 'utf8')

// the gallery's own recipes and hand-made pictures live in dev/visual-explainer/gallery/; docs/ is made, not kept
const gallerySrc = join(root, 'gallery')
mkdirSync(join(docs, 'images'), { recursive: true })
cpSync(join(gallerySrc, 'images'), join(docs, 'images'), { recursive: true })
const sources = [join(gallerySrc, 'examples'), join(repo, 'skills/visual-explainer/references/examples')]
const lessons = []
for (const d of sources) {
  for (const { file, scene } of await recipesIn(d)) lessons.push({ file, scene, english: (scene.locale ?? 'pt-BR').startsWith('en') })
}

// The picture of each lesson is its last chapter at the starting values: the whole drawing (the #snapshots mode).
const pages = await gallery(docs, lessons.map(({ file, scene }) => ({ name: file, html: fill(player, { RECIPE: inline(scene) }) })), {
  mode: 'snapshots',
  pick: (r) => r.shots?.filter((s) => s.label === 'default').at(-1)?.png,
})
// The README shows these as SVGs that draw themselves (build.mjs --svg).
for (const [k, { file }] of lessons.entries()) {
  if (!['time-off-request', 'training-hours'].includes(file)) continue
  const r = await runPage(pages[k], 'svg', '', { timeout: 60 })
  if (!r || r.error) throw new Error(`${file}: the animated SVG failed (${r?.error ?? 'no browser'})`)
  writeFileSync(join(docs, 'images', `${file}.svg`), r.svg)
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const card = ({ file, scene, english }) => `
      <a class="card" href="lessons/${file}.html">
        <img src="thumbs/${file}.png" alt="${esc(scene.title)}" loading="lazy">
        <span class="meta"><span>${esc(scene.category ?? '')}</span><span class="lang">${english ? 'English' : 'Português'}</span></span>
        <b>${esc(scene.title)}</b>
        <span class="goal">${esc(scene.learning?.goal ?? '')}</span>
      </a>`

writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>visual-explainer</title>
<meta name="description" content="A skill that makes Claude explain an idea by drawing it: a hand-drawn lesson that draws itself, in one HTML file.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
:root { --ink: #1f2a37; --muted: #667085; --line: #e4e7ec; --page: #f4f6f8; --card: #fff; --paper: #ffffff; --accent: #1f4e8c; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e9ecef; --muted: #a3acb6; --line: #333a42; --page: #15181c; --card: #1e2228; --paper: #ffffff; --accent: #8fa8ff; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 40px; }
h1 { margin: 0; font: 600 clamp(34px, 6vw, 56px)/1.1 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; letter-spacing: -0.02em; }
h2 { margin: 0; font: 600 26px/1.2 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; letter-spacing: -0.01em; }
p { margin: 0; }
a { color: var(--accent); }
.hero { display: grid; gap: 18px; justify-items: center; text-align: center; }
.hero .lead { font-size: 20px; max-width: 720px; }
.hero img { width: 100%; max-width: 900px; border-radius: 12px; border: 1px solid var(--line); background: var(--paper); }
.actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.button { display: inline-block; padding: 10px 18px; border-radius: 10px; border: 1px solid var(--line); background: var(--card); color: var(--ink); text-decoration: none; font-weight: 700; }
.button.primary { background: var(--ink); color: var(--page); border-color: var(--ink); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 18px; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: 12px; background: var(--card); border: 1px solid var(--line); color: var(--ink); text-decoration: none; transition: transform .15s, border-color .15s; }
.card:hover { transform: translateY(-2px); border-color: var(--ink); }
.card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card img { width: 100%; aspect-ratio: 900 / 560; object-fit: contain; border-radius: 8px; background: #ffffff; }
.meta { display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.card b { font: 600 19px/1.3 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; }
.goal { font-size: 14px; color: var(--muted); }
.how { display: grid; gap: 14px; }
.how img { width: 100%; border-radius: 12px; border: 1px solid var(--line); }
ol { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
code { font-size: 14px; background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px; }
footer { color: var(--muted); font-size: 14px; text-align: center; }
@media (prefers-reduced-motion: reduce) { .card { transition: none; } }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1>visual-explainer</h1>
    <p class="lead">Ask Claude to explain something by drawing it — and get a hand-drawn lesson that draws itself, chapter by chapter, with values you can move. One HTML file, offline.</p>
    <img src="images/hero.png" alt="A lesson on demand and capacity at the HR help desk, drawn in the business theme">
    <div class="actions">
      <a class="button primary" href="https://github.com/ruinosus/dna#install">Install the skill</a>
      <a class="button" href="https://github.com/ruinosus/dna">GitHub</a>
    </div>
  </section>
  <section>
    <h2>Lessons — open one and press Next</h2>
    <p class="goal" style="margin: 4px 0 16px">Each one was written by Claude with this skill and plays right here in your browser.</p>
    <div class="grid">${lessons.map(card).join('')}
    </div>
  </section>
  <section class="how">
    <h2>How it works</h2>
    <img src="images/visual-explainer-how.png" alt="You ask Claude, Claude chooses the hook, the audience and the value to move, writes the recipe, build.mjs checks it, out comes lesson.html">
    <ol>
      <li>Claude chooses the everyday thing to tie the idea to, who it is for and which number moves, and draws at once — then says what it chose and offers to change it. For a class it asks first.</li>
      <li>It writes a short text <b>recipe</b> — what to draw, step by step — never the drawing itself.</li>
      <li><code>scripts/build.mjs</code> checks the recipe, builds one HTML file and, with a headless browser, checks that nothing leaves the paper and no text covers another.</li>
    </ol>
  </section>
  <footer>visual-explainer is MIT licensed. IBM Plex Sans (SIL Open Font License); the hand-drawn look by Rough.js, Caveat and Shantell Sans (SIL OFL).</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/index.html with ${lessons.length} lessons`)
