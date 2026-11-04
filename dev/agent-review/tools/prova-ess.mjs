// The proof on a real public cast: Microsoft's Employee Self-Service sample (MIT), cloned outside this repository, read
// by agent-review. The sample is topics, not cloned agents (no agent.mcs.yml), so each of its groups — Workday,
// WorkdayDA, Facilities — becomes an agent in a temporary folder: a minimal agent.mcs.yml and its topics as they are.
// The XML templates of the Workday calls stay out (a clone of an agent has none). Not part of the checks: the sample is
// not in the repository; it runs when its folder is there.
//
//   node dev/agent-review/tools/prova-ess.mjs [<EmployeeSelfServiceAgent folder>] [--lang en|pt] [--out <folder>]
import { spawnSync } from 'node:child_process'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '../../..')
const args = process.argv.slice(2)
const option = (n) => (args.includes(n) ? args[args.indexOf(n) + 1] : undefined)
const sample = resolve(args.find((a, i) => !a.startsWith('--') && !['--lang', '--out'].includes(args[i - 1])) ?? join(repo, '../_referencias/copilot-studio-samples/EmployeeSelfServiceAgent'))
if (!existsSync(sample)) {
  console.log(`• no sample at ${sample}: clone github.com/microsoft/CopilotStudioSamples and point at its EmployeeSelfServiceAgent folder`)
  process.exit(0)
}
const work = mkdtempSync(join(tmpdir(), 'prova-ess-'))
const agents = join(work, 'ess')
const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]))
const GROUPS = { Workday: 'ess-workday', WorkdayDA: 'ess-workday-da', Facilities: 'ess-facilities' }
for (const [group, id] of Object.entries(GROUPS)) {
  const from = join(sample, group)
  if (!existsSync(from)) continue
  const to = join(agents, id)
  mkdirSync(join(to, 'topics'), { recursive: true })
  writeFileSync(join(to, 'agent.mcs.yml'), `kind: GptComponentMetadata\ndisplayName: Employee Self-Service - ${group}\ninstructions: Help employees with ${group === 'Facilities' ? 'facilities' : 'their Workday data'}.\n`)
  for (const f of walk(from).filter((x) => /\.ya?ml$/.test(x))) {
    // topic.yaml takes its scenario's folder name; msdyn_<schema>.topic.<Name>.yaml keeps its <Name>
    const name = basename(f) === 'topic.yaml' ? basename(dirname(f)) : basename(f).replace(/\.ya?ml$/, '').replace(/^.*\.topic\./, '')
    cpSync(f, join(to, 'topics', `${name}.topic.mcs.yml`))
  }
}
const out = resolve(option('--out') ?? join(work, 'out'))
const r = spawnSync(process.execPath, [join(repo, 'skills/agent-review/scripts/build.mjs'), agents, '--all', '--lang', option('--lang') ?? 'pt', '--out', out], { encoding: 'utf8' })
process.stdout.write(r.stdout)
process.stderr.write(r.stderr)
console.log(`• the sample read as ${readdirSync(agents).length} agents in ${agents}; the outputs in ${out}`)
process.exit(r.status ?? 1)
