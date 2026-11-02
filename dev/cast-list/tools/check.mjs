// Checks the skill as a person gets it: the engine's checks (checks/*.check.ts); the example agents make the map, the
// workbook and the cast file and print what to look at — 7 with the example profile, 8 with the demo cast file (what
// people said that the YAML contradicts); a broken profile says its line; a folder with no agent says so; the map
// loads nothing from the internet; and, in a browser, «to look at» opens its fact, a pattern shows the files, the
// role filter leaves the orchestrator out, the tabs open and the downloads work. Run after npm run assets.
import { spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the house-lights repository
const skill = join(repo, 'skills/cast-list')
const cast = join(skill, 'scripts/cast.mjs')
const examples = join(skill, 'examples')
const agents = join(examples, 'agents')
const profile = join(examples, 'profile.cast.yaml')
const work = mkdtempSync(join(tmpdir(), 'cast-list-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [cast, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}
const looks = (out) => (out.match(/^! (to look at|para olhar)/gm) ?? []).length

for (const f of readdirSync(join(root, 'checks')).filter((x) => x.endsWith('.check.ts'))) {
  const r = spawnSync('npx', ['tsx', '--tsconfig', join(here, 'tsconfig.json'), join(root, 'checks', f)], { cwd: here, encoding: 'utf8' })
  ok(r.status === 0, `checks/${f}`, r.stdout + r.stderr)
}

// the examples, with the profile and no cast file yet
const plain = join(work, 'plain')
const a = run(agents, '--profile', profile, '--all', '--lang', 'pt', '--out', plain)
ok(a.status === 0 && ['agents.html', 'agents.xlsx', 'agents.cast.yaml'].every((f) => existsSync(join(plain, f))), 'the examples: map, workbook and cast file', a.stdout + a.stderr)
ok(looks(a.stdout) === 7, `7 to look at (${looks(a.stdout)})`, a.stdout)
const again = run(agents, '--profile', profile, '--out', plain)
ok(again.status === 0 && readFileSync(join(plain, 'agents.cast.yaml'), 'utf8').includes('role: orchestrator'), 'a second run reads the cast file it wrote, and keeps the roles', again.stderr)

// with the demo cast file: what people said, and what was decided
const demo = join(work, 'demo')
mkdirSync(demo)
copyFileSync(join(examples, 'demo.cast.yaml'), join(demo, 'agents.cast.yaml'))
const d = run(agents, '--profile', profile, '--lang', 'pt', '--out', demo)
ok(d.status === 0 && looks(d.stdout) === 8 && d.stdout.includes('mas o YAML não tem'), '8 to look at with the demo cast file, the contradiction first', d.stdout)
ok(readFileSync(join(demo, 'agents.cast.yaml'), 'utf8').includes('# the handoff document says frete escalates'), "the cast file keeps the person's comments")

// what is broken says so
writeFileSync(join(work, 'broken.cast.yaml'), readFileSync(profile, 'utf8').replace('threshold: 0.7', 'threshold: 7'))
const line = readFileSync(join(work, 'broken.cast.yaml'), 'utf8').split('\n').findIndex((l) => l.startsWith('threshold: 7')) + 1
const b = run(agents, '--profile', join(work, 'broken.cast.yaml'), '--out', join(work, 'broken'))
ok(b.status === 1 && b.stderr.includes(`broken.cast.yaml:${line}:`) && !existsSync(join(work, 'broken')), `a broken profile says its line (${line}) and writes nothing`, b.stderr)
mkdirSync(join(work, 'empty'))
const e = run(join(work, 'empty'))
ok(e.status === 1 && /agent\.mcs\.yml/.test(e.stderr), 'a folder with no agent says so (exit 1)', e.stderr)
ok(run(agents, '--lang', 'fr').status === 2 && run(agents, '--nope').status === 2 && run(join(work, 'nowhere')).status === 2, 'bad arguments: exit 2')

const map = readFileSync(join(skill, 'assets/map.html'), 'utf8')
ok(!/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(map), 'the map loads nothing from the internet')

// The map in a browser, by the kit (over the DevTools pipe).
const { runPage, browser } = await import(join(skill, 'scripts/browser.mjs'))
if (!browser()) console.log('• no Chrome here: the map was not opened in a browser')
else {
  const html = readFileSync(join(demo, 'agents.html'), 'utf8').replace('</body>', `<script>
    const got = []; HTMLAnchorElement.prototype.click = function () { got.push(this.download) }
    const errs = []; addEventListener('error', (e) => errs.push(String(e.message)))
    setTimeout(async () => { const q = (s) => document.querySelector(s); const all = (s) => document.querySelectorAll(s); const out = {}
      out.looks = all('[data-look]').length
      q('[data-look="0"]').click(); out.look = q('.cl-detail h3')?.textContent
      q('[data-pattern="node:LogCustomTelemetryEvent"]').click(); out.files = [...all('.cl-detail .cl-file')].map((f) => f.textContent)
      out.lacks = q('.cl-detail')?.textContent.includes('bodega-loja-fisica')
      q('[data-role="specialist"]').click(); out.columns = [...all('.cl-matrix thead th')].map((t) => t.textContent)
      q('[data-get="xlsx"]').click(); q('[data-get="yaml"]').click(); q('[data-get="png"]').click()
      await new Promise((r) => setTimeout(r, 1500))
      q('[data-tab="patterns"]').click(); out.patterns = all('.cl-table tbody tr').length
      q('[data-tab="cast"]').click(); out.cast = all('.cl-agent').length
      q('[data-tab="microsoft"]').click(); out.ms = all('.cl-table tbody tr').length
      q('[data-tab="unknown"]').click(); out.unknown = q('.cl-empty')?.textContent
      out.got = got; out.errs = errs
      const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(p) }, 300)</script></body>`)
  writeFileSync(join(work, 'probe.html'), html)
  const r = (await runPage(join(work, 'probe.html'), 'probe', '', { timeout: 60 })) ?? { errs: ['the page did not answer'] }
  ok(r.looks === 8 && r.look === 'Escalonamento para humano', '«to look at»: its first item opens the fact', JSON.stringify(r))
  ok(r.files?.length === 5 && r.files.every((f) => f.startsWith('topics/OnError.topic.mcs.yml:')) && r.lacks, 'a pattern shows the file and line of each, and who is off it', JSON.stringify(r.files))
  ok(r.columns?.length === 6 && !r.columns.some((c) => c.includes('orquestrador')), 'the role filter leaves the orchestrator out', JSON.stringify(r.columns))
  ok((r.got ?? []).join() === 'agents.xlsx,agents.cast.yaml,agents.png' && !r.errs?.length, 'the downloads: workbook, cast file, PNG — no error', JSON.stringify(r))
  ok(r.patterns === 21 && r.cast === 6 && r.ms === 15 && r.unknown === 'Tudo foi entendido.', 'the tabs: patterns, cast, Microsoft, not understood', JSON.stringify(r))
}

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ cast-list: ${failed} failed`)
  process.exit(1)
}
console.log('✓ cast-list')
