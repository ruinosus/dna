// Checks the skill as a person gets it: the engine's checks (checks/*.check.ts); every example makes its map, workbook
// and lesson (the lesson passing chalk-talk's reviewer when there is a browser) and prints what it should look at — the
// return blueprint on purpose has four things, the others none; a broken file says its line; the map loads nothing from
// the internet; and, in a browser, the map opens a moment, its tabs and its downloads. Run after npm run assets.
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const skill = join(root, 'skills/front-of-house')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
const LANG = { devolucao: 'pt', 'gym-signup': 'en' }
// what each example has to look at, on purpose
const LOOKS = { devolucao: 4, 'gym-signup': 0 }
const work = mkdtempSync(join(tmpdir(), 'front-of-house-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}

for (const f of readdirSync(join(root, 'checks')).filter((x) => x.endsWith('.check.ts'))) {
  const r = spawnSync('npx', ['tsx', '--tsconfig', join(here, 'tsconfig.json'), join(root, 'checks', f)], { cwd: here, encoding: 'utf8' })
  ok(r.status === 0, `checks/${f}`, r.stdout + r.stderr)
}

const files = readdirSync(examples).filter((x) => x.endsWith('.blueprint.yaml'))
ok(files.length === Object.keys(LANG).length, `${files.length} examples`)
for (const f of files) {
  const id = f.replace('.blueprint.yaml', '')
  const r = run(join(examples, f), '--all', '--lang', LANG[id] ?? 'en', '--out', work)
  const made = ['html', 'xlsx', 'lesson.html'].every((ext) => existsSync(join(work, `${id}.${ext}`)))
  ok(r.status === 0 && made, `${id}: map, workbook and lesson`, r.stdout + r.stderr)
  const n = (r.stdout.match(/^! (to look at|para olhar)/gm) ?? []).length
  ok(n === LOOKS[id], `${id}: ${LOOKS[id]} to look at`, r.stdout)
}

const text = readFileSync(join(examples, 'devolucao.blueprint.yaml'), 'utf8')
const broken = text.replace('owner: financeiro, within', 'owner: tesouraria, within')
writeFileSync(join(work, 'broken.blueprint.yaml'), broken)
const line = broken.split('\n').findIndex((l) => l.includes('tesouraria')) + 1
const b = run(join(work, 'broken.blueprint.yaml'))
ok(b.status === 1 && b.stderr.includes(`broken.blueprint.yaml:${line}:`) && !existsSync(join(work, 'broken.html')), `a broken file says its line (${line})`, b.stderr)

const map = readFileSync(join(skill, 'assets/map.html'), 'utf8')
ok(!/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(map), 'the map loads nothing from the internet')

const browser = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium', process.env.CHROME_PATH].find((p) => p && existsSync(p))
if (!browser) console.log('• no Chrome here: the map was not opened in a browser')
else {
  const html = readFileSync(join(work, 'devolucao.html'), 'utf8').replace('</body>', `<script>
    const got = []; HTMLAnchorElement.prototype.click = function () { got.push(this.download) }
    const errs = []; addEventListener('error', (e) => errs.push(String(e.message)))
    setTimeout(async () => { const q = (s) => document.querySelector(s); const out = {}
      q('[data-look="0"]').click(); out.detail = q('.fh-detail h3')?.textContent
      q('[data-get="xlsx"]').click(); q('[data-get="yaml"]').click(); q('[data-get="png"]').click()
      await new Promise((r) => setTimeout(r, 1500))
      q('[data-tab="pains"]').click(); out.pains = document.querySelectorAll('.fh-table tbody tr').length
      out.got = got; out.errs = errs
      const p = document.createElement('pre'); p.id = 'probe'; p.textContent = JSON.stringify(out); document.body.append(p) }, 300)</script></body>`)
  writeFileSync(join(work, 'probe.html'), html)
  const profile = mkdtempSync(join(tmpdir(), 'front-of-house-chrome-'))
  const dom = execFileSync(browser, ['--headless=new', '--disable-gpu', `--user-data-dir=${profile}`, '--virtual-time-budget=8000', '--dump-dom', pathToFileURL(join(work, 'probe.html')).href], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 90000 })
  rmSync(profile, { recursive: true, force: true })
  const found = dom.match(/<pre id="probe">([^<]*)<\/pre>/)
  const r = found ? JSON.parse(found[1].replace(/&quot;/g, '"')) : { errs: ['the page did not answer'] }
  ok(r.detail === 'Espera notícia — 6 dias sem nada' && r.pains >= 2 && (r.got ?? []).join() === 'devolucao.xlsx,devolucao.blueprint.yaml,devolucao.png' && !r.errs.length, 'the map in a browser: a moment, the tabs, the downloads', JSON.stringify(r))
}

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ front-of-house checks ok')
