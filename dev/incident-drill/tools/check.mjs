// Checks the skill as a person gets it: the engine's checks (checks/*.check.ts); every example makes its game and its
// facilitator's script with nothing to look at; a broken file — and a broken drawing — says its line; the game page loads
// nothing from the internet; and, when there is a browser, every example is played to its end there. Run after
// npm run assets.
import { checkSkillMd } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const repo = resolve(here, '../../..') // the dna repository
const skill = join(repo, 'skills/incident-drill')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
const LANG = { checkout: 'pt', 'database-disk': 'en' }
const work = mkdtempSync(join(tmpdir(), 'incident-drill-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}
checkSkillMd(ok, join(skill, 'SKILL.md'), 'incident-drill')

for (const f of readdirSync(join(root, 'checks')).filter((x) => x.endsWith('.check.ts'))) {
  const r = spawnSync('npx', ['tsx', join(root, 'checks', f)], { cwd: here, encoding: 'utf8' })
  ok(r.status === 0, `checks/${f}`, r.stdout + r.stderr)
}

const drills = readdirSync(examples).filter((x) => x.endsWith('.drill.yaml'))
ok(drills.length === Object.keys(LANG).length, `${drills.length} examples`)
for (const f of drills) {
  const id = f.replace('.drill.yaml', '')
  const r = run(join(examples, f), '--all', '--lang', LANG[id] ?? 'en', '--out', work)
  ok(r.status === 0 && existsSync(join(work, `${id}.drill.html`)) && existsSync(join(work, `${id}.facilitator.md`)), `${id}: game and facilitator's script`, r.stdout + r.stderr)
  ok(!/^! /m.test(r.stdout), `${id}: nothing to look at`, r.stdout)
  // DNA 2.2.0: the paths in the script — plain Mermaid, and folded under it a visual-explainer-mermaid block
  const script = existsSync(join(work, `${id}.facilitator.md`)) ? readFileSync(join(work, `${id}.facilitator.md`), 'utf8') : ''
  const plain = /^```mermaid\nflowchart LR\n([\s\S]*?)\n```$/m.exec(script)?.[1] ?? ''
  const folded = /<details><summary>[^<]+<\/summary>\n\n```visual-explainer-mermaid\nflowchart LR\n%% title [^\n]+\n%% # [^\n]+\n%% > [^\n]+\n([\s\S]*?)\n```\n\n<\/details>/.exec(script)?.[1]
  ok(plain.includes('-->|') && folded === plain, `${id}: the paths, as plain Mermaid and as an explainer folded under it`, script.slice(0, 600))
}

// a broken file and a broken drawing say their line; nothing is written
const text = readFileSync(join(examples, 'checkout.drill.yaml'), 'utf8')
const lineOf = (t, needle) => t.split('\n').findIndex((l) => l.includes(needle)) + 1
const broken = text.replace('go: investigando-lider', 'go: lider-sumiu')
writeFileSync(join(work, 'broken.drill.yaml'), broken)
const b = run(join(work, 'broken.drill.yaml'))
ok(b.status === 1 && b.stderr.includes(`broken.drill.yaml:${lineOf(broken, 'lider-sumiu')}:`) && !existsSync(join(work, 'broken.drill.html')), 'a broken file says its line', b.stderr)
const badDraw = text.replace('      text "42%" at 470,60 size=26 color=red', '      tetx "42%" at 470,60')
writeFileSync(join(work, 'baddraw.drill.yaml'), badDraw)
const d = run(join(work, 'baddraw.drill.yaml'))
ok(d.status === 1 && d.stderr.includes(`baddraw.drill.yaml:${lineOf(badDraw, 'tetx')}:`), 'a broken drawing says its line in the file', d.stderr)

// the game loads nothing from the internet
const page = readFileSync(join(skill, 'assets/drill.html'), 'utf8')
ok(!/<(script|link|img)\b[^>]*\b(src|href)=["']?https?:/i.test(page), 'the game loads nothing from the internet')

// played to the end in a browser: the first choice the room can take, calling someone in when none can
// by the kit's browser, over the DevTools pipe
const { browser, runPage } = await import('@ruinosus/visual-explainer/kit/browser.mjs')
if (!browser()) console.log('• no Chrome here: the games were not played in a browser')
else
  for (const f of drills) {
    const id = f.replace('.drill.yaml', '')
    const html = readFileSync(join(work, `${id}.drill.html`), 'utf8').replace('</body>', `<script>
      const errs = []; addEventListener('error', (e) => errs.push(String(e.message)))
      setTimeout(() => { let steps = 0
        while (!document.querySelector('.dr-nums') && steps++ < 40) {
          const c = document.querySelector('.dr-choice:not(.blocked)') ?? document.querySelector('[data-call]')
          if (!c) break
          c.click()
        }
        const p = document.createElement('pre'); p.id = 'chalk-played'
        p.textContent = encodeURIComponent(JSON.stringify({ ended: !!document.querySelector('.dr-nums'), steps, errs })); document.body.append(p)
      }, 300)</script></body>`)
    writeFileSync(join(work, `${id}.play.html`), html)
    const r = (await runPage(join(work, `${id}.play.html`), 'played', '', { timeout: 60 })) ?? { ended: false, errs: ['the page did not answer'] }
    ok(r.ended && !r.errs.length, `${id}: played to the end in a browser (${r.steps} clicks)`, JSON.stringify(r))
  }

// --check --json, and the mod's game: the drill as read is one JSON document, and the mod's hooks/drill/play.js (built
// from src/play.ts) plays it to the same debrief as the skill's engine, on every path of the example
{
  const ex = join(skill, 'examples/checkout.drill.yaml')
  const j = spawnSync(process.execPath, [join(skill, 'scripts/build.mjs'), ex, '--check', '--json', '--lang', 'pt'], { encoding: 'utf8' })
  let doc
  try { doc = JSON.parse(j.stdout) } catch {}
  ok(j.status === 0 && doc?.format === 'incident-drill/read-v1' && Array.isArray(doc.drill?.scenes) && Array.isArray(doc.looks) && typeof doc.excerpts === 'object', '--check --json: the drill as read, what to look at and the runbook passages, one JSON document', j.stdout.slice(0, 200) + j.stderr)
  const mod = await import(pathToFileURL(join(repo, 'hooks/drill/play.js')).href)
  const eng = await import(pathToFileURL(join(skill, 'scripts/engine.mjs')).href)
  const d = doc.drill
  // every path: depth-first over the choices (and a call of each role first), each one played by both
  const paths = []
  const walk = (seq, scene, depth) => {
    const s = d.scenes.find((x) => x.id === scene)
    if (!s || s.end || depth > 12) return paths.push(seq)
    ;(s.choices ?? []).forEach((c, i) => walk([...seq, i], c.go, depth + 1))
  }
  walk([], d.start, 0)
  const playAll = (m, seq) => {
    let p = m.startPlay(d, 'pt')
    for (const r of d.roles) p = m.call(d, p, r.id, 'pt')
    for (const i of seq) p = m.choose(d, p, i, 'pt')
    return m.debrief(d, p, doc.looks, 'pt').markdown
  }
  const same = paths.every((seq) => playAll(mod, seq) === playAll(eng, seq))
  ok(paths.length >= 3 && same, `the mod's game plays all ${paths.length} paths of the example to the same debrief as the engine`)
}

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ incident-drill checks ok')
