// Checks the skill as a person gets it: every accelerator checks clean (each piece passes its own skill's check, each
// lens up to date with its way) and makes its page, one file with a tab per piece that loads nothing from the internet;
// a broken solution file says its line and exits 1; a missing or broken piece exits 4 with its skill's messages; a lens
// left behind by a change of the way is said; --new copies an accelerator and refuses a folder that is not empty; and,
// in a browser, the page opens each tab with its piece inside.
import { checkSkillMd } from '@ruinosus/visual-explainer/kit/tools/checks.mjs'
import { browser, runPages } from '@ruinosus/visual-explainer/kit/browser.mjs'
import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
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
  ok(n.status === 0 && existsSync(join(dest, 'service-desk.solution.yaml')) && existsSync(join(dest, 'agents/bodega-frete/agent.mcs.yml')), '--new copies an accelerator, pieces and agents', n.stdout + n.stderr)
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

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ solution checks ok')
