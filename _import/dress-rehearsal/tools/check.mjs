// Checks the skill as a person gets it: the engine's checks (checks/*.check.ts); every example makes its game and its
// facilitator's script with nothing to look at; a broken file — and a broken drawing — says its line; the game page loads
// nothing from the internet; and, when there is a browser, every example is played to its end there. Run after
// npm run assets.
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = resolve(here, '..')
const skill = join(root, 'skills/dress-rehearsal')
const build = join(skill, 'scripts/build.mjs')
const examples = join(skill, 'examples')
const LANG = { checkout: 'pt', 'database-disk': 'en' }
const work = mkdtempSync(join(tmpdir(), 'dress-rehearsal-check-'))
let failed = 0
const run = (...args) => spawnSync(process.execPath, [build, ...args], { encoding: 'utf8' })
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}

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
const { browser, runPage } = await import('chalk-talk/kit/browser.mjs')
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

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ dress-rehearsal checks ok')
