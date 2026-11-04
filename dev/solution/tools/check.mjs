// Checks the skill as a person gets it: every accelerator checks clean (each piece passes its own skill's check, each
// lens up to date with its way) and makes its page, one file with a tab per piece that loads nothing from the internet;
// a broken solution file says its line and exits 1; a missing or broken piece exits 4 with its skill's messages; a lens
// left behind by a change of the way is said; --new copies an accelerator and refuses a folder that is not empty; and,
// in a browser, the page opens each tab with its piece inside.
import { checkSkillMd } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'
import { browser, runPages } from '@ruinosus/visual-explainer/kit/browser.mjs'
import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../../..')
const skill = join(repo, 'skills/solution')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
const release = JSON.parse(readFileSync(join(repo, '.claude-plugin/plugin.json'), 'utf8')).version
const work = mkdtempSync(join(tmpdir(), 'solution-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}
checkSkillMd(ok, join(skill, 'SKILL.md'), 'solution')
ok(readFileSync(join(skill, 'SKILL.md'), 'utf8').includes(`version: "${release}"`), `SKILL.md carries the release (${release})`)

// every accelerator: checks clean, makes its page with every piece inside
const accs = readdirSync(examples).filter((d) => existsSync(join(examples, d, `${d}.solution.yaml`)))
ok(accs.length === 3, `${accs.length} solution accelerators: ${accs.join(', ')}`)
const pages = []
for (const a of accs) {
  const file = join(examples, a, `${a}.solution.yaml`)
  const c = run(file, '--check')
  ok(c.status === 0 && !/^[✗!]/m.test(c.stdout), `${a}: every piece passes its check, every lens up to date`, c.stdout + c.stderr)
  const out = join(work, a)
  mkdirSync(out)
  const p = run(file, '--out', out)
  const page = join(out, `${a}.solution.html`)
  const html = existsSync(page) ? readFileSync(page, 'utf8') : ''
  const kinds = readFileSync(file, 'utf8').match(/^(way|sim|blueprint|drill|agents|lesson):/gm).map((k) => k.slice(0, -1))
  ok(p.status === 0 && kinds.every((k) => html.includes(`id="piece-${k}"`)), `${a}: the page has its ${kinds.length} pieces inside (${kinds.join(', ')})`, p.stdout + p.stderr)
  ok(!/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(html.replace(/<script type="application\/octet-stream"[\s\S]*?<\/script>/g, '')), `${a}: the page loads nothing from the internet`)
  ok(html.includes(`content="solution ${release}"`), `${a}: the page carries its version`)
  pages.push({ a, page, kinds })
}

// the --json reading
{
  const j = run(join(examples, 'service-desk/service-desk.solution.yaml'), '--check', '--json')
  let doc
  try { doc = JSON.parse(j.stdout) } catch {}
  ok(j.status === 0 && doc?.format === 'solution/read-v1' && doc.pieces.length === 5 && doc.pieces.every((p) => p.state === 'ok'), '--check --json: the solution and each piece as one JSON document', j.stdout.slice(0, 200) + j.stderr)
}

// a broken file, a missing piece, a broken piece, a lens left behind
{
  const dir = join(work, 'cases')
  cpSync(join(examples, 'assistant-delivery'), dir, { recursive: true })
  const sol = join(dir, 'assistant-delivery.solution.yaml')
  const text = readFileSync(sol, 'utf8')
  writeFileSync(sol, text.replace('lang: pt', 'lang: pt\nsimulation: x.sim'))
  const bad = run(sol, '--check')
  const line = text.replace('lang: pt', 'lang: pt\nsimulation: x.sim').split('\n').findIndex((l) => l.startsWith('simulation:')) + 1
  ok(bad.status === 1 && bad.stderr.includes(`assistant-delivery.solution.yaml:${line}: «simulation» is not a field`), `a field that is not one says its line (${line})`, bad.stderr)
  ok(run(sol, '--check', '--format').status === 1, '--check --format refuses it too (the mod\'s guard)')
  writeFileSync(sol, text.replace('drill: assistant-delivery.drill.yaml', 'drill: gone.drill.yaml'))
  const gone = run(sol, '--check')
  ok(gone.status === 4 && /✗ drill: gone\.drill\.yaml (is not there|não está lá)/.test(gone.stdout), 'a missing piece exits 4 and says which', gone.stdout)
  ok(run(sol, '--check', '--format').status === 0, '--check --format reads only the file: a missing piece is not its business')
  writeFileSync(sol, text)
  writeFileSync(join(dir, 'assistant-delivery.sim'), readFileSync(join(dir, 'assistant-delivery.sim'), 'utf8').replace('end delivered', 'end delivered\nend delivered'))
  const broken = run(sol, '--check')
  ok(broken.status === 4 && /✗ sim: assistant-delivery\.sim does not pass process-simulation's check|✗ sim: assistant-delivery\.sim não passa no check do process-simulation/.test(broken.stdout), "a piece that fails its own check exits 4, with its skill's messages", broken.stdout)
  cpSync(join(examples, 'assistant-delivery/assistant-delivery.sim'), join(dir, 'assistant-delivery.sim'))
  const way = join(dir, 'assistant-delivery.way.yaml')
  writeFileSync(way, readFileSync(way, 'utf8').replace('name: Publicação', 'name: Publicação no Teams'))
  const behind = run(sol, '--check')
  ok(behind.status === 0 && (behind.stdout.match(/veio de uma versão anterior/g) ?? []).length === 3, 'the way changed: each of its three lenses is said to have fallen behind, with the command to make it again', behind.stdout)
}

// --list and --new
{
  const l = run('--list')
  ok(l.status === 0 && accs.every((a) => l.stdout.includes(a)), '--list shows the accelerators')
  const dest = join(work, 'mine')
  const n = run('--new', 'service-desk', dest)
  ok(n.status === 0 && existsSync(join(dest, 'service-desk.solution.yaml')) && existsSync(join(dest, 'agents/rh-folha/agent.mcs.yml')), '--new copies an accelerator, pieces and agents', n.stdout + n.stderr)
  ok(run('--new', 'service-desk', dest).status !== 0, '--new refuses a folder that is not empty')
  ok(run('--new', 'nowhere', join(work, 'x')).status !== 0, '--new refuses an accelerator that is not there')
}

// a clean copy of the skill alone (no other skill beside it): the solution file is read, each piece said not checked
{
  const alone = join(work, 'alone/solution')
  cpSync(skill, alone, { recursive: true })
  const r = spawnSync(process.execPath, [join(alone, 'scripts/build.mjs'), join(alone, 'examples/assistant-delivery/assistant-delivery.solution.yaml'), '--check'], { encoding: 'utf8' })
  ok(r.status === 0 && (r.stdout.match(/not checked|não conferido/g) ?? []).length === 4, 'alone, it reads the solution and says each piece is not checked', r.stdout + r.stderr)
}

// in a browser: each tab opens its piece
if (browser()) {
  // the probe clicks every tab and writes what it saw where the kit's browser reads it: <pre id="chalk-tabs">
  const probe = `<script>window.addEventListener('load',function(){var seen={};[].slice.call(document.querySelectorAll('nav [data-tab]')).forEach(function(b){if(b.dataset.tab==='summary'||b.disabled)return;b.click();var f=document.getElementById('frame');seen[b.dataset.tab]=!f.hidden&&f.srcdoc.length>1000});var pre=document.createElement('pre');pre.id='chalk-tabs';pre.hidden=true;pre.textContent=encodeURIComponent(JSON.stringify(seen));document.body.appendChild(pre)})</script>`
  const files = pages.map(({ a, page }) => {
    const f = join(work, `${a}.probe.html`)
    writeFileSync(f, readFileSync(page, 'utf8') + probe)
    return { file: f, mode: 'tabs' }
  })
  const { results } = await runPages(files, { timeout: 60 })
  pages.forEach(({ a, kinds }, k) => {
    const seen = results?.[k] ?? {}
    ok(kinds.every((x) => seen[x] === true), `${a}: in a browser, each tab opens its piece`, JSON.stringify(seen))
  })
} else console.log('• no Chrome, Chromium or Edge: the tabs were not opened')

// DNA 2.1.0: --okf writes the solution as an OKF v0.2 bundle — conformant, read back by the kit's reader, the same
// bytes when nothing changed, one concept changed when one piece did, a broken piece a draft, and the attester inside
// it checking a run's receipt
{
  const { readBundle } = await import(join(repo, 'kit/okf-read.mjs'))
  const okfRun = (now, ...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, env: { ...process.env, DNA_NOW: now } })
  const T1 = '2026-11-04T21:10:00Z'
  const T2 = '2026-11-05T08:00:00Z'
  const walk = (dir) => readdirSync(dir, { recursive: true }).filter((f) => statSync(join(dir, f)).isFile()).sort()
  const snapshot = (dir) => walk(dir).map((f) => `${f}\n${readFileSync(join(dir, f), 'utf8')}`).join('\n\0\n')
  /** The minimal conformance of OKF §11, and every internal link and path field resolving. */
  const conformance = (dir) => {
    const bad = []
    for (const f of walk(dir).filter((f) => f.endsWith('.md'))) {
      const text = readFileSync(join(dir, f), 'utf8')
      const reserved = /(^|\/)(index|log)\.md$/.test(f)
      const fm = /^---\n([\s\S]*?)\n---\n/.exec(text)
      if (!reserved && !(fm && /^type: \S/m.test(fm[1]))) bad.push(`${f}: no type`)
      if (f === 'index.md' && !(fm && /^okf_version: "0\.2"$/m.test(fm[1]))) bad.push('index.md: no okf_version "0.2"')
      if (reserved && f !== 'index.md' && fm) bad.push(`${f}: a frontmatter on a reserved file`)
      if (f === 'log.md') {
        const dates = [...text.matchAll(/^## (\d{4}-\d{2}-\d{2})$/gm)].map((m) => m[1])
        if (!dates.length || dates.join() !== [...dates].sort().reverse().join()) bad.push(`log.md: dates not newest first (${dates})`)
      }
      const targets = [...text.matchAll(/\]\(([^)\s#]+)\)/g)].map((m) => m[1]).filter((h) => !/^[a-z]+:/i.test(h))
      for (const m of (fm?.[1] ?? '').matchAll(/(?:^|[\s{,])(?:resource|computation): ("[^"]+"|[^\s,}]+)/gm)) targets.push(m[1].replace(/^"|"$/g, ''))
      for (const t of targets) {
        if (/^[a-z]+:/i.test(t) || / /.test(t)) continue // a URL, or a scope descriptor («3 of 10 interviews»)
        const at = t.startsWith('/') ? join(dir, t) : join(dir, dirname(f), t)
        if (!existsSync(at)) bad.push(`${f}: ${t} does not resolve`)
      }
    }
    return bad
  }
  for (const a of accs) {
    const file = join(examples, a, `${a}.solution.yaml`)
    const out = join(work, `${a}.okf`)
    const e = okfRun(T1, file, '--okf', '--out', out)
    const bad = existsSync(out) ? conformance(out) : ['no bundle']
    ok(e.status === 0 && !bad.length && /^✓ okf /m.test(e.stdout), `${a}: --okf writes a conformant OKF v0.2 bundle`, e.stdout + e.stderr + bad.join('\n'))
    const b = existsSync(out) ? readBundle(out, { now: new Date(T1) }) : { concepts: [] }
    const kinds = readFileSync(file, 'utf8').match(/^(way|sim|blueprint|drill|agents|lesson):/gm).length
    ok(b.dna === true && b.concepts.filter((c) => c.path.split('/').length === 2 || c.path === '/computations/simulation.md').length === kinds &&
       b.concepts.filter((c) => c.dna && !c.path.startsWith('/references/')).every((c) => c.trust === 'machine-confirmed' && c.status === 'stable'),
       `${a}: the kit's reader reads it back — made by DNA, one concept per piece (${kinds}), each machine-confirmed`, JSON.stringify(b.concepts.map((c) => [c.path, c.trust, c.status])))
    const before = snapshot(out)
    okfRun(T2, file, '--okf', '--out', out)
    ok(snapshot(out) === before, `${a}: exporting again with nothing changed gives the same bytes`)
  }
  // one piece changed: only its concept, and the log of the day
  const copy = join(work, 'ess-copy')
  cpSync(join(examples, 'employee-self-service'), copy, { recursive: true })
  const sol = join(copy, 'employee-self-service.solution.yaml')
  const out = join(work, 'ess-copy.okf')
  okfRun(T1, sol, '--okf', '--out', out)
  const was = Object.fromEntries(walk(out).map((f) => [f, readFileSync(join(out, f), 'utf8')]))
  const bp = join(copy, 'employee-self-service.blueprint.yaml')
  writeFileSync(bp, readFileSync(bp, 'utf8') + '# The moments were reread with the HR team.\n')
  const u = okfRun(T2, sol, '--okf', '--out', out)
  const now = Object.fromEntries(walk(out).map((f) => [f, readFileSync(join(out, f), 'utf8')]))
  const changed = Object.keys(now).filter((f) => now[f] !== was[f]).sort()
  ok(u.status === 0 && changed.join() === 'journey.md,log.md,references/dna/employee-self-service.blueprint.yaml' &&
     /^## 2026-11-05\n\* \*\*Update\*\*: .*journey\.md/m.test(now['log.md']) && now['journey.md'].includes('at: 2026-11-05T08:00:00Z') && now['process.md'].includes('at: 2026-11-04T21:10:00Z'),
     'a piece changed: only its concept and its copy change, with an Update in the log of the day', u.stdout + u.stderr + changed.join(', '))
  // a broken piece: a draft, without verified
  writeFileSync(bp, readFileSync(bp, 'utf8').replace(/^moments:/m, 'momentz:'))
  const d = okfRun(T2, sol, '--okf', '--out', out)
  const journey = existsSync(join(out, 'journey.md')) ? readFileSync(join(out, 'journey.md'), 'utf8') : ''
  ok(d.status === 4 && /^status: draft$/m.test(journey) && !/^verified:/m.test(journey), 'a piece that fails its check still goes, as status: draft, without verified (exit 4)', d.stdout + d.stderr + journey.slice(0, 400))
  // the attester the bundle carries, on a run's receipt
  const attester = join(work, 'employee-self-service.okf', 'references/attesters/process-simulation.mjs')
  const receipt = join(work, 'receipt.json')
  spawnSync(process.execPath, [join(repo, 'skills/process-simulation/scripts/build.mjs'), join(work, 'employee-self-service.okf/references/dna/employee-self-service.sim'), '--run', '--seeds', '2', '--set', 'hr_partners=10', '--receipt', receipt], { encoding: 'utf8' })
  const g = spawnSync(process.execPath, [attester, receipt], { encoding: 'utf8' })
  const forged = join(work, 'forged.json')
  writeFileSync(forged, JSON.stringify({ ...JSON.parse(readFileSync(receipt, 'utf8')), set: { hr_partners: 99 } }))
  const f = spawnSync(process.execPath, [attester, forged], { encoding: 'utf8' })
  ok(g.status === 0 && /^✓ attested/m.test(g.stdout) && f.status === 3 && /hr_partners=99 is outside 4\.\.30/.test(f.stdout),
     "the bundle's attester confirms a run's receipt and refuses a forged one, with only the bundle's files", g.stdout + g.stderr + f.stdout + f.stderr)
}

// a person's review of a piece (reviewed: in the solution, written by --review): human-reviewed in the bundle while the
// piece stays as it was reviewed; said by --check, and gone from the bundle, once it changes
{
  const env = (now) => ({ encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, env: { ...process.env, DNA_NOW: now } })
  const sol = (dir) => join(dir, 'employee-self-service.solution.yaml')
  const dir = join(work, 'review')
  cpSync(join(examples, 'employee-self-service'), dir, { recursive: true })
  const before = readFileSync(sol(dir), 'utf8')
  const dry = spawnSync(process.execPath, [build, sol(dir), '--review', 'blueprint', '--by', 'gerente-rh'], env('2026-11-05T14:00:00Z'))
  ok(dry.status === 0 && /^reviewed:\n {2}blueprint: human:gerente-rh 2026-11-05T14:00:00Z [0-9a-f]{8}$/m.test(dry.stdout) && readFileSync(sol(dir), 'utf8') === before,
     '--review without --write shows the solution with the review, and writes nothing', dry.stdout.slice(-300) + dry.stderr)
  const w = spawnSync(process.execPath, [build, sol(dir), '--review', 'blueprint', '--by', 'gerente-rh', '--write'], env('2026-11-05T14:00:00Z'))
  const written = readFileSync(sol(dir), 'utf8')
  ok(w.status === 0 && /^ {2}blueprint: human:gerente-rh 2026-11-05T14:00:00Z [0-9a-f]{8}$/m.test(written) && written.startsWith(before.trimEnd()),
     '--review --write keeps the solution as it was and adds the review', w.stdout + w.stderr)
  const again = spawnSync(process.execPath, [build, sol(dir), '--review', 'blueprint', '--by', 'human:lider-rh', '--write'], env('2026-11-06T10:00:00Z'))
  const twice = readFileSync(sol(dir), 'utf8')
  ok(again.status === 0 && (twice.match(/^ {2}blueprint:/gm) ?? []).length === 1 && /^ {2}blueprint: human:lider-rh 2026-11-06T10:00:00Z/m.test(twice), 'a second review of the same piece takes the place of the first', twice.slice(-200))
  const out = join(work, 'review.okf')
  const e = spawnSync(process.execPath, [build, sol(dir), '--okf', '--out', out], env('2026-11-06T11:00:00Z'))
  const journey = existsSync(join(out, 'journey.md')) ? readFileSync(join(out, 'journey.md'), 'utf8') : ''
  const c = spawnSync(process.execPath, [build, sol(dir), '--check'], env('2026-11-06T11:00:00Z'))
  ok(e.status === 0 && journey.includes('  - { by: human:lider-rh, at: 2026-11-06T10:00:00Z }') && /\*\*Review\*\*: .*journey\.md.* human:lider-rh/.test(readFileSync(join(out, 'log.md'), 'utf8')) && c.status === 0 && !/changed after/.test(c.stdout),
     'the review goes to the bundle as human-reviewed, with a Review in the log; --check says nothing', e.stdout + e.stderr + journey.slice(0, 600))
  const bp = join(dir, 'employee-self-service.blueprint.yaml')
  writeFileSync(bp, readFileSync(bp, 'utf8') + '# A moment was added after the review.\n')
  const c2 = spawnSync(process.execPath, [build, sol(dir), '--check'], env('2026-11-07T09:00:00Z'))
  spawnSync(process.execPath, [build, sol(dir), '--okf', '--out', out], env('2026-11-07T09:00:00Z'))
  const journey2 = readFileSync(join(out, 'journey.md'), 'utf8')
  ok(c2.status === 0 && c2.stdout.includes("blueprint changed after human:lider-rh's review") && !journey2.includes('{ by: human:lider-rh') && journey2.includes("blueprint changed after human:lider-rh's review"),
     'the piece changed after the review: --check says so, and the review leaves the bundle', c2.stdout + journey2.slice(0, 500))
  writeFileSync(sol(dir), readFileSync(sol(dir), 'utf8') + '  agents: human:x 2026-11-05T14:00:00Z abcdef12\n')
  const c3 = spawnSync(process.execPath, [build, sol(dir), '--check'], env('2026-11-07T09:00:00Z'))
  const line = readFileSync(sol(dir), 'utf8').trimEnd().split('\n').length
  ok(c3.status === 1 && c3.stderr.includes(`employee-self-service.solution.yaml:${line}:`) && /agents/.test(c3.stderr), 'a review of a piece the solution does not have is an error, with its line', c3.stdout + c3.stderr)
  const nb = spawnSync(process.execPath, [build, join(examples, 'employee-self-service', 'employee-self-service.solution.yaml'), '--review', 'lesson', '--by', 'x'], env('2026-11-07T09:00:00Z'))
  ok(nb.status === 2 && /lesson/.test(nb.stderr), '--review of a piece the solution does not have: exit 2', nb.stdout + nb.stderr)
}

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ solution checks ok')
