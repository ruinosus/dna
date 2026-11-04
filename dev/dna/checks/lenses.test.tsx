// /lenses in Claude Code's own harness: a way of working seen by the other skills, each lens written beside it at a
// press (and checked by its skill), one that differs asked about before it is written over, and a toast when the way
// changes under a lens. The engine beneath is a fake: node answered with what way-of-working --lens prints.
import { expect, test } from 'claude-code/testing'

const lens = (kind: string, v: string) => `# from: team.way.yaml@${v}\n# a ${kind} lens\n`

function engine(on: any, files: Record<string, string>, opts: { version?: () => string; toasts?: string[]; runs?: string[][] } = {}) {
  on('command.register', (_: any, e: any) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_: any, e: any) => (opts.toasts?.push(String(e.text ?? e.message ?? JSON.stringify(e))), { value: undefined }))
  on('clock.now', () => ({ value: 1_000_000 }))
  on('env.get', (_: any, e: any) => ({ value: e.name === 'HOME' ? '/home/me' : e.name === 'TMPDIR' ? '/tmp' : undefined }))
  on('fs.exists', (_: any, e: any) => ({ value: e.path in files }))
  on('fs.read', (_: any, e: any) => (e.path in files ? { value: files[e.path] } : { deny: `ENOENT ${e.path}` }))
  on('fs.write', (_: any, e: any) => ((files[e.path] = e.text), { value: undefined }))
  on('process.run', (_: any, e: any) => {
    const argv: string[] = [...e.argv]
    opts.runs?.push(argv)
    if (argv[0] === 'node' && argv.includes('--lens')) {
      const kind = argv[argv.indexOf('--lens') + 1]!
      if (argv[2]!.includes('broken')) return { value: { exitCode: 1, stdout: '', stderr: '✗ broken.way.yaml:3: «stages» must be a list\n' } }
      return { value: { exitCode: 0, stdout: lens(kind, opts.version ? opts.version() : 'aaaa1111'), stderr: `• ${kind === 'sim' ? 17 : 7} numbers or lines bet (# bet:): replace them with your own\n` } }
    }
    if (argv[0] === 'node' && argv.includes('--check')) return { value: { exitCode: 0, stdout: `✓ ${argv[2]!.split('/').pop()}: no problems\n`, stderr: '' } }
    return { value: { exitCode: 0, stdout: '✓ ok', stderr: '' } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
}
const pane = { plugin: 'dna', component: 'Pane', requestId: 'dna-lenses', surface: 'terminal', props: { title: 'x', isFocused: false, bodyColumns: 120, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} } } as const

test('/lenses shows the three lenses and writes one beside the way at a press, checked by its own skill', async ($, on) => {
  const files: Record<string, string> = { '/repo/team.way.yaml': 'way' }
  const runs: string[][] = []
  engine(on, files, { runs })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const r = JSON.stringify(await $.command.run({ command: 'lenses', args: '/repo/team.way.yaml --lang pt' } as any))
  expect(r).toContain('sim: team.sim · 17 apostas (# bet:) para trocar')
  expect(r).toContain('drill: team.drill.yaml')
  const p = await $.ui.mount(pane)
  await p.press({ key: 'w:sim' })
  expect(files['/repo/team.sim']).toBe(lens('sim', 'aaaa1111'))
  expect(runs.some((a) => a[1]!.includes('/process-simulation/') && a.includes('--check'))).toBe(true)
  expect((await p.find({ type: 'Text', text: /Gravado:/ }))?.text).toContain('/repo/team.sim')
  expect((await p.find({ type: 'Text', text: /no problems/ }))?.text).toContain('team.sim')
  expect((await p.find({ type: 'Text', text: /Para ver:/ }))?.text).toContain('/simulation-preview team.sim')
  await p.unmount()
})

test('a lens beside the way that differs is asked about before it is written over', async ($, on) => {
  const files: Record<string, string> = { '/repo/team.way.yaml': 'way', '/repo/team.blueprint.yaml': lens('blueprint', 'aaaa1111') + 'edited by hand\n' }
  engine(on, files)
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'lenses', args: '/repo/team.way.yaml' } as any)
  const p = await $.ui.mount(pane)
  expect((await p.find({ type: 'Text', text: /differs/ }))?.text).toContain('edited by hand?')
  await p.press({ key: 'w:blueprint' })
  expect(files['/repo/team.blueprint.yaml']).toContain('edited by hand') // the first press only asks
  expect(String(((await p.find({ type: 'Button', key: 'w:blueprint' })) as any)?.props?.label)).toContain('Sure?')
  await p.press({ key: 'w:blueprint' })
  expect(files['/repo/team.blueprint.yaml']).toBe(lens('blueprint', 'aaaa1111'))
  await p.unmount()
})

test('a way changed under a lens gets a toast; a way that breaks its format is said', async ($, on) => {
  const files: Record<string, string> = { '/repo/team.way.yaml': 'way', '/repo/team.sim': lens('sim', 'aaaa1111') }
  const toasts: string[] = []
  let v = 'aaaa1111'
  engine(on, files, { toasts, version: () => v })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await $.tool.call({ tool: 'Write', file_path: '/repo/team.way.yaml', content: 'way' })
  expect(toasts.length).toBe(0) // the same version: nothing to say
  v = 'bbbb2222'
  await $.tool.call({ tool: 'Write', file_path: '/repo/team.way.yaml', content: 'way, changed' })
  expect(toasts.join('\n')).toContain('team.sim came from an earlier version of the way — /lenses team.way.yaml')
  files['/repo/broken.way.yaml'] = 'x'
  expect(JSON.stringify(await $.command.run({ command: 'lenses', args: '/repo/broken.way.yaml' } as any))).toContain('«stages» must be a list')
  expect(JSON.stringify(await $.command.run({ command: 'lenses', args: '/repo/notes.md' } as any))).toContain('no such file')
})
