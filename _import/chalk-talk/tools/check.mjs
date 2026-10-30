// Checks the skill as someone installing it would get it: SKILL.md's frontmatter, every example built by
// scripts/build.mjs, a recipe that breaks the contract (exit 1) and one with a text off the paper (exit 3).
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

const examples = join(skill, 'references/examples')
for (const f of readdirSync(examples)) {
  const r = run(join(examples, f), [join(dir, f.replace('.json', '.html'))])
  expect(r.status === 0, `${f}: ${r.stdout.trim().split('\n').filter((l) => l.startsWith('✓ review') || l.startsWith('•') || l.startsWith('!')).join(' / ') || r.stderr.trim()}`)
}

const bad = join(dir, 'bad.json')
writeFileSync(bad, JSON.stringify({ id: 'bad', title: 'Bad', width: 900, height: 560, steps: [{ type: 'circle', center: [100, 100] }] }))
const b = run(bad)
expect(b.status === 1 && /✗ contract: .*r/.test(b.stderr), `a broken recipe stops with exit 1 (${b.stderr.trim()})`)

const off = join(dir, 'off.json')
writeFileSync(off, JSON.stringify({ id: 'off', title: 'Off', width: 900, height: 560, steps: [
  { type: 'text', at: [40, 60], text: 'a title', size: 40 },
  { type: 'text', at: [820, 300], text: 'this sentence runs off the paper', size: 30 },
] }))
const o = run(off)
const reviewed = !/• review/.test(o.stdout)
expect(reviewed ? o.status === 3 && /off the paper/.test(o.stdout) : o.status === 0, reviewed ? 'a text off the paper is found (exit 3)' : 'no browser here: off-paper check skipped')

rmSync(dir, { recursive: true, force: true })
if (failed) {
  console.error(`${failed} failed`)
  process.exit(1)
}
