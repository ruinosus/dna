// /attest <receipt.json> [file.sim]: the verdict on a simulation's receipt — process-simulation's own --attest, run on
// the host, with the recipe named or the last one /simulate or the guard read. Nothing is decided here: the skill's
// script runs the recipe again from the receipt's seed and controls and says whether its numbers hold.
import { atom, read } from 'claude-code'
import type { On } from 'claude-code'

import { pathOf, scriptOf } from '../recipes/run'

const last = atom({ plugin: 'dna', key: 'last' } as const, null, { shape: 'last-1' })

export function attestCommand(on: On) {
  on('command.run', { command: 'attest' }, async ($, e) => {
    const [receipt, recipe] = e.args.trim() ? e.args.trim().split(/\s+/) : []
    if (!receipt) return { text: 'use /attest <receipt.json> [file.sim] — the receipt is what process-simulation --run --receipt writes' }
    const sim = recipe ?? (await read($, last))?.path
    if (!sim) return { text: `name the recipe the receipt was made from: /attest ${receipt} <file.sim>` }
    const run = await $.process.run(['node', scriptOf($, 'process-simulation'), await pathOf($, sim), '--attest', await pathOf($, receipt)], { timeoutMs: 20000 })
    const text = (run.stdout.trim() || run.stderr.trim() || `--attest ended with exit ${run.exitCode}`).split('\n').slice(0, 12).join('\n')
    return { text, context: [`The person ran /attest on ${receipt} (recipe ${sim}): ${text}`] }
  })
}
