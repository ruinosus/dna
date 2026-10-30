// Checks the skill as someone installing it would get it: SKILL.md's frontmatter, every example built by
// scripts/build.mjs, a recipe that breaks the contract (exit 1) and one with a line across a text (exit 3).
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

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
