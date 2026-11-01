// Checks what holds the five skills together: one version in the plugin, the npm package and every SKILL.md; the npm
// package carrying each skill's build; and npx house-lights <skill> drawing an example of each, with its exit code.
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { checker, checkOneVersion, runNode, skillFrontmatter } from 'chalk-talk/kit/tools/checks.mjs'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const { expect, done } = checker()
const SKILLS = ['chalk-talk', 'back-of-napkin', 'dress-rehearsal', 'gates-and-handoffs', 'service-blueprint']
const json = (f) => JSON.parse(readFileSync(join(repo, f), 'utf8'))

expect(readdirSync(join(repo, 'skills')).sort().join() === [...SKILLS].sort().join(), `the plugin has the five skills (${SKILLS.join(', ')})`)
checkOneVersion(expect, {
  plugin: json('.claude-plugin/plugin.json').version,
  'npm house-lights': json('npm/house-lights/package.json').version,
  ...Object.fromEntries(SKILLS.map((s) => [`${s} SKILL.md`, skillFrontmatter(join(repo, 'skills', s, 'SKILL.md')).version])),
})

// The npm package: each skill's build inside, no SKILL.md.
execFileSync(process.execPath, [join(repo, 'dev/house-lights/tools/pack.mjs')], { stdio: 'ignore' })
const packed = JSON.parse(execFileSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], { cwd: join(repo, 'npm/house-lights'), encoding: 'utf8' }))[0].files.map((f) => f.path)
expect(SKILLS.every((s) => packed.includes(`skills/${s}/scripts/build.mjs`)) && !packed.some((p) => p.endsWith('SKILL.md')), `npm house-lights carries the five builds (${packed.length} files)`)

// npx house-lights <skill> …: an example of each, drawn.
const cli = join(repo, 'npm/house-lights/cli.mjs')
const none = runNode(cli)
expect(none.status === 1 && SKILLS.every((s) => none.stderr.includes(s)), 'house-lights alone lists the five skills (exit 1)', none.stderr)
const odd = runNode(cli, ['stage-door', 'x.way.yaml'])
expect(odd.status === 1 && /no skill named «stage-door»/.test(odd.stderr), 'an old or unknown name is told (exit 1)', odd.stderr)
const ex = (s, f) => join(repo, 'npm/house-lights/skills', s, f)
const work = mkdtempSync(join(tmpdir(), 'house-lights-check-'))
const cases = [
  ['chalk-talk', [ex('chalk-talk', 'references/examples/juros.json'), join(work, 'chalk-talk', 'juros.html'), '--no-review']],
  ['back-of-napkin', [ex('back-of-napkin', 'examples/pitch-pharmacy-queue.chalk'), join(work, 'back-of-napkin', 'pitch.html'), '--no-review']],
  ['dress-rehearsal', [ex('dress-rehearsal', 'examples/checkout.drill.yaml'), '--out', join(work, 'dress-rehearsal')]],
  ['gates-and-handoffs', [ex('gates-and-handoffs', 'examples/scrum.way.yaml'), '--out', join(work, 'gates-and-handoffs')]],
  ['service-blueprint', [ex('service-blueprint', 'examples/gym-signup.blueprint.yaml'), '--out', join(work, 'service-blueprint')]],
]
for (const [s, args] of cases) {
  mkdirSync(join(work, s))
  const r = runNode(cli, [s, ...args])
  let made = []
  try { made = readdirSync(join(work, s)).filter((f) => f.endsWith('.html')) } catch {}
  expect(r.status === 0 && made.length > 0, `npx house-lights ${s} draws an example (${made.join(', ') || 'nothing'})`, r.stdout + r.stderr)
}
rmSync(work, { recursive: true, force: true })

// Every relative link of the front page, the README and each skill's guide points at a file that is there.
const pages = ['docs/index.html', 'README.md', ...SKILLS.map((s) => `dev/${s}/README.md`)]
const broken = pages.flatMap((page) => {
  const text = readFileSync(join(repo, page), 'utf8')
  const links = [...text.matchAll(/(?:href|src)="([^"]+)"|\]\(([^)\s]+)\)/g)].map((m) => (m[1] ?? m[2]).split('#')[0])
    .filter((l) => l && !l.includes(':') && !l.includes('$'))
  return links.filter((l) => !existsSync(join(repo, dirname(page), l))).map((l) => `${page} → ${l}`)
})
expect(!broken.length, `every relative link is there (${pages.length} pages)${broken.length ? ` — not: ${broken.join(', ')}` : ''}`)
done('house-lights')
