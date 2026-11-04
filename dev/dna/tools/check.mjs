// Checks what holds the seven skills together: one version in the plugin, the npm package and every SKILL.md; the npm
// package carrying each skill's build; and npx @ruinosus/dna <skill> drawing an example of each, with its exit code.
import { execFileSync, spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { checker, checkOneVersion, runNode, skillFrontmatter } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const { expect, done } = checker()
const SKILLS = ['visual-explainer', 'visual-pitch', 'incident-drill', 'way-of-working', 'service-blueprint', 'agent-review', 'process-simulation', 'solution']
const json = (f) => JSON.parse(readFileSync(join(repo, f), 'utf8'))

expect(readdirSync(join(repo, 'skills')).sort().join() === [...SKILLS].sort().join(), `the plugin has the eight skills (${SKILLS.join(', ')})`)
checkOneVersion(expect, {
  plugin: json('.claude-plugin/plugin.json').version,
  'npm dna': json('npm/dna/package.json').version,
  ...Object.fromEntries(SKILLS.map((s) => [`${s} SKILL.md`, skillFrontmatter(join(repo, 'skills', s, 'SKILL.md')).version])),
})

// The npm package: each skill's build inside, no SKILL.md.
execFileSync(process.execPath, [join(repo, 'dev/dna/tools/pack.mjs')], { stdio: 'ignore' })
const packed = JSON.parse(execFileSync('npm', ['pack', '--dry-run', '--json', '--ignore-scripts'], { cwd: join(repo, 'npm/dna'), encoding: 'utf8' }))[0].files.map((f) => f.path)
expect(SKILLS.every((s) => packed.includes(`skills/${s}/scripts/build.mjs`)) && !packed.some((p) => p.endsWith('SKILL.md')), `npm dna carries the eight builds (${packed.length} files)`)

// npx @ruinosus/dna <skill> …: an example of each, drawn.
const cli = join(repo, 'npm/dna/cli.mjs')
const none = runNode(cli)
expect(none.status === 1 && SKILLS.every((s) => none.stderr.includes(s)), 'dna alone lists the eight skills (exit 1)', none.stderr)
const odd = runNode(cli, ['stage-door', 'x.way.yaml'])
expect(odd.status === 1 && /no skill named «stage-door»/.test(odd.stderr), 'an old or unknown name is told (exit 1)', odd.stderr)
const ex = (s, f) => join(repo, 'npm/dna/skills', s, f)
const work = mkdtempSync(join(tmpdir(), 'dna-check-'))
const cases = [
  ['visual-explainer', [ex('visual-explainer', 'references/examples/juros.json'), join(work, 'visual-explainer', 'juros.html'), '--no-review']],
  ['visual-pitch', [ex('visual-pitch', 'examples/pitch-pharmacy-queue.chalk'), join(work, 'visual-pitch', 'pitch.html'), '--no-review']],
  ['incident-drill', [ex('incident-drill', 'examples/checkout.drill.yaml'), '--out', join(work, 'incident-drill')]],
  ['way-of-working', [ex('way-of-working', 'examples/scrum.way.yaml'), '--out', join(work, 'way-of-working')]],
  ['service-blueprint', [ex('service-blueprint', 'examples/employee-onboarding.blueprint.yaml'), '--out', join(work, 'service-blueprint')]],
  ['agent-review', [ex('agent-review', 'examples/agents'), '--out', join(work, 'agent-review')]],
  ['process-simulation', [ex('process-simulation', 'examples/hr-help-desk.sim'), '--out', join(work, 'process-simulation')]],
  ['solution', [ex('solution', 'examples/assistant-delivery/assistant-delivery.solution.yaml'), '--out', join(work, 'solution')]],
]
for (const [s, args] of cases) {
  mkdirSync(join(work, s))
  const r = runNode(cli, [s, ...args])
  let made = []
  try { made = readdirSync(join(work, s)).filter((f) => f.endsWith('.html')) } catch {}
  expect(r.status === 0 && made.length > 0, `npx @ruinosus/dna ${s} draws an example (${made.join(', ') || 'nothing'})`, r.stdout + r.stderr)
}
// The mod's commands: none named like one of the plugin's skills — Claude Code refuses it (it is /dna:<skill>)
{
  const names = [...readFileSync(join(repo, 'hooks/register.tsx'), 'utf8').matchAll(/^ {4}name: '([^']+)'/gm)].map((m) => m[1])
  const clash = names.filter((n) => SKILLS.includes(n) || ['agents', 'help', 'clear', 'config', 'plugin', 'skills', 'mcp', 'model'].includes(n))
  expect(names.length >= 9 && !clash.length, `the mod's ${names.length} commands, none named like a skill or a command of Claude Code's own${clash.length ? ` — not: ${clash.join(', ')}` : ''}`)
}

// DNA's header is how a file says what it is now; every file written before it still reads: each kind, written back
// with the format line of before, passes its skill's check
const OLD = [
  ['way-of-working', 'examples/scrum.way.yaml', 'stage-door/v1'],
  ['service-blueprint', 'examples/employee-onboarding.blueprint.yaml', 'front-of-house/v1'],
  ['incident-drill', 'examples/checkout.drill.yaml', 'dress-rehearsal/v1'],
  ['solution', 'examples/assistant-delivery/assistant-delivery.solution.yaml', 'opening-night/v1'],
]
for (const [s, f, format] of OLD) {
  const src = join(repo, 'skills', s, f)
  const text = readFileSync(src, 'utf8')
  const old = text.replace(/^apiVersion: github\.com\/ruinosus\/dna\/v1\nkind: \w+\nmetadata:\n {2}name:/m, `format: ${format}\nname:`)
  expect(old !== text, `${s}: ${f} has DNA's header`)
  if (old !== text) {
    const copy = join(work, `old-${s}-${f.split('/').pop()}`)
    writeFileSync(copy, old)
    for (const p of readdirSync(dirname(src))) if (p !== f.split('/').pop()) try { cpSync(join(dirname(src), p), join(work, p), { recursive: true }) } catch {}
    const r = runNode(join(repo, 'skills', s, 'scripts/build.mjs'), [copy, '--check'])
    expect(r.status === 0, `${s}: a file with «format: ${format}» (from before DNA) still passes its check`, r.stdout + r.stderr)
    const up = runNode(join(repo, 'skills', s, 'scripts/build.mjs'), [copy, '--upgrade'])
    expect(up.status === 0 && up.stdout === text, `${s}: --upgrade gives it DNA's header, the rest as it was`, up.stdout.slice(0, 200) + up.stderr)
  }
}
{
  const prof = readFileSync(join(repo, 'skills/agent-review/examples/team.standard.yaml'), 'utf8')
  const old = prof.replace(/^apiVersion: github\.com\/ruinosus\/dna\/v1\nkind: AgentStandard\nmetadata:\n {2}name:/m, 'format: cast-list/profile-v1\nname:')
  const copy = join(work, 'old-team.standard.yaml')
  writeFileSync(copy, old)
  const r = runNode(join(repo, 'skills/agent-review/scripts/build.mjs'), [join(repo, 'skills/agent-review/examples/agents'), '--check', '--profile', copy])
  expect(old !== prof && r.status === 0 && /38 patterns/.test(r.stdout), 'agent-review: a profile with «format: cast-list/profile-v1» still reads (38 patterns)', r.stdout.slice(0, 300) + r.stderr)
  const up = runNode(join(repo, 'skills/agent-review/scripts/build.mjs'), [copy, '--upgrade'])
  expect(up.status === 0 && up.stdout === prof, 'agent-review: --upgrade gives the profile DNA\'s header', up.stdout.slice(0, 200) + up.stderr)
}
rmSync(work, { recursive: true, force: true })

// What Claude Code and the Copilot clone to install the plugin stays small: the site goes to the gh-pages branch and
// the visual-explainer npm package's built files are made, not kept.
const tracked = execFileSync('git', ['-C', repo, 'ls-files', '-z'], { encoding: 'utf8' }).split('\0').filter(Boolean)
const kept = tracked.filter((f) => f.startsWith('docs/') || /^npm\/visual-explainer\/(?:[^/]+\.js$|scripts\/|assets\/|references\/)/.test(f))
const mb = tracked.reduce((n, f) => n + (existsSync(join(repo, f)) ? statSync(join(repo, f)).size : 0), 0) / 1048576
expect(!kept.length && mb < 25, `main carries only what is installed and built from (${mb.toFixed(1)} MB in ${tracked.length} files)${kept.length ? ` — not: ${kept.slice(0, 5).join(', ')}` : ''}`)

// The mod (hooks/): every test of it — the recipes' and names' guards, process-simulation's guard, /simulate and the preview — in
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
done('dna')
