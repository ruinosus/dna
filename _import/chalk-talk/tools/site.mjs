// The GitHub Pages gallery (docs/): every example built into a lesson you can open and play (docs/lessons/), a picture
// of each (docs/thumbs/: the whole drawing, from the page's #snapshots mode in a headless browser) and docs/index.html
// listing them.
// Run after `npm run assets`: npm run site.
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { runPage } from '../kit/browser.mjs'
import { fill, inline } from '../kit/page.mjs'
import { gallery } from '../kit/tools/gallery.mjs'
import { recipesIn } from './recipes.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const docs = join(root, 'docs')
const player = readFileSync(join(root, 'skills/chalk-talk/assets/player.html'), 'utf8')

const sources = [join(docs, 'examples'), join(root, 'skills/chalk-talk/references/examples')]
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
  if (!['coffee-order', 'coin-jar'].includes(file)) continue
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
<title>chalk-talk</title>
<meta name="description" content="A skill that makes Claude explain an idea by drawing it: a hand-drawn lesson that draws itself, in one HTML file.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@700&family=Shantell+Sans:wght@400;700&display=swap" rel="stylesheet">
<style>
:root { --ink: #242424; --muted: #6b665c; --line: #e0d8c6; --page: #f3f1ec; --card: #fff; --paper: #fbf7ee; --accent: #2f5bea; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #ece8df; --muted: #a8a294; --line: #3a3832; --page: #1c1b19; --card: #262521; --paper: #2b2a26; --accent: #8fa8ff; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 'Shantell Sans', system-ui, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 40px; }
h1 { margin: 0; font: 700 clamp(48px, 9vw, 88px)/1 'Caveat', cursive; }
h2 { margin: 0; font: 700 36px/1.1 'Caveat', cursive; }
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
.card img { width: 100%; aspect-ratio: 900 / 560; object-fit: contain; border-radius: 8px; background: #fbf7ee; }
.meta { display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.card b { font: 700 26px/1.1 'Caveat', cursive; }
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
    <h1>chalk-talk</h1>
    <p class="lead">Ask Claude to explain something by drawing it — and get a hand-drawn lesson that draws itself, chapter by chapter, with values you can move. One HTML file, offline.</p>
    <img src="images/hero.gif" alt="A hand-drawn lesson about compound interest drawing itself, then the growth rate is moved and the curve changes">
    <div class="actions">
      <a class="button primary" href="https://github.com/ruinosus/chalk-talk#install">Install the skill</a>
      <a class="button" href="https://github.com/ruinosus/chalk-talk">GitHub</a>
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
    <img src="images/chalk-talk-how.png" alt="You ask Claude, Claude chooses the hook, the audience and the value to move, writes the recipe, build.mjs checks it, out comes lesson.html">
    <ol>
      <li>Claude chooses the everyday thing to tie the idea to, who it is for and which number moves, and draws at once — then says what it chose and offers to change it. For a class it asks first.</li>
      <li>It writes a short text <b>recipe</b> — what to draw, step by step — never the drawing itself.</li>
      <li><code>scripts/build.mjs</code> checks the recipe, builds one HTML file and, with a headless browser, checks that nothing leaves the paper and no text covers another.</li>
    </ol>
  </section>
  <footer>chalk-talk is MIT licensed. Strokes by Rough.js; fonts Caveat and Shantell Sans (SIL Open Font License).</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/index.html with ${lessons.length} lessons`)
