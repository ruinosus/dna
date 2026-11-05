// Measures the catalog on Workday's real WSDLs (an index fetch or ingest made; the repository has only synthetic ones):
//   - the search: with each case's Workday terms, is the operation among the first three? (no model, free);
//   - with --agent: Claude with this plugin (claude -p --plugin-dir), asked in Portuguese, names which operation?
//     (about US$ 0.25 a case; --only <id,id> to run some).
//
//   node dev/workday-integration/tools/bench-real.mjs [--agent] [--only id,id] [--index <folder>]
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defaultIndexDir, Index } from '../src/index.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const plugin = join(here, '../../../plugins/workday-integration')
const argv = process.argv.slice(2)
const opt = (k) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : undefined)
const ix = new Index(opt('--index') ?? defaultIndexDir())
if (ix.empty) {
  console.error(`✗ nothing indexed in ${ix.dir}: fetch or ingest Workday's WSDLs first`)
  process.exit(2)
}
const only = opt('--only')?.split(',')
const cases = JSON.parse(readFileSync(join(here, '../bench/cases.json'), 'utf8')).cases.filter((c) => !only || only.includes(c.id))

let searchOk = 0
console.log('search (Workday terms → the first three):')
for (const c of cases) {
  const top = ix.search(c.terms, { scope: 'all', limit: 3 }).map((r) => r.operation)
  const rank = top.indexOf(c.want) + 1
  if (rank) searchOk++
  console.log(`  ${rank ? '✓' : '✗'} ${c.id.padEnd(22)} «${c.terms}» → ${rank ? `#${rank}` : 'not in the first 3'} (${top.join(', ')})`)
}
console.log(`  ${searchOk}/${cases.length}`)
if (!argv.includes('--agent')) process.exit(searchOk === cases.length ? 0 : 1)

const ask = (c) => new Promise((resolve) => {
  const prompt = `Usando a skill workday-integration (o índice já está pronto; não use a rede, não baixe nada), qual operação do Workday Web Services (SOAP) serve para ${c.ask}? Confira antes de responder. Na última linha escreva só: OPERAÇÃO: <o nome exato da operação>`
  const p = spawn('claude', ['-p', '--plugin-dir', plugin, '--allowedTools', 'Bash Skill Read', '--max-turns', '20', prompt], { stdio: ['ignore', 'pipe', 'pipe'] })
  let out = ''
  p.stdout.on('data', (d) => (out += d))
  p.on('close', () => resolve(out))
})
console.log('agent (a request in Portuguese → the operation it names):')
let agentOk = 0
for (let i = 0; i < cases.length; i += 3) {
  const batch = cases.slice(i, i + 3)
  const outs = await Promise.all(batch.map(ask))
  batch.forEach((c, k) => {
    const named = /OPERA[ÇC][ÃA]O:\s*`?([A-Za-z0-9_]+)/i.exec(outs[k])?.[1] ?? '(none)'
    const okay = named === c.want
    if (okay) agentOk++
    console.log(`  ${okay ? '✓' : '✗'} ${c.id.padEnd(22)} → ${named}${okay ? '' : ` (want ${c.want})`}`)
  })
}
console.log(`  ${agentOk}/${cases.length}`)
process.exit(searchOk === cases.length && agentOk === cases.length ? 0 : 1)
