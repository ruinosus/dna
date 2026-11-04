#!/usr/bin/env node
// The attester of a DNA simulation in an OKF bundle (references/attesters/process-simulation.mjs): takes a run's receipt
// and says whether it holds — the recipe the receipt names is the bundle's computation, the parameters are declared and
// in range, the engine is this one, and the numbers come out again from the same seed and parameters. Deterministic:
// no model, no network, no dependency; the engine is engine.mjs, beside this file. Copied into the bundle by the
// solution skill's --okf; it only runs there.
//
//   node process-simulation.mjs <receipt.json> [--json]
//
// Exit codes: 0 attested; 3 refused (with the reason); 2 bad arguments or a receipt that is not JSON.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ATTEST, SIMLANG } from './engine.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const argv = process.argv.slice(2)
const json = argv.includes('--json')
const files = argv.filter((a) => !a.startsWith('--'))
const usage = 'usage: node process-simulation.mjs <receipt.json> [--json]'
const fail = (msg) => {
  console.error(`${msg}\n${usage}`)
  process.exit(2)
}
if (files.length !== 1 || argv.some((a) => a.startsWith('--') && a !== '--json')) fail('✗ name one receipt')
let receipt
try {
  receipt = JSON.parse(readFileSync(files[0], 'utf8'))
} catch {
  fail(`✗ ${files[0]} is not a JSON receipt`)
}
// the Attested Computation this attester belongs to: its computation (the recipe) and the engine it was written with
const conceptPath = join(here, '../../computations/simulation.md')
const concept = readFileSync(conceptPath, 'utf8')
const computation = /^computation: "?([^"\n]+?)"?\s*$/m.exec(concept)?.[1]
const engine = /^dna: \{.*\bengine: ([^,\s}]+)/m.exec(concept)?.[1]
if (!computation || !engine) fail(`✗ ${conceptPath} has no computation or engine`)
const recipe = readFileSync(resolve(dirname(conceptPath), computation), 'utf8')
const v = ATTEST.attest(receipt, recipe, engine)
if (json) console.log(JSON.stringify({ format: 'dna/process-simulation/verdict-v1', ok: v.ok, ...(v.reason ? { reason: v.reason } : {}), checked: v.checked }, null, 2))
else if (v.ok) console.log(`✓ attested: ${SIMLANG.parse(recipe).model.name}, ${receipt.rows.length} metrics, seed ${receipt.seed}, ${receipt.runs} runs`)
else console.log(`✗ ${v.reason}`)
process.exit(v.ok ? 0 : 3)
