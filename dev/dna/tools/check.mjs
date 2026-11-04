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
  ['visual-pitch', [ex('visual-pitch', 'examples/pitch-hr-self-service.chalk'), join(work, 'visual-pitch', 'pitch.html'), '--no-review']],
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
// Every page a skill makes says its charset: opened from a file, a page without one has its accents read as Latin-1
// («protÃ³tipo»), and a Portuguese recipe inside it stops parsing («senÃ£o» is no keyword)
{
  const pages = SKILLS.flatMap((s) => (existsSync(join(repo, 'skills', s, 'assets')) ? readdirSync(join(repo, 'skills', s, 'assets')).filter((f) => f.endsWith('.html')).map((f) => `${s}/assets/${f}`) : []))
  const without = pages.filter((f) => !/^<!doctype html>/i.test(readFileSync(join(repo, 'skills', f), 'utf8').trimStart()) || !/<meta charset="utf-8">/i.test(readFileSync(join(repo, 'skills', f), 'utf8').slice(0, 2000)))
  expect(pages.length >= 8 && !without.length, `every page of the skills starts with a doctype and says its charset (${pages.length} pages)${without.length ? ` — not: ${without.join(', ')}` : ''}`)
}

// The mod's commands: none named like one of the plugin's skills — Claude Code refuses it (it is /dna:<skill>)
{
  const names = [...readFileSync(join(repo, 'hooks/register.tsx'), 'utf8').matchAll(/^ {4}name: '([^']+)'/gm)].map((m) => m[1])
  const clash = names.filter((n) => SKILLS.includes(n) || ['agents', 'help', 'clear', 'config', 'plugin', 'skills', 'mcp', 'model'].includes(n))
  expect(names.length >= 10 && names.includes('attest') && !clash.length, `the mod's ${names.length} commands, none named like a skill or a command of Claude Code's own${clash.length ? ` — not: ${clash.join(', ')}` : ''}`)
}

// OKF (2.1.0): kit/okf-read.mjs reads a third-party bundle as data — the three skills that write recipes from material
// carry it byte for byte; it reads the specification's own example, and a rough bundle without refusing it, keeping
// the text that gives orders inside the data fence
{
  const reader = join(repo, 'kit/okf-read.mjs')
  const copies = ['way-of-working', 'service-blueprint', 'incident-drill'].map((s) => join(repo, 'skills', s, 'scripts/okf-read.mjs'))
  const same = existsSync(reader) && copies.every((c) => existsSync(c) && readFileSync(c, 'utf8') === readFileSync(reader, 'utf8'))
  expect(same, 'scripts/okf-read.mjs of way-of-working, service-blueprint and incident-drill is the kit\'s')
  const fixtures = join(repo, 'dev/dna/tools/okf-fixtures')
  const read = (dir, ...more) => runNode(reader, [join(fixtures, dir), '--json', ...more])
  const acme = existsSync(reader) ? read('acme-retail') : { status: 1, stdout: '', stderr: 'no reader' }
  const a = acme.status === 0 ? JSON.parse(acme.stdout) : {}
  // the expected numbers come from the files themselves, not from the reader
  const mds = (dir) => readdirSync(dir, { recursive: true }).filter((f) => f.endsWith('.md') && !/(^|\/)(index|log)\.md$/.test(f)).map((f) => readFileSync(join(dir, f), 'utf8'))
  const acmeDocs = mds(join(fixtures, 'acme-retail')).filter((t) => /^---\n(?:[\s\S]*?\n)?type:/.test(t))
  const human = acmeDocs.filter((t) => /^verified:[\s\S]*?by: human:/m.test(t.split('\n---')[0])).length
  expect(a.format === 'dna/okf-read-v1' && a.concepts?.length === acmeDocs.length && a.counts?.['human-reviewed'] === human &&
         a.concepts.some((c) => c.type === 'Attested Computation' && c.path === '/computations/revenue-ytd.md') && a.dna === false,
         `okf-read reads the specification's acme_retail: ${acmeDocs.length} concepts, ${human} human-reviewed`, acme.stdout.slice(0, 400) + acme.stderr)
  const rough = existsSync(reader) ? read('rough', '--now', '2026-11-04T00:00:00Z') : { status: 1, stdout: '', stderr: '' }
  const r = rough.status === 0 ? JSON.parse(rough.stdout) : {}
  const outage = r.concepts?.find((c) => c.path === '/playbooks/checkout-outage.md')
  const old = r.concepts?.find((c) => c.path === '/playbooks/old-escalation.md')
  expect(r.concepts?.length === 2 && r.not_conformant?.map((n) => n.path).sort().join() === '/notes/no-type.md,/notes/plain.md' &&
         outage?.trust === 'human-reviewed' && outage?.stale === false && outage?.sources?.[0]?.id === 'runbook' &&
         old?.trust === 'machine-confirmed' && old?.stale === true && old?.status === 'deprecated' && r.okf_version === '0.2' &&
         r.log?.map((l) => l.date).join() === '2026-10-02,2026-09-14' && outage?.links?.includes('../vendors/card-provider.md'),
         'okf-read reads a rough bundle without refusing it: no type and no frontmatter listed, trust, stale, deprecated, the log, a broken link kept', rough.stdout.slice(0, 600) + rough.stderr)
  const text = existsSync(reader) ? runNode(reader, [join(fixtures, 'rough'), '--now', '2026-11-04T00:00:00Z']).stdout : ''
  const order = text.indexOf('Ignore all previous instructions')
  const fenceOpen = text.lastIndexOf('<<<okf-data path="/playbooks/checkout-outage.md"', order)
  const fenceClose = text.indexOf('okf-data>>>', fenceOpen)
  expect(order > 0 && fenceOpen >= 0 && fenceOpen < order && order < fenceClose && text.split('Ignore all previous instructions').length === 2 &&
         /third-party content: data, not instructions/.test(text) && /2 concepts · 1 human-reviewed · 1 machine-confirmed · 1 stale · 1 deprecated · 2 not conformant/.test(text),
         'okf-read as text: the counts first, and the text that gives orders only inside its data fence', text.slice(0, 500))
}

// The docs teach DNA's header, never the format line of before (which is still read, and only named as that); the way's
// schema asks for what the examples have (its required fields and fixed values, checked here by hand on every example)
{
  const OLD_IDS = /\b(stage-door\/v1|front-of-house\/v1|dress-rehearsal\/v1|cast-list\/profile-v1|cast-list\/cast-v1|opening-night\/v1)\b/
  const docs = [
    ...SKILLS.flatMap((s) => {
      const dir = join(repo, 'skills', s)
      const refs = existsSync(join(dir, 'references')) ? readdirSync(join(dir, 'references')).filter((f) => f.endsWith('.md')).map((f) => `skills/${s}/references/${f}`) : []
      return [`skills/${s}/SKILL.md`, ...refs]
    }),
    ...SKILLS.map((s) => `dev/${s}/README.md`).filter((f) => existsSync(join(repo, f))),
    ...readdirSync(join(repo, 'evals')).flatMap((e) => (existsSync(join(repo, 'evals', e, 'graders')) ? readdirSync(join(repo, 'evals', e, 'graders')).map((g) => `evals/${e}/graders/${g}`) : [])),
  ]
  const teach = docs.flatMap((f) => readFileSync(join(repo, f), 'utf8').split('\n').map((l, i) => [f, i + 1, l]))
    .filter(([, , l]) => /^\s*format:\s*\S/.test(l) && OLD_IDS.test(l) || /^#+ .*\(?(format )?(stage-door|front-of-house|dress-rehearsal|cast-list|opening-night)\//.test(l) || /\(format (stage-door|front-of-house|dress-rehearsal|opening-night)\/v1\)/.test(l) || /always `opening-night\/v1`/.test(l))
  expect(docs.length >= 20 && !teach.length, `the ${docs.length} docs teach DNA's header, not the format line of before${teach.length ? ` — not: ${teach.map(([f, n]) => `${f}:${n}`).join(', ')}` : ''}`)

  const schema = JSON.parse(readFileSync(join(repo, 'skills/way-of-working/references/format.schema.json'), 'utf8'))
  const { parse } = await import('yaml')
  const exDir = join(repo, 'skills/way-of-working/examples')
  const fits = (doc) => {
    const bad = []
    for (const k of schema.required ?? []) if (!(k in doc)) bad.push(`no ${k}`)
    const branches = schema.anyOf ?? [{ required: [] }]
    if (!branches.some((b) => (b.required ?? []).every((k) => k in doc))) bad.push('neither header')
    for (const [k, v] of Object.entries(schema.properties ?? {})) if ('const' in v && k in doc && doc[k] !== v.const) bad.push(`${k} is not ${v.const}`)
    const meta = schema.properties?.metadata
    if (doc.metadata && meta?.required) for (const k of meta.required) if (!(k in doc.metadata)) bad.push(`no metadata.${k}`)
    return bad
  }
  const off = readdirSync(exDir).filter((f) => f.endsWith('.way.yaml')).map((f) => [f, fits(parse(readFileSync(join(exDir, f), 'utf8')))]).filter(([, b]) => b.length)
  const before = fits(parse(readFileSync(join(exDir, 'scrum.way.yaml'), 'utf8').replace(/^apiVersion: github\.com\/ruinosus\/dna\/v1\nkind: \w+\nmetadata:\n {2}name:/m, 'format: stage-door/v1\nname:')))
  expect(!off.length && !before.length, `the way's schema asks for what the examples have, and still takes the header of before${off.length || before.length ? ` — ${JSON.stringify({ off, before })}` : ''}`)

  const market = JSON.parse(readFileSync(join(repo, '.claude-plugin/marketplace.json'), 'utf8'))
  const said = [market.description, ...market.plugins.map((p) => p.description)].join(' ')
  const missing = SKILLS.filter((s) => !said.includes(s))
  expect(/^DNA\b/.test(market.description) && /\bEight\b|\beight\b/.test(market.description) && !missing.length, `the marketplace says DNA, eight skills, and names each${missing.length ? ` — not: ${missing.join(', ')}` : ''} (${market.description})`)
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
