// Checks the skill as a person gets it: the engine's checks (checks/*.check.ts); the example agents make the map, the
// workbook, the lesson (passing chalk-talk's reviewer when there is a browser) and the cast file and print what to look at — 22 with the example profile, 23 with the demo cast file (what
// people said that the YAML contradicts); the workbook filled in comes back (--from, --take); --facts; a clean copy with
// no node_modules runs on Node alone; 18 agents in under 30 s with the network blocked; broken files never stop it; a
// broken profile says its line; a folder with no agent says so; the map loads nothing from the internet; and, in a browser, «to look at» opens its fact, a pattern shows the files, the
// role filter leaves the orchestrator out, the tabs open and the downloads work. Run after npm run assets.
import { spawnSync } from 'node:child_process'
import { cpSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the house-lights repository
const skill = join(repo, 'skills/cast-list')
const cast = join(skill, 'scripts/build.mjs')
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
ok(a.status === 0 && ['agents.html', 'agents.xlsx', 'agents.lesson.html', 'agents.cast.yaml'].every((f) => existsSync(join(plain, f))), 'the examples: map, workbook, lesson and cast file', a.stdout + a.stderr)
ok(/✓ review|• review/.test(a.stdout) && !/! review/.test(a.stdout), "the lesson passes chalk-talk's reviewer (when there is a browser)", a.stdout)
ok(looks(a.stdout) === 22, `22 to look at (${looks(a.stdout)})`, a.stdout)
const again = run(agents, '--profile', profile, '--out', plain)
const kept = readFileSync(join(plain, 'agents.cast.yaml'), 'utf8')
ok(again.status === 0 && kept.includes('role: orchestrator') && /blocks:\n(.*\n)*  - id: links\n    text: \|/.test(kept), 'a second run reads the cast file it wrote, and keeps the roles and the blocks of text', kept.slice(0, 600))

// with the demo cast file: what people said, and what was decided
const demo = join(work, 'demo')
mkdirSync(demo)
copyFileSync(join(examples, 'demo.cast.yaml'), join(demo, 'agents.cast.yaml'))
const d = run(agents, '--profile', profile, '--lang', 'pt', '--out', demo)
ok(d.status === 0 && looks(d.stdout) === 22 + 1 && d.stdout.includes('mas o YAML não tem'), '23 to look at with the demo cast file, the contradiction first', d.stdout)
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

// the way back: the workbook filled in (a line in Declared, «aceito» on telemetry), saved as an .xlsx again
const { readXlsx } = await import(join(skill, 'scripts/read-xlsx.mjs'))
const { workbookFile } = await import(join(skill, 'scripts/engine.mjs'))
run(agents, '--profile', profile, '--xlsx', '--lang', 'pt', '--out', demo)
const sheets = readXlsx(readFileSync(join(demo, 'agents.xlsx')))
sheets.find((x) => x.name === 'Declarado').rows.push(['bodega-frete', 'kpi', 'cotação em menos de 5 s', 'planilha do time'])
const pats = sheets.find((x) => x.name === 'Padrões')
pats.rows.find((r) => r[0] === 'node:LogCustomTelemetryEvent')[pats.rows[0].indexOf('Decisão')] = 'aceito'
writeFileSync(join(work, 'edited.xlsx'), workbookFile(sheets.map((x) => ({ key: 'summary', name: x.name, header: true, columns: (x.rows[0] ?? []).map((t) => ({ title: t, width: 20 })), rows: x.rows }))))
const listed = run(agents, '--from', join(work, 'edited.xlsx'), '--lang', 'pt', '--out', demo)
ok(listed.status === 0 && /^\s+d1\s+\+ declarado\s+bodega-frete · KPI declarado = «cotação em menos de 5 s»/m.test(listed.stdout) && /^\s+p1\s+\+ decisão\s+Registra telemetria: aceito \(plataforma\)/m.test(listed.stdout), '--from lists what was filled in, each with its key', listed.stdout)
ok(run(agents, '--from', join(work, 'edited.xlsx'), '--take', 'zz', '--out', demo).status === 2, '--take with a key that is not there: exit 2')
const took = run(agents, '--from', join(work, 'edited.xlsx'), '--take', 'all', '--lang', 'pt', '--out', demo)
const written = readFileSync(join(demo, 'agents.cast.yaml'), 'utf8')
ok(took.status === 0 && written.includes('cotação em menos de 5 s') && /key: node:LogCustomTelemetryEvent, status: accepted/.test(written) && written.includes('# the handoff document says frete escalates'), '--take all writes them to the cast file, comments kept', written)
const next = run(agents, '--profile', profile, '--check', '--lang', 'pt', '--out', demo)
ok(next.stdout.includes('não registra telemetria (bodega-loja-fisica), e o padrão foi aceito: corrigir?') && next.stdout.includes('3 especialistas não cumprem'), 'the next run checks the accepted pattern, and counts the declared KPI', next.stdout)

// the facts, for a model
const f = run(agents, '--facts', '--out', join(work, 'facts'))
const facts = JSON.parse(readFileSync(join(work, 'facts', 'agents.facts.json'), 'utf8'))
ok(f.status === 0 && facts.format === 'cast-list/facts-v1' && facts.agents.length === 6 && facts.agents.find((x) => x.id === 'bodega-frete').facts['trigger:OnUnknownIntent'][0].file === 'topics/Fallback.topic.mcs.yml', '--facts: each agent, its facts with file and line', f.stderr)

// a clean copy of the skill, with no node_modules anywhere above it, runs on Node alone
const clean = join(work, 'clean')
cpSync(skill, join(clean, 'cast-list'), { recursive: true })
const c = spawnSync(process.execPath, [join(clean, 'cast-list/scripts/build.mjs'), join(clean, 'cast-list/examples/agents'), '--all', '--out', join(clean, 'out')], { encoding: 'utf8', cwd: clean })
ok(c.status === 0 && existsSync(join(clean, 'out/agents.html')) && existsSync(join(clean, 'out/agents.xlsx')) && existsSync(join(clean, 'out/agents.lesson.html')), 'a clean copy, no node_modules: map, workbook and lesson on Node alone', c.stdout + c.stderr)

// 18 agents (the examples three times over) in under 30 s, with no network: any connection throws
const many = join(work, 'many')
for (const n of [1, 2, 3]) for (const d of readdirSync(agents)) cpSync(join(agents, d), join(many, `${d}-${n}`), { recursive: true })
writeFileSync(join(work, 'no-net.mjs'), "import net from 'node:net'\nnet.Socket.prototype.connect = () => { throw new Error('cast-list must not use the network') }\nglobalThis.fetch = () => { throw new Error('cast-list must not use the network') }\n")
const start = Date.now()
const m = spawnSync(process.execPath, ['--import', join(work, 'no-net.mjs'), cast, many, '--all', '--out', join(work, 'many-out')], { encoding: 'utf8' })
const took18 = (Date.now() - start) / 1000
ok(m.status === 0 && m.stdout.includes('18 in the cast') && took18 < 30, `18 agents with no network: done in ${took18.toFixed(1)} s`, m.stdout + m.stderr)

// what cannot be read never stops it
const odd = join(work, 'odd/strange')
mkdirSync(join(odd, 'topics'), { recursive: true })
writeFileSync(join(odd, 'agent.mcs.yml'), 'kind: GptComponentMetadata\ninstructions: Seja breve.\n')
writeFileSync(join(odd, 'topics/Broken.topic.mcs.yml'), 'kind: AdaptiveDialog\nbeginDialog: [unclosed\n')
writeFileSync(join(odd, 'topics/Empty.topic.mcs.yml'), '')
writeFileSync(join(odd, 'topics/Made.topic.mcs.yaml'), 'kind: AdaptiveDialog\nbeginDialog:\n  kind: OnInventado\n')
writeFileSync(join(odd, 'notes.txt'), 'loose')
mkdirSync(join(odd, '.mcs'))
writeFileSync(join(odd, '.mcs/conn.json'), '{"never": "read"}')
const o = run(join(work, 'odd'), '--all', '--lang', 'pt', '--out', join(work, 'odd-out'))
ok(o.status === 0 && o.stdout.includes('strange: a análise não entendeu 4 arquivos') && !o.stdout.includes('conn.json'), 'broken, empty, made-up and loose files: told, never stopping it; .mcs/ never read', o.stdout + o.stderr)

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
      q('[data-role="specialist"]').click(); out.columns = [...all('.cl-matrix thead th[scope=col]')].map((t) => t.textContent)
      q('[data-get="xlsx"]').click(); q('[data-get="yaml"]').click(); q('[data-get="png"]').click()
      await new Promise((r) => setTimeout(r, 1500))
      q('[data-tab="patterns"]').click(); out.patterns = all('.cl-table tbody tr').length
      q('[data-tab="cast"]').click(); out.cast = all('.cl-agent').length
      q('[data-tab="microsoft"]').click(); out.ms = all('.cl-table tbody tr').length
      q('[data-tab="unknown"]').click(); out.unknown = q('.cl-empty')?.textContent
      q('[data-tab="cast"]').click()
      const card = (id) => [...all('.cl-agent')].find((c) => c.querySelector('h3')?.textContent === id)
      out.chain = card('bodega-pedidos')?.querySelector('.cl-chain')?.textContent.trim()
      out.silent = card('bodega-cupons')?.querySelector('.cl-chain .cl-silent')?.textContent
      out.routing = card('bodega-orquestrador')?.querySelectorAll('.cl-routing tbody tr').length
      q('[data-tab="unused"]').click(); out.unused = all('.cl-table tbody tr').length
      out.got = got; out.errs = errs
      const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(p) }, 300)</script></body>`)
  writeFileSync(join(work, 'probe.html'), html)
  const r = (await runPage(join(work, 'probe.html'), 'probe', '', { timeout: 60 })) ?? { errs: ['the page did not answer'] }
  ok(r.looks === 23 && r.look === 'Escalonamento para humano', '«to look at»: its first item opens the fact', JSON.stringify(r))
  ok(r.files?.length === 5 && r.files.every((f) => f.startsWith('topics/OnError.topic.mcs.yml:')) && r.lacks, 'a pattern shows the file and line of each, and who is off it', JSON.stringify(r.files))
  ok(r.columns?.length === 6 && r.columns.filter((c) => c.startsWith('bodega-cupons')).length === 2 && !r.columns.some((c) => c.includes('orquestrador')), 'the role filter leaves the orchestrator out (cupons in its two types)', JSON.stringify(r.columns))
  ok((r.got ?? []).join() === 'agents.xlsx,agents.cast.yaml,agents.png' && !r.errs?.length, 'the downloads: workbook, cast file, PNG — no error', JSON.stringify(r))
  ok(r.chain === 'Bodega Azul - Pedidos → Abrir chamado no ERP → erp.bodega-azul.example' && r.silent === '— não devolve nada', 'the cast: the chain of pedidos, and the flow of cupons that returns nothing', JSON.stringify([r.chain, r.silent]))
  ok(r.routing === 6 && r.unused === 4 && !r.errs?.length, 'the orchestrator\'s routing, 6 calls; the Unused tab, 4 rows; no error', JSON.stringify([r.routing, r.unused, r.errs]))
  ok(r.patterns === 31 && r.cast === 6 && r.ms === 15 && r.unknown === 'Tudo foi entendido.', 'the tabs: patterns, cast, Microsoft, not understood', JSON.stringify(r))
}

// wave 1 in a browser: the example profile has markers, an official block and types
if (browser()) {
  const w1 = join(work, 'w1')
  mkdirSync(w1)
  const t = run(agents, '--profile', profile, '--html', '--lesson', '--lang', 'pt', '--out', w1)
  ok(t.status === 0 && /✓ review/.test(t.stdout), "the examples with the wave 1 profile: the map, and the lesson by type passing chalk-talk's reviewer", t.stdout + t.stderr)
  const page = readFileSync(join(w1, 'agents.html'), 'utf8').replace('</body>', `<script>
    const errs = []; addEventListener('error', (e) => errs.push(String(e.message)))
    setTimeout(() => { const q = (s) => document.querySelector(s); const all = (s) => [...document.querySelectorAll(s)]; const out = {}
      out.groups = all('.cl-groups th').map((t) => t.textContent).filter(Boolean)
      out.cupons = all('.cl-matrix thead th[scope=col]').filter((t) => t.textContent.startsWith('bodega-cupons')).map((t) => t.textContent)
      out.variant = all('.cl-mark.var').length
      out.typeBadge = all('.cl-badge.type').length
      out.officialBadge = all('.cl-badge.official').length
      q('[data-type="transaction"]').click(); out.transaction = all('.cl-matrix thead th[scope=col]').map((t) => t.textContent.replace(/(especialista|também em).*/, ''))
      q('[data-type=""]').click()
      q('.cl-fact[data-key="text:block:links"]').click(); out.text = q('.cl-detail .cl-text')?.textContent.slice(0, 6); out.variants = all('.cl-detail .cl-variant').length
      out.del = all('.cl-detail .cl-del').map((x) => x.textContent); out.add = all('.cl-detail .cl-add').map((x) => x.textContent)
      out.errs = errs
      const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(p) }, 300)</script></body>`)
  writeFileSync(join(w1, 'probe.html'), page)
  const x = (await runPage(join(w1, 'probe.html'), 'probe', '', { timeout: 60 })) ?? { errs: ['the page did not answer'] }
  ok((x.groups ?? []).join() === 'orquestrador,transação,orientação,triagem' && (x.cupons ?? []).length === 2 && x.cupons.some((c) => c.includes('também em')), 'the matrix by type: cupons in two groups, «também em»', JSON.stringify(x))
  ok((x.transaction ?? []).join() === 'bodega-cupons,bodega-devolucoes,bodega-pedidos', 'the type filter: transação keeps its three', JSON.stringify(x.transaction))
  ok(x.variant >= 1 && x.typeBadge >= 1 && x.officialBadge >= 1, '≈ for a variation, the type badge, the official block badge', JSON.stringify(x))
  ok(x.text === 'Links:' && x.variants === 1 && (x.del ?? []).some((d) => d.includes('link de ação vai no topo')) && (x.del ?? []).includes('3') && (x.add ?? []).includes('5') && !x.errs?.length, "the block's detail: its text, frete's variation word by word", JSON.stringify(x))
}

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ cast-list: ${failed} failed`)
  process.exit(1)
}
console.log('✓ cast-list')
