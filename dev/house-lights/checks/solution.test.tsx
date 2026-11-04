// /solution in Claude Code's own harness: an opening-night solution in a pane — each piece and where it stands — and a
// lens that fell behind the way made again from it, only at a second press. A .solution.yaml that breaks its format is
// refused when written. The engine beneath is a fake: node answered with what opening-night's --check --json prints.
import { expect, test } from 'claude-code/testing'

const piece = (kind: string, file: string, extra: object = {}) => ({ kind, file, skill: 'x', state: 'ok', said: [], looks: [], ...extra })
const READ = (stale: boolean) => ({
  format: 'opening-night/read-v1', name: 'Central de atendimento', about: '', lang: 'pt', file: 'desk.solution.yaml',
  pieces: [piece('way', 'desk.way.yaml'), piece('sim', 'desk.sim', stale ? { stale: true, looks: ['desk.sim veio de uma versão anterior'] } : {}), piece('drill', 'desk.drill.yaml', { state: 'broken', said: ['✗ desk.drill.yaml:3: every «go» is a scene'] })],
})

function engine(on: any, opts: { runs?: string[][]; stale?: () => boolean } = {}) {
  on('command.register', (_: any, e: any) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000_000 }))
  on('env.get', (_: any, e: any) => ({ value: e.name === 'HOME' ? '/home/me' : e.name === 'TMPDIR' ? '/tmp' : undefined }))
  on('fs.exists', (_: any, e: any) => ({ value: !String(e.path).includes('missing') }))
  on('fs.write', () => ({ value: undefined }))
  on('process.run', (_: any, e: any) => {
    const argv: string[] = [...e.argv]
    opts.runs?.push(argv)
    if (argv[0] === 'node' && argv[1]!.includes('/opening-night/')) {
      if (argv.includes('--format')) return { value: argv[2]!.includes('broken') ? { exitCode: 1, stdout: '', stderr: '✗ broken.solution.yaml:4: «simulation» is not a field of a solution\n' } : { exitCode: 0, stdout: '✓ ok', stderr: '' } }
      return { value: { exitCode: 4, stdout: JSON.stringify(READ(opts.stale ? opts.stale() : true)), stderr: '' } }
    }
    return { value: { exitCode: 0, stdout: '✓ ok', stderr: '' } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
}
const pane = { plugin: 'house-lights', component: 'Pane', requestId: 'house-lights-solution', surface: 'terminal', props: { title: 'x', isFocused: false, bodyColumns: 120, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} } } as const

test('/solution shows each piece and where it stands; a lens behind the way is made again only at a second press', async ($, on) => {
  const runs: string[][] = []
  let stale = true
  engine(on, { runs, stale: () => stale })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const r = JSON.stringify(await $.command.run({ command: 'solution', args: '/repo/desk.solution.yaml' } as any))
  expect(r).toContain('sim: desk.sim — atrás do way')
  expect(r).toContain('drill: desk.drill.yaml — não passa no check')
  const p = await $.ui.mount(pane)
  expect((await p.find({ type: 'Text', text: /every «go»/ }))?.text).toContain('desk.drill.yaml:3')
  expect((await p.find({ type: 'Text', text: /para ver: \/way-preview/ }))?.text).toContain('/repo/desk.way.yaml')
  await p.press({ key: 'r:sim' })
  expect(runs.some((a) => a.includes('--lens'))).toBe(false) // the first press only asks
  expect(String(((await p.find({ type: 'Button', key: 'r:sim' })) as any)?.props?.label)).toContain('Certeza?')
  stale = false
  await p.press({ key: 'r:sim' })
  const lens = runs.find((a) => a.includes('--lens'))!
  expect(lens.slice(2)).toEqual(['/repo/desk.way.yaml', '--lens', 'sim', '--lang', 'pt', '--write', '--force'])
  expect((await p.find({ type: 'Text', text: /desk\.sim —/ }))?.text).toContain('refeito a partir do way')
  await p.unmount()
})

test('a .solution.yaml that breaks its format is refused when written; one that is not there is said', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const out = JSON.stringify(await $.tool.call({ tool: 'Write', file_path: '/repo/broken.solution.yaml', content: 'format: opening-night/v1\nsimulation: x.sim' }))
  expect(out).toContain('is not a valid solution yet')
  expect(out).toContain('«simulation» is not a field')
  expect(JSON.stringify(await $.tool.call({ tool: 'Write', file_path: '/repo/fine.solution.yaml', content: 'format: opening-night/v1' }))).not.toContain('not a valid')
  expect(JSON.stringify(await $.command.run({ command: 'solution', args: '~/missing.solution.yaml' } as any))).toContain('could not read ~/missing.solution.yaml: no such file')
})
