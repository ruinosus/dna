// Checks the skill as someone installing it would get it: SKILL.md's frontmatter, every example built by
// scripts/build.mjs, a recipe that breaks the contract (exit 1) and one with a line across a text (exit 3).
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const skill = resolve(dirname(fileURLToPath(import.meta.url)), '../skills/chalk-talk')
const build = join(skill, 'scripts/build.mjs')
const dir = mkdtempSync(join(tmpdir(), 'chalk-talk-check-'))
let failed = 0
const expect = (ok, what) => {
  console.log(`${ok ? '✓' : '✗'} ${what}`)
  if (!ok) failed++
}
const run = (recipe, flags = []) => spawnSync(process.execPath, [build, recipe, ...flags], { encoding: 'utf8' })

const head = readFileSync(join(skill, 'SKILL.md'), 'utf8').match(/^---\n([\s\S]*?)\n---/)?.[1] ?? ''
const field = (k) => head.match(new RegExp(`^${k}: (.*)$`, 'm'))?.[1] ?? ''
expect(field('name') === 'chalk-talk', 'SKILL.md name is the folder name')
expect(field('description').length > 0 && field('description').length <= 1024, `SKILL.md description has ${field('description').length} of 1024 characters`)
expect(readFileSync(join(skill, 'SKILL.md'), 'utf8').split('\n').length < 500, 'SKILL.md under 500 lines')
const plugin = JSON.parse(readFileSync(join(skill, '../../.claude-plugin/plugin.json'), 'utf8')).version
const npmVersion = JSON.parse(readFileSync(join(skill, '../../npm/package.json'), 'utf8')).version
const cdn = readFileSync(join(skill, 'SKILL.md'), 'utf8').match(/chalk-talk@([\d.]+)\/player\.js/)?.[1]
expect(field('metadata') === '' && head.includes(`version: "${plugin}"`) && npmVersion === plugin && cdn === plugin, `one version everywhere: plugin ${plugin}, npm ${npmVersion}, SKILL.md CDN ${cdn}`)

const examples = join(skill, 'references/examples')
for (const f of readdirSync(examples)) {
  const r = run(join(examples, f), [join(dir, f.replace('.json', '.html'))])
  expect(r.status === 0, `${f}: ${r.stdout.trim().split('\n').filter((l) => l.startsWith('✓ review') || l.startsWith('•') || l.startsWith('!')).join(' / ') || r.stderr.trim()}`)
}

// The text and Mermaid examples of the gallery build too.
const docs = join(skill, '../../docs/examples')
for (const f of readdirSync(docs).filter((f) => /\.(chalk|mmd)$/.test(f))) {
  const r = run(join(docs, f), [join(dir, f.replace(/\.[^.]+$/, '.html'))])
  expect(r.status === 0, `${f}: ${r.stdout.trim().split('\n').filter((l) => /review/.test(l)).join(' / ') || r.stderr.trim()}`)
}
// --svg: an SVG that draws itself with CSS and no script, with only the fonts it uses; a Markdown file gives one per block.
const svgOut = join(dir, 'coin.svg')
const sv = run(join(docs, 'coin-jar.chalk'), [svgOut, '--svg', '--no-review'])
if (sv.status === 4) expect(true, 'no browser here: the --svg check is skipped')
else {
  const svg = sv.status === 0 ? readFileSync(svgOut, 'utf8') : ''
  const timed = (svg.match(/animation:/g) ?? []).length
  expect(sv.status === 0 && !/<script/i.test(svg) && /@keyframes ct-draw/.test(svg) && /prefers-reduced-motion/.test(svg) && timed > 50 && /font-family:\s*'Caveat'/.test(svg),
    `--svg draws itself with no script (${timed} timed elements, ${Math.round(svg.length / 1024)} KB)${sv.status ? `: ${sv.stderr.trim()}` : ''}`)
  const page = join(dir, 'two.md')
  writeFileSync(page, '```chalk-talk\ntitle Um\nid um\ntext "um" at 40,60\n```\n\n```mermaid\nflowchart LR\n  %% title Dois\n  A --> B\n```\n')
  const two = run(page, ['--svg', '--no-review'])
  const names = readdirSync(dir).filter((f) => f.endsWith('.svg')).sort().join(', ')
  expect(two.status === 0 && names === 'coin.svg, dois.svg, um.svg', `a Markdown file gives one SVG per block (${names}${two.status ? `: ${two.stderr.trim()}` : ''})`)
}

// chalk-talk/embed: two lessons on one page (as two blocks in a note) — each moves on its own, the styles go in once,
// and a broken text says its line.
{
  const { runPage } = await import('../skills/chalk-talk/scripts/browser.mjs')
  const embed = pathToFileURL(join(skill, '../../npm/embed.js')).href
  const coin = readFileSync(join(docs, 'coin-jar.chalk'), 'utf8')
  const page = join(dir, 'embed.html')
  writeFileSync(page, `<!doctype html><meta charset="utf-8"><body><div id="a"></div><div id="b"></div><script type="module">
import { mountLesson, readRecipe, ChalkTextError } from ${JSON.stringify(embed)}
const out = {}
try {
  const scene = readRecipe(${JSON.stringify(coin)})
  const [a, b] = [document.getElementById('a'), document.getElementById('b')]
  await mountLesson(a, scene, { compact: true, lang: 'pt' })
  const mb = await mountLesson(b, readRecipe(JSON.stringify(scene)), { compact: true, lang: 'en', onExpand: () => {} })
  a.querySelector('[data-part="next"]').click()
  await new Promise((r) => setTimeout(r, 4000))
  const on = (root) => [...root.querySelectorAll('.chapters button')].findIndex((x) => x.classList.contains('is-on'))
  out.chapters = [on(a), on(b)]
  out.drawn = [a, b].map((r) => r.querySelector('svg').querySelectorAll('path').length)
  out.styles = document.querySelectorAll('#chalk-talk-styles').length
  out.ids = [...document.body.querySelectorAll('[id]')].map((e) => e.id).filter((id) => !/^(a|b)$/.test(id) && !id.startsWith('dw'))
  out.expand = [a, b].map((r) => !r.querySelector('[data-part="expand"]').hidden)
  mb.destroy()
  out.destroyed = b.childElementCount
  try { readRecipe('title X\\nperson ana at 1') } catch (e) { out.error = e instanceof ChalkTextError ? e.line : e.message }
} catch (e) { out.failed = e.message }
const pre = document.createElement('pre'); pre.id = 'chalk-embed'; pre.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(pre)
</script>`)
  const r = runPage(page, 'embed')
  if (!r) expect(true, 'no browser here: the embed check is skipped')
  else {
    const ok = !r.failed && r.chapters?.[0] === 1 && r.chapters?.[1] === 0 && r.drawn.every((n) => n > 5) && r.styles === 1 && !r.ids.length && r.expand[0] === false && r.expand[1] === true && r.destroyed === 0 && r.error === 2
    expect(ok, `chalk-talk/embed: two lessons on a page, each on its own (${JSON.stringify(r)})`)
  }
}

const badText = join(dir, 'bad.chalk')
writeFileSync(badText, 'title X\nperson ana at 1\n')
const bt = run(badText)
expect(bt.status === 1 && /✗ text: line 2:/.test(bt.stderr), `a broken text names its line (${bt.stderr.trim()})`)

const bad = join(dir, 'bad.json')
writeFileSync(bad, JSON.stringify({ id: 'bad', title: 'Bad', width: 900, height: 560, steps: [{ type: 'circle', center: [100, 100] }] }))
const b = run(bad)
expect(b.status === 1 && /✗ contract: .*r/.test(b.stderr), `a broken recipe stops with exit 1 (${b.stderr.trim()})`)

// The engine brings a text back inside the paper by itself; a line drawn across a text is left for the reviewer.
const across = join(dir, 'across.json')
writeFileSync(across, JSON.stringify({ id: 'across', title: 'Across', width: 900, height: 560, steps: [
  { type: 'text', at: [300, 300], text: 'a sentence with a line through it', size: 30 },
  { type: 'line', from: [250, 290], to: [800, 290] },
] }))
const o = run(across)
const reviewed = !/• review/.test(o.stdout)
expect(reviewed ? o.status === 3 && /crosses the text/.test(o.stdout) : o.status === 0, reviewed ? 'a line across a text is found (exit 3)' : 'no browser here: the review check is skipped')

rmSync(dir, { recursive: true, force: true })
if (failed) {
  console.error(`${failed} failed`)
  process.exit(1)
}
