// The kinds of the Microsoft schema, read the way its own reader reads them: the same list as
// `schema-lookup.bundle.js kinds`, with the kinds the example agents use, and nothing made up.
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { knownKinds } from '../src/kinds'

const vendor = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/vendor/microsoft')
const schema = JSON.parse(readFileSync(join(vendor, 'reference/bot.schema.yaml-authoring.json'), 'utf8'))
let failed = 0
const ok = (cond: boolean, what: string, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}${!cond && detail ? `\n${detail}` : ''}`)
  if (!cond) failed++
}

const kinds = knownKinds(schema)
const theirs = execFileSync(process.execPath, [join(vendor, 'scripts/schema-lookup.bundle.js'), 'kinds'], { encoding: 'utf8' })
  .split('\n').filter((l) => l.startsWith('  - ')).map((l) => l.slice(4))
ok(theirs.length > 400 && [...kinds].sort().join() === theirs.join(), `the same ${kinds.size} kinds as the Microsoft reader`, `${kinds.size} ≠ ${theirs.length}`)
const used = ['AdaptiveDialog', 'TaskDialog', 'AgentDialog', 'OnRedirect', 'OnEscalate', 'OnToolSelected', 'InvokeConnectedAgentTaskAction', 'LogCustomTelemetryEvent', 'KnowledgeSourceConfiguration', 'SharePointSearchSource', 'ConnectionReferencesSourceFile', 'GptComponentMetadata']
ok(used.every((k) => kinds.has(k)), 'the kinds the example agents use are there', used.filter((k) => !kinds.has(k)).join(', '))
ok(!kinds.has('Inventado') && !kinds.has(''), 'a made-up kind is not')
process.exit(failed ? 1 : 0)
