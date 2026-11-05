#!/usr/bin/env node
// dna <skill> <file or folder> [options]: runs that skill's build with the same options, and gives back its exit code.
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SKILLS = {
  'visual-explainer': 'teach an idea by drawing it — an explainer from a .chalk, .json or .mmd recipe',
  'visual-pitch': 'present by drawing — a pitch, an architecture, a decision, data, a timeline or a story (.chalk)',
  'incident-drill': 'play an incident drill made from a runbook (.drill.yaml)',
  'way-of-working': "map a team's way of working — stages, gates, roles, outputs (.way.yaml)",
  'service-blueprint': 'map a customer journey and who makes each moment happen (.blueprint.yaml)',
  'agent-review': 'compare Copilot Studio agents: patterns, who is off them, what is missing (a folder of cloned agents)',
  'process-simulation': 'simulate a process and ask «what if»: queues, people, assistants and costs (.sim)',
  'solution': 'put a process together as a solution: every piece checked, one page with a tab each (.solution.yaml)',
}
const [skill, ...args] = process.argv.slice(2)
const build = join(dirname(fileURLToPath(import.meta.url)), 'skills', skill ?? '', 'scripts/build.mjs')
if (!SKILLS[skill] || !existsSync(build)) {
  if (skill) console.error(`dna: no skill named «${skill}».`)
  console.error('usage: npx @ruinosus/dna <skill> <file or folder> [options]   (the options are the skill\'s own)\n')
  for (const [name, what] of Object.entries(SKILLS)) console.error(`  ${name.padEnd(19)} ${what}`)
  process.exit(1)
}
const r = spawnSync(process.execPath, [build, ...args], { stdio: 'inherit' })
process.exit(r.status ?? 1)
