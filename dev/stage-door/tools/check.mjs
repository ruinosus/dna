// Checks the skill as a person gets it: every example makes its map, workbook and lesson (the lesson passing chalk-talk's
// reviewer when there is a browser); the workbook it made reads back as no change; a broken file says its line; the map
// needs nothing from the internet; and, when LibreOffice is here, the workbook opens in it. Run after npm run assets.
import { execFileSync, spawnSync } from 'node:child_process'
import { copyFileSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const skill = resolve(here, '../../../skills/stage-door')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
// The language each example is written in.
const LANG = { 'feature-delivery': 'pt', scrum: 'en', 'service-desk': 'pt', 'initiative-portfolio': 'pt' }
const work = mkdtempSync(join(tmpdir(), 'stage-door-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}

const files = readdirSync(examples).filter((f) => f.endsWith('.way.yaml'))
ok(files.length === Object.keys(LANG).length, `${files.length} examples`)
for (const f of files) {
  const id = f.replace('.way.yaml', '')
  const lang = LANG[id] ?? 'en'
  const r = run(join(examples, f), '--all', '--lang', lang, '--out', work)
  const made = ['html', 'xlsx', 'lesson.html'].every((ext) => existsSync(join(work, `${id}.${ext}`)))
  ok(r.status === 0 && made, `${id}: map, workbook and lesson`, r.stdout + r.stderr)
  ok(!/^! (to look at|para olhar)/m.test(r.stdout), `${id}: nothing to look at`, r.stdout)
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

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ stage-door checks ok')
