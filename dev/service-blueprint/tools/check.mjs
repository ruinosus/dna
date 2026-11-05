// Checks the skill as a person gets it: the engine's checks (checks/*.check.ts); every example makes its map, workbook
// and explainer (the explainer passing visual-explainer's reviewer when there is a browser) and prints what it should look at — the
// return blueprint on purpose has four things, the others none; a broken file says its line; the map loads nothing from
// the internet; and, in a browser, the map opens a moment, its tabs and its downloads. Run after npm run assets.
import { checkNoOldName, checkSkillMd } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the dna repository
const skill = join(repo, 'skills/service-blueprint')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
const LANG = { 'reembolso-despesas': 'pt', 'employee-onboarding': 'en' }
// what each example has to look at, on purpose
const LOOKS = { 'reembolso-despesas': 4, 'employee-onboarding': 0 }
const work = mkdtempSync(join(tmpdir(), 'service-blueprint-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}
checkSkillMd(ok, join(skill, 'SKILL.md'), 'service-blueprint')

for (const f of readdirSync(join(root, 'checks')).filter((x) => x.endsWith('.check.ts'))) {
  const r = spawnSync('npx', ['tsx', '--tsconfig', join(here, 'tsconfig.json'), join(root, 'checks', f)], { cwd: here, encoding: 'utf8' })
  ok(r.status === 0, `checks/${f}`, r.stdout + r.stderr)
}

const files = readdirSync(examples).filter((x) => x.endsWith('.blueprint.yaml'))
ok(files.length === Object.keys(LANG).length, `${files.length} examples`)
for (const f of files) {
  const id = f.replace('.blueprint.yaml', '')
  const r = run(join(examples, f), '--all', '--lang', LANG[id] ?? 'en', '--out', work)
  const made = ['html', 'xlsx', 'explainer.html'].every((ext) => existsSync(join(work, `${id}.${ext}`)))
  ok(r.status === 0 && made, `${id}: map, workbook and explainer`, r.stdout + r.stderr)
  const n = (r.stdout.match(/^! (to look at|para olhar)/gm) ?? []).length
  ok(n === LOOKS[id], `${id}: ${LOOKS[id]} to look at`, r.stdout)
}

const text = readFileSync(join(examples, 'reembolso-despesas.blueprint.yaml'), 'utf8')
const broken = text.replace('owner: financeiro, within', 'owner: tesouraria, within')
writeFileSync(join(work, 'broken.blueprint.yaml'), broken)
const line = broken.split('\n').findIndex((l) => l.includes('tesouraria')) + 1
const b = run(join(work, 'broken.blueprint.yaml'))
ok(b.status === 1 && b.stderr.includes(`broken.blueprint.yaml:${line}:`) && !existsSync(join(work, 'broken.html')), `a broken file says its line (${line})`, b.stderr)

const map = readFileSync(join(skill, 'assets/map.html'), 'utf8')
ok(!/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(map), 'the map loads nothing from the internet')

// The map in a browser, by the kit (over the DevTools pipe): a moment opens, the tabs and the downloads work.
const { runPage, browser } = await import('../../../skills/service-blueprint/scripts/browser.mjs')
if (!browser()) console.log('• no Chrome here: the map was not opened in a browser')
else {
  const html = readFileSync(join(work, 'reembolso-despesas.html'), 'utf8').replace('</body>', `<script>
    const got = []; HTMLAnchorElement.prototype.click = function () { got.push(this.download) }
    const errs = []; addEventListener('error', (e) => errs.push(String(e.message)))
    setTimeout(async () => { const q = (s) => document.querySelector(s); const out = {}
      q('[data-look="0"]').click(); out.detail = q('.fh-detail h3')?.textContent
      q('[data-get="xlsx"]').click(); q('[data-get="yaml"]').click(); q('[data-get="png"]').click()
      await new Promise((r) => setTimeout(r, 1500))
      q('[data-tab="pains"]').click(); out.pains = document.querySelectorAll('.fh-table tbody tr').length
      out.got = got; out.errs = errs
      const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(p) }, 300)</script></body>`)
  writeFileSync(join(work, 'probe.html'), html)
  const r = (await runPage(join(work, 'probe.html'), 'probe', '', { timeout: 60 })) ?? { errs: ['the page did not answer'] }
  ok(r.detail === 'Espera notícia — 6 dias sem nada' && r.pains >= 2 && (r.got ?? []).join() === 'reembolso-despesas.xlsx,reembolso-despesas.blueprint.yaml,reembolso-despesas.png' && !r.errs?.length, 'the map in a browser: a moment, the tabs, the downloads', JSON.stringify(r))
  // with no «feels» anywhere, the lane says nobody said it — no flat red line at a made-up «3»
  const flat = readFileSync(join(work, 'reembolso-despesas.html'), 'utf8').replace(/"feels":\d,?/g, '').replace('</body>', `<script>setTimeout(() => { const c = document.querySelector('.fh-curve')
    const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify({ text: c?.textContent, line: !!c?.querySelector('polyline'), faces: document.querySelectorAll('.fh-face').length })); document.body.append(p) }, 300)</script></body>`)
  writeFileSync(join(work, 'flat.html'), flat)
  const f = (await runPage(join(work, 'flat.html'), 'probe', '', { timeout: 60 })) ?? {}
  ok(f.text === 'ninguém disse como o cliente se sente' && !f.line && f.faces === 0, 'the map with no «feels»: the lane says nobody said it, no line', JSON.stringify(f))
}

// --check --json: what was read, as one JSON document — what the mod's preview pane draws
{
  const j = spawnSync(process.execPath, [join(skill, 'scripts/build.mjs'), join(skill, 'examples/employee-onboarding.blueprint.yaml'), '--check', '--json'], { encoding: 'utf8' })
  let doc
  try { doc = JSON.parse(j.stdout) } catch {}
  ok(j.status === 0 && doc?.format === 'service-blueprint/read-v1' && Array.isArray(doc.blueprint?.moments) && Array.isArray(doc.looks), '--check --json: the blueprint as read, and what to look at, as one JSON document', j.stdout.slice(0, 200) + j.stderr)
}
rmSync(work, { recursive: true, force: true })
checkNoOldName(ok, skill, 'front-of-house')

if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ service-blueprint checks ok')
