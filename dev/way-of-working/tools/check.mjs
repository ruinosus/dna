// Checks the skill as a person gets it: every example makes its map, workbook and explainer (the explainer passing visual-explainer's
// reviewer when there is a browser); the workbook it made reads back as no change; a broken file says its line; the map
// needs nothing from the internet; and, when LibreOffice is here, the workbook opens in it. Run after npm run assets.
import { checkNoOldName, checkSkillMd } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'
import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const skill = resolve(here, '../../../skills/way-of-working')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
// The language each example is written in.
const LANG = { 'feature-delivery': 'pt', scrum: 'en', 'service-desk': 'pt', 'initiative-portfolio': 'pt' }
const work = mkdtempSync(join(tmpdir(), 'way-of-working-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}
checkSkillMd(ok, join(skill, 'SKILL.md'), 'way-of-working')

const files = readdirSync(examples).filter((f) => f.endsWith('.way.yaml'))
ok(files.length === Object.keys(LANG).length, `${files.length} examples`)
for (const f of files) {
  const id = f.replace('.way.yaml', '')
  const lang = LANG[id] ?? 'en'
  const r = run(join(examples, f), '--all', '--lang', lang, '--out', work)
  const made = ['html', 'xlsx', 'explainer.html'].every((ext) => existsSync(join(work, `${id}.${ext}`)))
  ok(r.status === 0 && made, `${id}: map, workbook and explainer`, r.stdout + r.stderr)

  // DNA 2.2.0: the explainer as Markdown too — its recipe in a ```visual-explainer block a preview with DNA draws
  const md = existsSync(join(work, `${id}.explainer.md`)) ? readFileSync(join(work, `${id}.explainer.md`), 'utf8') : ''
  const block = /^```visual-explainer\n([\s\S]*?)\n```$/m.exec(md)?.[1]
  ok(!!block && JSON.parse(block).steps?.length > 0 && md.includes(`${id}.explainer.html`), `${id}: ${id}.explainer.md, the explainer in a visual-explainer block`, md.slice(0, 300))
  ok(!/^! (to look at|para olhar)/m.test(r.stdout), `${id}: nothing to look at`, r.stdout)
  if (f === files[0]) {
    mkdirSync(join(work, 'old'), { recursive: true })
    const old = run(join(examples, f), '--lesson', '--lang', lang, '--out', join(work, 'old'))
    ok(old.status === 0 && existsSync(join(work, 'old', `${id}.explainer.html`)), `${id}: --lesson, the flag before 2.2.0, still writes the explainer`, old.stdout + old.stderr)
  }
  // the workbook it made, read back: no change
  const way = join(work, f)
  copyFileSync(join(examples, f), way)
  const back = run(way, '--from', join(work, `${id}.xlsx`), '--lang', 'en')
  ok(back.status === 0 && back.stdout.includes('the workbook changes nothing'), `${id}: the workbook reads back as no change`, back.stdout + back.stderr)
}

// the thread back: the person says an input from outside comes from inside after all, in the workbook
{
  const engine = await import(join(skill, 'scripts/engine.mjs'))
  const file = join(work, 'initiative-portfolio.way.yaml')
  copyFileSync(join(examples, 'initiative-portfolio.way.yaml'), file)
  const read = engine.readWay(readFileSync(file, 'utf8'))
  const sheets = engine.workbookOf(read.name, read.def, 'pt')
  const stages = sheets.find((x) => x.key === 'stages')
  const at = stages.rows[0].findIndex((c) => (c.v ?? c) === 'Entra')
  stages.rows.find((r) => (r[3].v ?? r[3]) === 'Descoberta')[at] = 'Hipótese registrada (Ideia); Dados de atendimento'
  writeFileSync(join(work, 'edited.xlsx'), engine.xlsx(sheets))
  const back = run(file, '--from', join(work, 'edited.xlsx'), '--lang', 'en')
  ok(back.status === 0 && back.stdout.includes('stage:descoberta:outside') && back.stdout.includes('1 change'), 'an input’s origin changed in the workbook comes back as one change', back.stdout + back.stderr)
}

// a broken file: the line of the problem, nothing written
const broken = join(work, 'broken.way.yaml')
writeFileSync(broken, readFileSync(join(examples, 'scrum.way.yaml'), 'utf8').replace('lane: team\n    roles:\n      - dev\n      - po', 'lane: marketing\n    roles:\n      - dev\n      - po'))
const line = readFileSync(broken, 'utf8').split('\n').findIndex((l) => l.includes('lane: marketing')) + 1
const bad = run(broken)
ok(bad.status === 1 && bad.stderr.includes(`broken.way.yaml:${line}:`) && !existsSync(join(work, 'broken.html')), `a broken file says its line (${line})`, bad.stderr)

// the map opens with no internet: nothing loaded from elsewhere
const map = readFileSync(join(skill, 'assets/map.html'), 'utf8')
ok(!/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(map) && !/@import\s+url\(\s*["']?https?:/i.test(map), 'the map loads nothing from the internet')

// the workbook in LibreOffice, when it is here
const office = ['soffice', 'libreoffice', '/Applications/LibreOffice.app/Contents/MacOS/soffice'].find((p) => p.startsWith('/') ? existsSync(p) : spawnSync('which', [p]).status === 0)
if (!office) console.log('• LibreOffice is not here: the workbook was not opened in it')
else {
  const id = 'feature-delivery'
  execFileSync(office, ['--headless', '--convert-to', 'csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,2', '--outdir', work, join(work, `${id}.xlsx`)], { stdio: 'ignore', timeout: 120000 })
  const csv = readdirSync(work).filter((f) => f.startsWith(id) && f.endsWith('.csv'))
  ok(csv.length >= 7 && readFileSync(join(work, csv.find((f) => /Etapas/.test(f)) ?? csv[0]), 'utf8').includes('Protótipo'), `LibreOffice opens the workbook (${csv.length} sheets)`)
}

// Spec 2026-11-02 (aprovações no gate): «a change to payments also needs security's OK» is a second approval with its
// condition (feature-delivery has it); written as a second gate after the stage, it is refused with the way to say it
{
  const two = join(work, 'two-gates.way.yaml')
  const text = readFileSync(join(examples, 'feature-delivery.way.yaml'), 'utf8')
  writeFileSync(two, text.replace('  - id: producao-gate\n', '  - id: seguranca-gate\n    after: testar\n    name: Segurança ok?\n    approver: seg\n    results:\n      - id: ok\n        label: ok\n        ok: true\n  - id: producao-gate\n'))
  const r = run(two)
  ok(r.status === 1 && r.stderr.includes('Another approval on the same gate? use approvals:, with when: for the condition'), 'two gates after a stage: refused, pointing to approvals', r.stderr)
  // the other examples (only approver) keep their workbook as it was: no «When» column, a row per gate
  const { readWay, workbookOf } = await import(pathToFileURL(join(skill, 'scripts/engine.mjs')).href)
  for (const f of files.filter((x) => x !== 'feature-delivery.way.yaml')) {
    const w = readWay(readFileSync(join(examples, f), 'utf8')).def
    const rows = workbookOf('x', w, 'pt').find((x) => x.key === 'gates').rows
    ok(!rows[0].some((c) => ['Quando', 'When'].includes(typeof c === 'object' ? c.v : c)) && rows.length - 1 === w.gates.length, `${f}: the gates sheet as it was`)
  }
  // in a browser: the gate says «+ SEG se mudança em pagamento», and its detail lists both approvals
  const { runPage, browser } = await import(pathToFileURL(join(skill, 'scripts/browser.mjs')).href)
  if (!browser()) console.log('• no Chrome here: the map was not opened in a browser')
  else {
    run(join(examples, 'feature-delivery.way.yaml'), '--lang', 'pt', '--out', work)
    const html = readFileSync(join(work, 'feature-delivery.html'), 'utf8').replace('</body>', `<script>setTimeout(() => { const q = (s) => document.querySelector(s); const out = {}
      const g = q('[data-gate="producao-gate"]'); out.gate = g?.textContent.replace(/\\s+/g, ' ').trim(); g?.click()
      setTimeout(() => { out.approvals = [...document.querySelectorAll('.sd-approval')].map((x) => x.textContent.replace(/\\s+/g, ' ').trim())
        // as the side panel of a wide screen (300 px), with a long condition: nothing goes past the card's edge
        const d = q('.sd-detail'); d.style.width = '300px'; d.style.boxSizing = 'border-box'
        const cond = d.querySelector('.sd-approval .sd-where'); if (cond) cond.textContent += ' ou com dado de colaborador de outro país'
        const edge = d.getBoundingClientRect().right - parseFloat(getComputedStyle(d).paddingRight) + 1
        out.spills = [...d.querySelectorAll('*')].filter((e) => e.getBoundingClientRect().right > edge).map((e) => e.className || e.tagName).slice(0, 5)
        const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(p) }, 200) }, 300)</script></body>`)
    writeFileSync(join(work, 'probe.html'), html)
    const p = (await runPage(join(work, 'probe.html'), 'probe', '', { timeout: 60 })) ?? {}
    ok(p.gate === 'Pronto para produção? · TL+ SEG se mudança em pagamento' && p.approvals?.length === 2 && p.approvals[0] === 'TL Tech Lead sempre' && p.approvals[1] === 'SEG Segurança se mudança em pagamento', 'the map: the gate and its two approvals', JSON.stringify(p))
    ok(Array.isArray(p.spills) && !p.spills.length, 'the gate in the side panel (300 px): its approvals and a long condition wrap inside the card', JSON.stringify(p.spills))
  }
}

// --check --json: what was read, as one JSON document — what the mod's preview pane draws
{
  const j = spawnSync(process.execPath, [join(skill, 'scripts/build.mjs'), join(skill, 'examples/feature-delivery.way.yaml'), '--check', '--json'], { encoding: 'utf8' })
  let doc
  try { doc = JSON.parse(j.stdout) } catch {}
  ok(j.status === 0 && doc?.format === 'way-of-working/read-v1' && Array.isArray(doc.way?.stages) && Array.isArray(doc.looks), '--check --json: the way as read, and what to look at, as one JSON document', j.stdout.slice(0, 200) + j.stderr)
}
// --lens: each example seen by the other skills — a .sim, a blueprint and a drill, each passing its own skill's check;
// the version of the way at the top; a lens beside it that differs is not written over without --force
{
  const lensDir = join(work, 'lenses')
  mkdirSync(lensDir)
  for (const f of files) {
    const way = join(lensDir, f)
    copyFileSync(join(examples, f), way)
    for (const kind of ['sim', 'blueprint', 'drill']) {
      const r = run(way, '--lens', kind, '--lang', LANG[f.replace('.way.yaml', '')], '--write')
      ok(r.status === 0 && /^ {2}✓/m.test(r.stdout) && !/✗/.test(r.stdout), `--lens ${kind} of ${f}: written and passes ${{ sim: 'process-simulation', blueprint: 'service-blueprint', drill: 'incident-drill' }[kind]}'s check`, r.stdout + r.stderr)
    }
  }
  const sim = join(lensDir, 'feature-delivery.sim')
  ok(/^# from: feature-delivery\.way\.yaml@[0-9a-f]{8}$/m.test(readFileSync(sim, 'utf8')), '--lens: the way and its version at the top')
  ok(/^ {2}[a-z_]+ \$construir_gate_nao$/m.test(readFileSync(sim, 'utf8')) && /^ {2}entender \$construir_gate_nao$/m.test(readFileSync(sim, 'utf8')), "--lens sim: a gate's «no» goes back to its on_fail (a loop)")
  writeFileSync(sim, readFileSync(sim, 'utf8') + '# edited by hand\n')
  const again = run(join(lensDir, 'feature-delivery.way.yaml'), '--lens', 'sim', '--write')
  ok(again.status !== 0 && readFileSync(sim, 'utf8').includes('# edited by hand'), '--lens --write does not write over a lens that differs', again.stdout + again.stderr)
  const forced = run(join(lensDir, 'feature-delivery.way.yaml'), '--lens', 'sim', '--write', '--force')
  ok(forced.status === 0 && !readFileSync(sim, 'utf8').includes('# edited by hand'), '--lens --write --force writes over it')
  const printed = run(join(examples, 'scrum.way.yaml'), '--lens', 'drill', '--gate', 'done')
  ok(printed.status === 0 && printed.stdout.startsWith('# from: scrum.way.yaml@') && /bet/.test(printed.stderr), '--lens with no --write prints the lens, and says how many bets it has')
  ok(run(join(examples, 'scrum.way.yaml'), '--lens', 'drill', '--gate', 'nowhere').status !== 0, '--lens drill --gate of a gate that is not there is refused')
}
rmSync(work, { recursive: true, force: true })
checkNoOldName(ok, skill, 'stage-door')

if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ way-of-working checks ok')
