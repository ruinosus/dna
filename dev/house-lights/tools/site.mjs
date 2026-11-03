// The front page of the GitHub Pages site (docs/index.html): the six skills, each with a picture from its own gallery
// (docs/<skill>/, made by that skill's site), what it is for and how to install them all. Run after the six sites.
import { existsSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const SKILLS = [
  ['chalk-talk', 'images/chalk-talk-how.png', 'Teach an idea by drawing it', 'A hand-drawn lesson that appears stroke by stroke, chapter by chapter, with narration and values you can move.'],
  ['back-of-napkin', 'thumbs/pitch-pharmacy-queue.png', 'Present it on a napkin', 'A pitch, an architecture, a decision, data, a timeline or a story, drawn to be shown — it opens presenting, and becomes a PowerPoint.'],
  ['dress-rehearsal', 'images/checkout-scene.png', 'Rehearse the incident', 'A runbook becomes a drill to play, with a clock and choices, and a debrief of what the runbook does not say.'],
  ['gates-and-handoffs', 'images/feature-delivery-map.png', 'Map how the team works', 'Stages, gates and who approves them, roles and outputs: one checkable file, a map, a workbook and a lesson.'],
  ['service-blueprint', 'images/gym-signup-map.png', 'Map what the customer lives', 'Each moment of a journey, how it feels, and who makes it happen on stage, backstage and in the systems.'],
  ['cast-list', 'images/bodega-azul-map.png', 'Compare the agents', 'Copilot Studio agents side by side: what repeats, who is off the pattern, what the orchestrator passes on, which events fire, what nobody uses — with the file behind each.'],
]
for (const [s, img] of SKILLS) if (!existsSync(join(repo, 'docs', s, img))) throw new Error(`docs/${s}/${img} is missing: run that skill's site first.`)
const card = ([s, img, title, text]) => `
      <a class="card" href="${s}/">
        <img src="${s}/${img}" alt="" loading="lazy">
        <span class="meta"><span>${s}</span><span>gallery →</span></span>
        <b>${title}</b>
        <span>${text}</span>
      </a>`

writeFileSync(join(repo, 'docs/index.html'), `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>house-lights</title>
<meta name="description" content="Six Claude skills for showing an idea to people: teach it by drawing, present it, rehearse an incident, map a team's way of working and a customer journey, compare Copilot Studio agents — each one HTML file that opens offline.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Caveat:wght@700&family=Shantell+Sans:wght@400;700&display=swap" rel="stylesheet">
<style>
:root { --ink: #242424; --muted: #6b665c; --line: #e0d8c6; --page: #f3f1ec; --card: #fff; --accent: #2f5bea; color-scheme: light dark; }
@media (prefers-color-scheme: dark) { :root { --ink: #ece8df; --muted: #a8a294; --line: #3a3832; --page: #1c1b19; --card: #262521; --accent: #8fa8ff; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 16px/1.55 'Shantell Sans', system-ui, sans-serif; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 16px 64px; display: flex; flex-direction: column; gap: 40px; }
h1 { margin: 0; font: 700 clamp(48px, 9vw, 88px)/1 'Caveat', cursive; }
h2 { margin: 0; font: 700 36px/1.1 'Caveat', cursive; }
p { margin: 0; }
a { color: var(--accent); }
.hero { display: grid; gap: 18px; justify-items: center; text-align: center; }
.hero .lead { font-size: 20px; max-width: 760px; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
.button { display: inline-block; padding: 10px 18px; border-radius: 10px; border: 1px solid var(--line); background: var(--card); color: var(--ink); text-decoration: none; font-weight: 700; }
.button.primary { background: var(--ink); color: var(--page); border-color: var(--ink); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; }
.card { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: 12px; background: var(--card); border: 1px solid var(--line); color: var(--ink); text-decoration: none; transition: transform .15s, border-color .15s; }
.card:hover { transform: translateY(-2px); border-color: var(--ink); }
.card:focus-visible, .button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.card img { width: 100%; aspect-ratio: 16 / 10; object-fit: contain; border-radius: 8px; background: #fbf7ee; }
.meta { display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); }
.card b { font: 700 26px/1.1 'Caveat', cursive; }
pre { margin: 0; padding: 14px 16px; border-radius: 10px; background: var(--card); border: 1px solid var(--line); overflow-x: auto; font-size: 14px; }
.install { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; max-width: 760px; margin: 0 auto; width: 100%; }
code { font-size: 14px; background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 1px 6px; }
.note { color: var(--muted); }
footer { color: var(--muted); font-size: 14px; text-align: center; }
@media (prefers-reduced-motion: reduce) { .card { transition: none; } }
</style>
</head>
<body>
<main>
  <section class="hero">
    <h1>house-lights</h1>
    <p class="lead">The lights that come up so everyone can see. Six skills for Claude that show an idea to people — by drawing it, playing it, mapping it or comparing it — each one an HTML file that opens offline.</p>
    <div class="actions">
      <a class="button primary" href="#install">Install</a>
      <a class="button" href="https://github.com/ruinosus/house-lights">GitHub</a>
    </div>
  </section>
  <section>
    <div class="grid">${SKILLS.map(card).join('')}
    </div>
  </section>
  <section class="install" id="install">
    <h2>Install</h2>
    <p>In Claude Code, all six at once:</p>
    <pre>/plugin marketplace add ruinosus/house-lights
/plugin install house-lights@house-lights</pre>
    <p class="note">In claude.ai, upload each skill's zip from the <a href="https://github.com/ruinosus/house-lights/releases">latest release</a> (Settings › Capabilities › Skills, code execution on). Outside Claude: <code>npx house-lights &lt;skill&gt; &lt;file&gt;</code>.</p>
  </section>
  <footer>house-lights is MIT licensed; every example is fictional. Strokes by Rough.js; fonts Caveat and Shantell Sans (SIL Open Font License); animated emoji from Noto (CC BY 4.0), played by lottie-web (MIT).</footer>
</main>
</body>
</html>
`)
console.log(`✓ docs/index.html with the ${SKILLS.length} skills`)
