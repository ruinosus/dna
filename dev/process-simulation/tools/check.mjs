// Checks the skill as a person gets it: the engine's checks (checks/run.mjs: parsing, the translation's round trip,
// the same numbers in both languages, the seeded snapshots, the validator, determinism); every example checks, runs
// and makes its page; a broken recipe says what to fix and exits 1; the page loads nothing from the internet and
// carries its version; a clean copy of the skill runs on Node alone; and, in a browser, the page simulates the example
// to the end of its comparison, with its fonts inside. The mod's tests run in dev/dna/tools/check.mjs. Run after npm run assets.
import { checkSkillMd } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'
import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the dna repository
const skill = join(repo, 'skills/process-simulation')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
const release = JSON.parse(readFileSync(join(repo, '.claude-plugin/plugin.json'), 'utf8')).version
const work = mkdtempSync(join(tmpdir(), 'process-simulation-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}
checkSkillMd(ok, join(skill, 'SKILL.md'), 'process-simulation')

const engine = spawnSync(process.execPath, [join(root, 'checks/run.mjs')], { encoding: 'utf8' })
ok(engine.status === 0, `checks/run.mjs: ${engine.stdout.trim().split('\n').pop()}`, engine.stdout + engine.stderr)

// every example: checks clean, runs, makes its page
const sims = readdirSync(examples).filter((f) => f.endsWith('.sim'))
const index = JSON.parse(readFileSync(join(examples, 'index.json'), 'utf8')).map((e) => e.file)
ok(sims.length === 4 && sims.every((f) => index.includes(f)), `${sims.length} examples, each in examples/index.json`)
for (const f of sims) {
  const c = run(join(examples, f), '--check')
  const r = run(join(examples, f), '--run', '--seeds', '2', '--json')
  const rows = r.status === 0 ? JSON.parse(r.stdout).rows : []
  ok(c.status === 0 && rows.length > 0 && rows.every((x) => Number.isFinite(x.median)), `${f}: checks, and runs with a number for each metric`, c.stdout + r.stdout + r.stderr)
}
const ess = join(examples, 'employee-self-service.sim')
const page = run(ess, join(examples, 'corner-cafe.sim'), '--lang', 'pt', '--out', work)
const pagePath = join(work, 'employee-self-service.process-simulation.html')
const html = existsSync(pagePath) ? readFileSync(pagePath, 'utf8') : ''
ok(page.status === 0 && html.includes('"id": "employee-self-service"') && html.includes('"id": "corner-cafe"') && html.includes('var START_UI = "pt";'), 'the page opens on the first recipe, the others in its menu, in the language asked', page.stdout + page.stderr)
ok(!!html && !/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(html) && !html.includes('fonts.googleapis') && (html.match(/@font-face/g) ?? []).length === 7, 'the page loads nothing from the internet: its seven font faces are inside it')
ok(html.includes(`content="process-simulation (dna ${release})"`) && html.includes(`process-simulation ${release}</p>`), `the page says the version that made it (${release})`)
ok(!/\bcoi\b|\bcompass\b/i.test(readdirSync(examples).map((f) => readFileSync(join(examples, f), 'utf8')).join('\n') + html), 'no client name in the examples or the page')

// what to fix, and the other modes
writeFileSync(join(work, 'broken.sim'), 'sim "t"\nhorizon 1 day\narrive item 10/hour\nstep a time 1min\nend done\nend other\na ->\n  done 60%\n  other 30%\nshow count end done\n')
const broken = run(join(work, 'broken.sim'), '--check')
ok(broken.status === 1 && /✗ broken\.sim: .*add up to 90%/.test(broken.stdout), 'a broken recipe: exit 1, and the validator says what to fix', broken.stdout)
ok(run(join(work, 'broken.sim')).status === 1 && !existsSync(join(work, 'broken.process-simulation.html')), 'no page for a broken recipe')
const pt = run(join(examples, 'corner-cafe.sim'), '--to', 'pt-BR')
writeFileSync(join(work, 'cafe-pt.sim'), pt.stdout)
const back = spawnSync(process.execPath, [build, join(work, 'cafe-pt.sim'), '--to', 'en'], { encoding: 'utf8' })
ok(pt.stdout.includes('chegada customer 30/hora') && back.stdout === readFileSync(join(examples, 'corner-cafe.sim'), 'utf8'), '--to: to Portuguese and back, byte for byte')
const set = JSON.parse(run(ess, '--run', '--seeds', '2', '--set', 'hr_partners=8', '--json').stdout)
ok(set.knobs.hr_partners === 8 && run(ess, '--nope').status === 2, '--set changes a control; an unknown option: exit 2')

// a clean copy of the skill, with no node_modules anywhere above it, runs on Node alone
const clean = join(work, 'clean')
cpSync(skill, join(clean, 'process-simulation'), { recursive: true })
const c = spawnSync(process.execPath, [join(clean, 'process-simulation/scripts/build.mjs'), join(clean, 'process-simulation/examples/corner-cafe.sim'), '--out', join(clean, 'out')], { encoding: 'utf8', cwd: clean })
ok(c.status === 0 && existsSync(join(clean, 'out/corner-cafe.process-simulation.html')), 'a clean copy, no node_modules: the page on Node alone', c.stdout + c.stderr)

// The page in a browser, by the kit (over the DevTools pipe): it runs, ranges and compares the scenarios.
const { runPage, browser } = await import('@ruinosus/visual-explainer/kit/browser.mjs')
if (!browser()) console.log('• no Chrome here: the page was not opened in a browser')
else {
  // the page has no </body>: the probe goes at its end
  writeFileSync(join(work, 'probe.html'), html + `<script>
    const errs = []; addEventListener('error', (e) => errs.push(String(e.message)))
    const q = (s) => document.querySelector(s)
    ;(async () => { const out = {}
      const t0 = Date.now()
      while (Date.now() - t0 < 45000 && (!q('#compare-table tbody') || q('#compare-table .pending'))) await new Promise((r) => setTimeout(r, 250))
      out.title = q('#sim-name')?.textContent; out.lang = document.documentElement.lang
      out.cards = [...document.querySelectorAll('[id^="mv-"]')].map((e) => e.textContent)
      out.columns = q('#compare-table thead')?.querySelectorAll('th').length; out.pending = !!q('#compare-table .pending')
      await document.fonts.ready
      const loaded = new Set([...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/["']/g, '')))
      out.fonts = ['IBM Plex Sans', 'IBM Plex Mono', 'Bricolage Grotesque'].every((f) => loaded.has(f))
      q('#ui-en').click(); out.en = document.documentElement.lang
      out.errs = errs
      const p = document.createElement('pre'); p.id = 'chalk-probe'; p.textContent = encodeURIComponent(JSON.stringify(out)); document.body.append(p) })()</script>`)
  const r = (await runPage(join(work, 'probe.html'), 'probe', '', { timeout: 90 })) ?? { errs: ['the page did not answer'] }
  ok(r.title === 'Employee Self-Service with Workday' && r.lang === 'pt-BR' && r.cards?.length === 4 && r.cards.every((v) => v && v !== '–'), 'the page in a browser: the example runs, in Portuguese, with a value in each card', JSON.stringify(r))
  ok(r.columns === 5 && r.pending === false && r.fonts === true && r.en === 'en' && !r.errs?.length, 'the three scenarios compared to the end, the fonts inside, EN at a click, no error', JSON.stringify(r))
}

// the mod's tests (dev/process-simulation/checks/mod.test.tsx) run with the whole mod's, in dev/dna/tools/check.mjs

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
