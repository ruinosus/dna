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
const page = run(ess, join(examples, 'hr-help-desk.sim'), '--lang', 'pt', '--out', work)
const pagePath = join(work, 'employee-self-service.process-simulation.html')
const html = existsSync(pagePath) ? readFileSync(pagePath, 'utf8') : ''
ok(page.status === 0 && html.includes('"id": "employee-self-service"') && html.includes('"id": "hr-help-desk"') && html.includes('var START_UI = "pt";'), 'the page opens on the first recipe, the others in its menu, in the language asked', page.stdout + page.stderr)
ok(!!html && !/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(html) && !html.includes('fonts.googleapis') && (html.match(/@font-face/g) ?? []).length === 7, 'the page loads nothing from the internet: its seven font faces are inside it')
ok(html.includes(`content="process-simulation (dna ${release})"`) && html.includes(`process-simulation ${release}</p>`), `the page says the version that made it (${release})`)
ok(!/\bcoi\b|\bcompass\b/i.test(readdirSync(examples).map((f) => readFileSync(join(examples, f), 'utf8')).join('\n') + html), 'no client name in the examples or the page')

// what to fix, and the other modes
writeFileSync(join(work, 'broken.sim'), 'sim "t"\nhorizon 1 day\narrive item 10/hour\nstep a time 1min\nend done\nend other\na ->\n  done 60%\n  other 30%\nshow count end done\n')
const broken = run(join(work, 'broken.sim'), '--check')
ok(broken.status === 1 && /✗ broken\.sim: .*add up to 90%/.test(broken.stdout), 'a broken recipe: exit 1, and the validator says what to fix', broken.stdout)
ok(run(join(work, 'broken.sim')).status === 1 && !existsSync(join(work, 'broken.process-simulation.html')), 'no page for a broken recipe')
const pt = run(join(examples, 'hr-help-desk.sim'), '--to', 'pt-BR')
writeFileSync(join(work, 'help-desk-pt.sim'), pt.stdout)
const back = spawnSync(process.execPath, [build, join(work, 'help-desk-pt.sim'), '--to', 'en'], { encoding: 'utf8' })
ok(pt.stdout.includes('chegada request 30/hora') && back.stdout === readFileSync(join(examples, 'hr-help-desk.sim'), 'utf8'), '--to: to Portuguese and back, byte for byte')
const set = JSON.parse(run(ess, '--run', '--seeds', '2', '--set', 'hr_partners=8', '--json').stdout)
ok(set.knobs.hr_partners === 8 && run(ess, '--nope').status === 2, '--set changes a control; an unknown option: exit 2')

// a clean copy of the skill, with no node_modules anywhere above it, runs on Node alone
const clean = join(work, 'clean')
cpSync(skill, join(clean, 'process-simulation'), { recursive: true })
const c = spawnSync(process.execPath, [join(clean, 'process-simulation/scripts/build.mjs'), join(clean, 'process-simulation/examples/hr-help-desk.sim'), '--out', join(clean, 'out')], { encoding: 'utf8', cwd: clean })
ok(c.status === 0 && existsSync(join(clean, 'out/hr-help-desk.process-simulation.html')), 'a clean copy, no node_modules: the page on Node alone', c.stdout + c.stderr)

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

// a run's receipt, and the attester that checks it (DNA 2.1.0: the simulation as an OKF Attested Computation)
{
  const ess = join(repo, 'skills/solution/examples/employee-self-service/employee-self-service.sim')
  const receipt = join(work, 'receipt.json')
  const plain = run(ess, '--run', '--seeds', '3', '--set', 'hr_partners=14', '--json')
  const r = run(ess, '--run', '--seeds', '3', '--set', 'hr_partners=14', '--receipt', receipt)
  const got = existsSync(receipt) ? JSON.parse(readFileSync(receipt, 'utf8')) : {}
  ok(r.status === 0 && got.format === 'dna/process-simulation/receipt-v1' && /^[0-9a-f]{64}$/.test(got.recipe_sha256 ?? '') &&
     got.engine === `dna/process-simulation/${release}` && got.seed === 11 && got.runs === 3 && got.set?.hr_partners === 14 &&
     JSON.stringify(got.rows) === JSON.stringify(JSON.parse(plain.stdout).rows),
     '--receipt writes the run: the recipe\'s sha256, the engine, the seed, the runs, the controls and the same numbers', r.stdout + r.stderr + JSON.stringify(got).slice(0, 300))
  const attest = (rc, ...more) => { const f = join(work, `r-${Math.random().toString(36).slice(2)}.json`); writeFileSync(f, JSON.stringify(rc)); return run(ess, '--attest', f, ...more) }
  const good = attest(got)
  ok(good.status === 0 && /^✓ attested: Employee Self-Service with Workday, 4 metrics, seed 11, 3 runs/m.test(good.stdout), '--attest confirms a good receipt', good.stdout + good.stderr)
  const j = attest(got, '--json')
  const v = j.status === 0 ? JSON.parse(j.stdout) : {}
  ok(v.format === 'dna/process-simulation/verdict-v1' && v.ok === true && v.checked?.length === 4, '--attest --json gives the verdict as a document', j.stdout + j.stderr)
  const bad = [
    [{ ...got, recipe_sha256: '0'.repeat(64) }, 'the recipe was swapped'],
    [{ ...got, set: { ...got.set, hr_partners: 50 } }, 'hr_partners=50 is outside 4..30'],
    [{ ...got, set: { ...got.set, custo: 1 } }, 'custo is not a parameter'],
    [{ ...got, engine: 'dna/process-simulation/9.9.0' }, 'made by another engine (9.9.0)'],
    [{ ...got, rows: got.rows?.map((x, i) => (i ? x : { ...x, median: x.median * 1.01 })) }, `${got.rows?.[0]?.metric}: the receipt says`],
  ]
  for (const [rc, why] of bad) {
    const x = attest(rc)
    ok(x.status === 3 && x.stdout.includes(`✗ ${why}`), `--attest refuses: «${why}» (exit 3)`, `${x.status} ${x.stdout}${x.stderr}`)
  }
  const torn = join(work, 'torn.json'); writeFileSync(torn, '{ not json')
  const t = run(ess, '--attest', torn)
  ok(t.status === 2, 'a receipt that is not JSON: exit 2', `${t.status} ${t.stdout}${t.stderr}`)
}

// the mod's tests (dev/process-simulation/checks/mod.test.tsx) run with the whole mod's, in dev/dna/tools/check.mjs

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
