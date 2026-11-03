// The example as a person runs it in full: the agents, the team's profile, the demo's cast file with the inventory and
// the team spreadsheet taken, and the export of Application Insights — what the RH and the stage are checked on.
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { readCast, type Cast } from '../src/cast'
import { compare, type Fired } from '../src/compare'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { applyChanges } from '../src/fromSheets'
import { readProfile } from '../src/profile'
import { reviewCast } from '../src/review'
import { declaredFrom, firedFrom, mergeDeclared, readCsv } from '../src/tables'
import { evalsFrom } from '../src/evals'

export const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/examples')
const csv = (f: string) => readCsv(readFileSync(join(examples, f), 'utf8'), '')
export const found = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
export const profile = readProfile(readFileSync(join(examples, 'profile.cast.yaml'), 'utf8')).profile!
export const demo = readCast(readFileSync(join(examples, 'demo.cast.yaml'), 'utf8')).cast!
const tables = (cast: Cast, files: string[]) => {
  const changes = mergeDeclared(files.flatMap((f) => declaredFrom(csv(f), found, cast, { file: f, lang: 'pt' }).changes))
  return applyChanges(cast, changes, changes.map((c) => c.key))
}
/** The two example exports of the Evaluate tab. */
export const evals = evalsFrom(readdirSync(join(examples, 'avaliacoes')).sort().map((name) => ({ name: `avaliacoes/${name}`, table: readCsv(readFileSync(join(examples, 'avaliacoes', name), 'utf8'), '') })), found).sets
export const fired = firedFrom(csv('telemetria.csv'), found, { file: 'telemetria.csv', days: 30 }) as Fired
/** The run with these tables taken (both by default) and, unless told not to, the telemetry. */
export function run(files = ['inventario.csv', 'equipe.csv'], telemetry = true) {
  const cast = tables(demo, files)
  const result = compare(found, profile, cast, telemetry ? fired : undefined)
  return { cast, result, looks: reviewCast(result) }
}
