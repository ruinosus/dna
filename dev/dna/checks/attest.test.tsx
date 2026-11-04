// /attest in Claude Code's own harness: the verdict on a simulation's receipt, from process-simulation's own --attest
// (the engine beneath is a fake: node answered as build.mjs --attest does), with the recipe named or the last one read.
import { expect, test } from 'claude-code/testing'

function engine(on: any, runs: string[][], verdict: { exitCode: number; stdout: string }) {
  on('command.register', (_: any, e: any) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000_000 }))
  on('env.get', (_: any, e: any) => ({ value: e.name === 'HOME' ? '/home/me' : undefined }))
  on('fs.exists', () => ({ value: true }))
  on('process.run', (_: any, e: any) => {
    runs.push([...e.argv])
    return { value: { exitCode: verdict.exitCode, stdout: verdict.stdout, stderr: '' } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
}

test('/attest runs process-simulation --attest on the receipt and the recipe, and says the verdict', async ($, on) => {
  const runs: string[][] = []
  engine(on, runs, { exitCode: 0, stdout: '✓ attested: HR help desk, 3 metrics, seed 7, 10 runs\n' })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const out = await $.command.run({ command: 'attest', args: 'receipt.json examples/hr-help-desk.sim' } as any)
  expect(runs[0]!.slice(2)).toEqual(['examples/hr-help-desk.sim', '--attest', 'receipt.json'])
  expect(runs[0]![1]).toContain('/skills/process-simulation/scripts/build.mjs')
  expect(out.text).toContain('✓ attested: HR help desk')
})

test('/attest says a refusal with its reason, and asks for the recipe when none is named or read', async ($, on) => {
  const runs: string[][] = []
  engine(on, runs, { exitCode: 3, stdout: '✗ hr_partners=50 is outside 4..30\n' })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const refused = await $.command.run({ command: 'attest', args: '~/r.json desk.sim' } as any)
  expect(refused.text).toContain('✗ hr_partners=50 is outside 4..30')
  expect(runs[0]!.slice(2)).toEqual(['desk.sim', '--attest', '/home/me/r.json'])
  const none = await $.command.run({ command: 'attest', args: '' } as any)
  expect(none.text).toContain('/attest <receipt.json> [file.sim]')
  const noRecipe = await $.command.run({ command: 'attest', args: 'r.json' } as any)
  expect(noRecipe.text).toContain('name the recipe')
})
