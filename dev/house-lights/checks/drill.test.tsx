// /drill in Claude Code's own harness: a whole game by the pane's buttons — a choice the room cannot do (blocked), a
// call, the end — then the debrief, saved beside the drill, and a new game. The engine beneath is a fake: node answered
// with what dress-rehearsal's --check --json prints for a small drill written here.
import { expect, test } from 'claude-code/testing'

const DRILL = {
  format: 'dress-rehearsal/read-v1', looks: [], excerpts: {},
  drill: {
    name: 'Checkout down at 3', clock: '03:12', impact: 'lost orders', call_minutes: 3,
    roles: [{ id: 'oncall', name: 'On call', you: true }, { id: 'release', name: 'Release', can: ['rollback'] }],
    start: 'alarm',
    scenes: [
      { id: 'alarm', says: 'The payment errors alarm goes off.', injects: [{ at: '03:13', says: 'Support: customers cannot pay' }], choices: [
        { label: 'Roll back the deploy', go: 'fixed', needs: 'rollback', minutes: 5, runbook: '§2' },
        { label: 'Wait and see', go: 'worse', minutes: 20, lost: 900 },
      ] },
      { id: 'fixed', says: 'Payments are back.', end: 'resolved' },
      { id: 'worse', says: 'The queue of failed orders grows.', end: 'worse' },
    ],
  },
}

function engine(on: any, writes: Record<string, string>) {
  on('command.register', (_: any, e: any) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('clock.now', () => ({ value: 1_000_000 }))
  on('env.get', () => ({ value: undefined }))
  on('fs.write', (_: any, e: any) => {
    writes[e.path] = e.text
    return { value: undefined }
  })
  on('process.run', (_: any, e: any) => {
    const argv: string[] = [...e.argv]
    if (argv[0] === 'node' && argv[1]!.includes('/dress-rehearsal/') && argv.includes('--json')) {
      return { value: argv[2]!.includes('broken') ? { exitCode: 1, stdout: '', stderr: '✗ broken.drill.yaml:1: «format» must be dress-rehearsal/v1\n' } : { exitCode: 0, stdout: JSON.stringify(DRILL), stderr: '' } }
    }
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
}
const pane = (surface: 'terminal' | 'desktop') => ({ plugin: 'house-lights', component: 'Pane', requestId: 'house-lights-drill', surface, props: { title: 'x', isFocused: false, bodyColumns: 120, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} } }) as const

for (const surface of ['terminal', 'desktop'] as const) {
  test(`a whole drill by the pane's buttons, then its debrief saved beside it (${surface})`, async ($, on) => {
    const writes: Record<string, string> = {}
    engine(on, writes)
    await $.session.start({ cwd: '/repo', surface, isInteractive: true })
    const r = await $.command.run({ command: 'drill', args: '/repo/checkout.drill.yaml' } as any)
    expect(JSON.stringify(r)).toContain('the drill is in the pane')
    const p = await $.ui.mount(pane(surface))
    expect((await p.find({ type: 'Text', text: /03:12/ }))?.text).toContain('In the room: On call')
    expect((await p.find({ type: 'Text', text: /Support:/ }))?.text).toContain('03:13 Support: customers cannot pay')
    // the rollback needs someone the room does not have: noted, nothing else changes
    expect(String(((await p.find({ type: 'Button', key: 'c:0' })) as any)?.props?.label)).toContain('needs «rollback»')
    await p.press({ key: 'c:0' })
    expect((await p.find({ type: 'Text', text: /payment errors alarm/ }))?.text).toBeTruthy()
    // call Release (3 minutes), then roll back (5): resolved at 03:20
    await p.press({ key: 'r:release' })
    expect((await p.find({ type: 'Text', text: /03:15/ }))?.text).toContain('On call, Release')
    await p.press({ key: 'c:0' })
    expect((await p.find({ type: 'Text', text: /Resolved · Debrief/ }))?.text).toBeTruthy()
    expect((await p.find({ type: 'Text', text: /To resolve: 8 min/ }))?.text).toContain('To tell the people affected: did not happen')
    expect((await p.find({ type: 'Text', text: /nobody in the room could/ }))?.text).toContain('can: Release')
    await p.press({ key: 'save' })
    expect(writes['/repo/checkout.debrief.md']).toContain('# Debrief: Checkout down at 3')
    expect((await p.find({ type: 'Text', text: /Saved:/ }))?.text).toContain('/repo/checkout.debrief.md')
    // a new game starts at the alarm
    await p.press({ key: 'again' })
    expect((await p.find({ type: 'Text', text: /03:12/ }))?.text).toContain('0 lost orders')
    await p.unmount()
  })
}

test('/drill says why a drill cannot be played, and with no drill asks for one', async ($, on) => {
  engine(on, {})
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  expect(JSON.stringify(await $.command.run({ command: 'drill', args: '' } as any))).toContain('name a drill')
  expect(JSON.stringify(await $.command.run({ command: 'drill', args: '/repo/broken.drill.yaml' } as any))).toContain('«format» must be dress-rehearsal/v1')
})
