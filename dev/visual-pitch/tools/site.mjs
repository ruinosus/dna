// The GitHub Pages gallery (docs/): every example drawn into a page you can open and play (docs/drawings/), a picture
// of each (docs/thumbs/: the whole drawing, from the page's #snapshots mode in a headless browser, by the kit) and
// docs/index.html listing them by purpose. Run after npm run assets: npm run site.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gallery } from '@ruinosus/visual-explainer/kit/tools/gallery.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the dna repository
const docs = join(repo, 'docs/visual-pitch')
const examples = join(repo, 'skills/visual-pitch/examples')
const FOR = { pitch: 'Pitch', arch: 'Architecture', decision: 'Decision', data: 'Data', timeline: 'Timeline', story: 'Story' }
const ORDER = Object.keys(FOR)

const work = mkdtempSync(join(tmpdir(), 'visual-pitch-site-'))
const drawings = readdirSync(examples).filter((f) => f.endsWith('.chalk')).map((f) => {
  const text = readFileSync(join(examples, f), 'utf8')
  const name = f.replace('.chalk', '')
  const out = join(work, `${name}.html`)
  execFileSync(process.execPath, [join(repo, 'skills/visual-pitch/scripts/build.mjs'), join(examples, f), '--out', out, '--no-review'], { stdio: 'ignore' })
  const line = (k) => text.match(new RegExp(`^${k}\\s+(.+)$`, 'm'))?.[1] ?? ''
  return { name, kind: line('kind'), title: line('title'), english: line('locale').startsWith('en'), html: readFileSync(out, 'utf8') }
}).sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind))
rmSync(work, { recursive: true, force: true })

// The picture of each drawing is its last chapter at the starting values: the whole board.
await gallery(docs, drawings, { pages: 'drawings', mode: 'snapshots', pick: (r) => r.shots?.filter((s) => s.label === 'default').at(-1)?.png })

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
const card = ({ name, kind, title, english }) => `
      <a class="card" href="drawings/${name}.html">
        <img src="thumbs/${name}.png" alt="${esc(title)}" loading="lazy">
        <span class="meta"><span>${FOR[kind]}</span><span>${english ? 'English' : 'Português'}</span></span>
        <b>${esc(title)}</b>
      </a>`

writeFileSync(join(docs, 'index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>visual-pitch</title>
<meta name="description" content="A skill that makes Claude explain anything by drawing it, for a meeting: a pitch, an architecture, a decision, data, a timeline or a story, drawn stroke by stroke in one HTML file.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
:root { --ink: #1f2a37; --muted: #667085; --line: #e4e7ec; --page: #f4f6f8; --card: #fff; --accent: #1f4e8c; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #e9ecef; --muted: #a3acb6; --line: #333a42; --page: #15181c; --card: #1e2228; --accent: #8db8e6; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 40px; }
h1 { margin: 0; font: 600 clamp(34px, 6vw, 56px)/1.1 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; letter-spacing: -0.02em; }
h2 { margin: 0; font: 600 26px/1.2 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; letter-spacing: -0.01em; }
p { margin: 0; }
a { color: var(--accent); }
.hero { display: grid; gap: 18px; justify-items: center; text-align: center; }
.hero .lead { font-size: 20px; max-width: 720px; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.button { display: inline-block; padding: 10px 18px; border-radius: 10px; border: 1px solid var(--line); background: var(--card); color: var(--ink); text-decoration: none; font-weight: 700; }
.button.primary { background: var(--ink); color: var(--page); border-color: var(--ink); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: 12px; background: var(--card); border: 1px solid var(--line); color: var(--ink); text-decoration: none; transition: transform .15s, border-color .15s; }
.card:hover { transform: translateY(-2px); border-color: var(--ink); }
.card:focus-visible, .button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card img { width: 100%; aspect-ratio: 900 / 560; object-fit: contain; border-radius: 8px; background: #ffffff; }
.meta { display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.card b { font: 600 19px/1.3 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif; }
.note { color: var(--muted); }
code { font-size: 14px; background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px; }
footer { color: var(--muted); font-size: 14px; text-align: center; }
@media (prefers-reduced-motion: reduce) { .card { transition: none; } }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1>visual-pitch</h1>
    <p class="lead">Ask Claude to draw a pitch, an architecture, a decision, a number, what happened or a story — and get a clean drawing that draws itself, chapter by chapter, with a highlight at the end. One HTML file, offline.</p>
    <div class="actions">
      <a class="button primary" href="https://github.com/ruinosus/dna#install">Install the skill</a>
      <a class="button" href="https://github.com/ruinosus/dna">GitHub</a>
    </div>
  </section>
  <section>
    <h2>One drawing per purpose — open one and press Next</h2>
    <p class="note" style="margin: 4px 0 16px">Written by Claude with this skill; every example is fictional. To teach a concept, its sibling <a href="../visual-explainer/">visual-explainer</a> draws an explainer.</p>
    <div class="grid">${drawings.map(card).join('')}
    </div>
  </section>
  <footer>visual-pitch is MIT licensed and draws with visual-explainer's engine. IBM Plex Sans (SIL Open Font License); the hand-drawn look by Rough.js, Caveat and Shantell Sans (SIL OFL); animated emoji from Noto (CC BY 4.0), played by lottie-web (MIT).</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/index.html with ${drawings.length} drawings`)
