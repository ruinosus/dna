#!/usr/bin/env node
// house-lights <skill> <file or folder> [options]: runs that skill's build with the same options, and gives back its exit code.
import { spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SKILLS = {
  'chalk-talk': 'teach an idea by drawing it — a lesson from a .chalk, .json or .mmd recipe',
  'back-of-napkin': 'present by drawing — a pitch, an architecture, a decision, data, a timeline or a story (.chalk)',
  'dress-rehearsal': 'play an incident drill made from a runbook (.drill.yaml)',
  'gates-and-handoffs': "map a team's way of working — stages, gates, roles, outputs (.way.yaml)",
  'service-blueprint': 'map a customer journey and who makes each moment happen (.blueprint.yaml)',
  'cast-list': 'compare Copilot Studio agents: patterns, who is off them, what is missing (a folder of cloned agents)',
  'box-office': 'simulate a process and ask «what if»: queues, people, assistants and costs (.sim)',
  'opening-night': 'put a process together as a solution: every piece checked, one page with a tab each (.solution.yaml)',
}
const [skill, ...args] = process.argv.slice(2)
const build = join(dirname(fileURLToPath(import.meta.url)), 'skills', skill ?? '', 'scripts/build.mjs')
if (!SKILLS[skill] || !existsSync(build)) {
  if (skill) console.error(`house-lights: no skill named «${skill}».`)
  console.error('usage: npx house-lights <skill> <file or folder> [options]   (the options are the skill\'s own)\n')
  for (const [name, what] of Object.entries(SKILLS)) console.error(`  ${name.padEnd(19)} ${what}`)
  process.exit(1)
}
const r = spawnSync(process.execPath, [build, ...args], { stdio: 'inherit' })
process.exit(r.status ?? 1)
