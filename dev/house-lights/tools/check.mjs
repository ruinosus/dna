// Checks what holds the seven skills together: one version in the plugin, the npm package and every SKILL.md; the npm
// package carrying each skill's build; and npx house-lights <skill> drawing an example of each, with its exit code.
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { checker, checkOneVersion, runNode, skillFrontmatter } from 'chalk-talk/kit/tools/checks.mjs'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const { expect, done } = checker()
const SKILLS = ['chalk-talk', 'back-of-napkin', 'dress-rehearsal', 'gates-and-handoffs', 'service-blueprint', 'cast-list', 'box-office', 'opening-night']
const json = (f) => JSON.parse(readFileSync(join(repo, f), 'utf8'))

expect(readdirSync(join(repo, 'skills')).sort().join() === [...SKILLS].sort().join(), `the plugin has the eight skills (${SKILLS.join(', ')})`)
checkOneVersion(expect, {
  plugin: json('.claude-plugin/plugin.json').version,
  'npm house-lights': json('npm/house-lights/package.json').version,
  ...Object.fromEntries(SKILLS.map((s) => [`${s} SKILL.md`, skillFrontmatter(join(repo, 'skills', s, 'SKILL.md')).version])),
})

// The npm package: each skill's build inside, no SKILL.md.
execFileSync(process.execPath, [join(repo, 'dev/house-lights/tools/pack.mjs')], { stdio: 'ignore' })
const packed = JSON.parse(execFileSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], { cwd: join(repo, 'npm/house-lights'), encoding: 'utf8' }))[0].files.map((f) => f.path)
expect(SKILLS.every((s) => packed.includes(`skills/${s}/scripts/build.mjs`)) && !packed.some((p) => p.endsWith('SKILL.md')), `npm house-lights carries the eight builds (${packed.length} files)`)

// npx house-lights <skill> …: an example of each, drawn.
const cli = join(repo, 'npm/house-lights/cli.mjs')
const none = runNode(cli)
expect(none.status === 1 && SKILLS.every((s) => none.stderr.includes(s)), 'house-lights alone lists the eight skills (exit 1)', none.stderr)
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
  ['cast-list', [ex('cast-list', 'examples/agents'), '--out', join(work, 'cast-list')]],
  ['box-office', [ex('box-office', 'examples/corner-cafe.sim'), '--out', join(work, 'box-office')]],
  ['opening-night', [ex('opening-night', 'examples/assistant-delivery/assistant-delivery.solution.yaml'), '--out', join(work, 'opening-night')]],
]
for (const [s, args] of cases) {
  mkdirSync(join(work, s))
  const r = runNode(cli, [s, ...args])
  let made = []
  try { made = readdirSync(join(work, s)).filter((f) => f.endsWith('.html')) } catch {}
  expect(r.status === 0 && made.length > 0, `npx house-lights ${s} draws an example (${made.join(', ') || 'nothing'})`, r.stdout + r.stderr)
}
rmSync(work, { recursive: true, force: true })

// What Claude Code and the Copilot clone to install the plugin stays small: the site goes to the gh-pages branch and
// the chalk-talk npm package's built files are made, not kept.
const tracked = execFileSync('git', ['-C', repo, 'ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean)
const kept = tracked.filter((f) => f.startsWith('docs/') || /^npm\/chalk-talk\/(?:[^/]+\.js$|scripts\/|assets\/|references\/)/.test(f))
const mb = tracked.reduce((n, f) => n + (existsSync(join(repo, f)) ? statSync(join(repo, f)).size : 0), 0) / 1048576
expect(!kept.length && mb < 25, `main carries only what is installed and built from (${mb.toFixed(1)} MB in ${tracked.length} files)${kept.length ? ` — not: ${kept.slice(0, 5).join(', ')}` : ''}`)

// The mod (hooks/): every test of it — the recipes' and names' guards, box-office's guard, /sim and the preview — in
// Claude Code's own harness, when Claude Code is here.
const claude = spawnSync('claude', ['--version'], { encoding: 'utf8' })
if (claude.status !== 0) console.log('• no Claude Code here: the mod was not tested')
else {
  const t = spawnSync('claude', ['plugin', 'test', repo], { encoding: 'utf8', timeout: 300000 })
  const pass = Number((t.stdout.match(/(\d+) pass/) ?? [])[1] ?? 0)
  const fail = Number((t.stdout.match(/(\d+) fail/) ?? [])[1] ?? 0)
  expect(t.status === 0 && pass >= 25 && fail === 0, `the mod in Claude Code's harness: ${pass} tests pass, ${fail} fail`, t.stdout + t.stderr)
}

// Every relative link of the front page, the README and each skill's guide points at a file that is there.
// the site's front page only once npm run site has made it (docs/ is not kept in git)
const pages = [...(existsSync(join(repo, 'docs/index.html')) ? ['docs/index.html'] : []), 'README.md', ...SKILLS.map((s) => `dev/${s}/README.md`)]
const broken = pages.flatMap((page) => {
  const text = readFileSync(join(repo, page), 'utf8')
  const links = [...text.matchAll(/(?:href|src)="([^"]+)"|\]\(([^)\s]+)\)/g)].map((m) => (m[1] ?? m[2]).split('#')[0])
    .filter((l) => l && !l.includes(':') && !l.includes('$'))
  return links.filter((l) => !existsSync(join(repo, dirname(page), l))).map((l) => `${page} → ${l}`)
})
expect(!broken.length, `every relative link is there (${pages.length} pages)${broken.length ? ` — not: ${broken.join(', ')}` : ''}`)
done('house-lights')
