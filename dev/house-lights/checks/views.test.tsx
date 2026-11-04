// The mod's panes in Claude Code's own harness: the recipes' preview (a way of working, a service blueprint) and /cast
// (cast-list's comparison, and the toast when an agent edited in the compared folder changes it). The engine beneath is
// a fake: files in memory, node answered here with what each skill's --check (--json) prints.
import { expect, test } from 'claude-code/testing'

const WAY = {
  format: 'gates-and-handoffs/read-v1', name: 'Entrega de agente', looks: [{ en: 'QA approves its own work', pt: 'QA aprova o próprio trabalho' }],
  way: {
    lanes: [{ id: 'prod', name: 'Produto' }, { id: 'qa', name: 'Qualidade' }],
    roles: [{ id: 'po', acronym: 'PO', name: 'Product Owner' }, { id: 'qa', acronym: 'QA', name: 'Qualidade' }],
    phases: [{ id: 'd', name: 'Descoberta' }, { id: 'e', name: 'Entrega' }],
    stages: [{ id: 'triagem', name: 'Triagem', phase: 'd', lane: 'prod', roles: ['po'] }, { id: 'avaliacao', name: 'Avaliação', phase: 'e', lane: 'qa', roles: ['qa'] }],
    gates: [{ id: 'g', after: 'avaliacao', name: 'Acerto ≥ 85%?', approvals: [{ by: 'qa' }, { by: 'po', when: 'dado de colaborador' }] }],
  },
}
const BLUEPRINT = {
  format: 'service-blueprint/read-v1', looks: [],
  blueprint: {
    name: 'Joining a gym', who: 'A new member', phases: [{ id: 'join', name: 'Join' }], systems: [{ id: 'billing', name: 'Billing' }],
    actors: [{ id: 'desk', name: 'Front desk', layer: 'front' }],
    moments: [{ id: 'sign', phase: 'join', customer: 'Signs up at the desk', feels: 2, front: [{ actor: 'desk', does: 'Fills the form' }], support: ['billing'], pains: [{ says: 'Twenty minutes' }] }],
  },
}
const CAST1 = '✓ 6 no elenco: 1 orquestrador, 5 especialistas\n✓ 38 padrões · 3 fora do padrão · 4 só um tem\n▸ Contradições · 1\n! para olhar: bodega-devolucoes tem «Só o conhecimento»\n▸ Fora do padrão · 2\n! para olhar: 1 especialista não escala (bodega-frete)\n! para olhar: 1 especialista não registra telemetria\n• os arquivos têm dados do cliente\n'
const CAST2 = CAST1.replace('▸ Fora do padrão · 2', '▸ Fora do padrão · 3') + ''
const CAST2_FULL = CAST2.replace('! para olhar: 1 especialista não registra telemetria\n', '! para olhar: 1 especialista não registra telemetria\n! para olhar: bodega-pedidos não tem histórico\n')

function engine(on: any, opts: { toasts?: string[]; cast?: () => string } = {}) {
  const files: Record<string, string> = { '/repo/team.way.yaml': 'way', '/repo/gym.blueprint.yaml': 'blueprint' }
  on('command.register', (_: any, e: any) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_: any, e: any) => {
    opts.toasts?.push(String(e.text ?? e.message ?? JSON.stringify(e)))
    return { value: undefined }
  })
  on('clock.now', () => ({ value: 1_000_000 }))
  on('env.get', (_: any, e: any) => ({ value: e.name === 'TMPDIR' ? '/tmp' : undefined }))
  on('fs.read', (_: any, e: any) => (e.path in files ? { value: files[e.path] } : { deny: `ENOENT ${e.path}` }))
  on('fs.write', (_: any, e: any) => {
    files[e.path] = e.text
    return { value: undefined }
  })
  on('fs.exists', () => ({ value: true }))
  on('fs.list', () => ({ value: [] }))
  on('fs.stat', (_: any, e: any) => ({ value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false, realPath: e.path.startsWith('/') ? e.path : `/repo/${e.path.replace(/\/$/, '')}` } }))
  on('process.run', (_: any, e: any) => {
    const argv: string[] = [...e.argv]
    if (argv[0] !== 'node') return { value: { exitCode: 0, stdout: '', stderr: '' } }
    if (argv[1]!.includes('/cast-list/')) return { value: { exitCode: 0, stdout: opts.cast ? opts.cast() : CAST1, stderr: '' } }
    const json = argv[1]!.includes('/gates-and-handoffs/') ? WAY : argv[1]!.includes('/service-blueprint/') ? BLUEPRINT : undefined
    return { value: { exitCode: 0, stdout: json && argv.includes('--json') ? JSON.stringify(json) : '✓ ok', stderr: '' } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
}
const start = ($: any) => $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
const pane = (requestId: string, surface: 'terminal' | 'desktop') => ({ plugin: 'house-lights', component: 'Pane', requestId, surface, props: { title: 'x', isFocused: false, bodyColumns: 120, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} } }) as const

test('a valid way of working written opens the preview: stages in lanes on desktop, phases as text in the terminal, in EN and PT', async ($, on) => {
  engine(on)
  await start($)
  const out = await $.tool.call({ tool: 'Write', file_path: '/repo/team.way.yaml', content: 'stages: fine' })
  expect(JSON.stringify(out)).not.toContain('is not a valid')
  const desk = await $.ui.mount(pane('house-lights-recipe', 'desktop'))
  const svg = String(((await desk.find({ type: 'Svg' })) as any)?.props?.source ?? '')
  expect(svg).toContain('Triagem')
  expect(svg).toContain('>Acerto ≥ 85%?<')
  expect(svg).toContain('>QA + PO<') // who approves on a line of its own, never cut off by the name
  await desk.unmount()
  const term = await $.ui.mount(pane('house-lights-recipe', 'terminal'))
  const line = await term.find({ type: 'Text', text: /◆ Acerto/ })
  expect(line?.text).toContain('Entrega: Avaliação [QA] ◆ Acerto ≥ 85%? (QA+PO)')
  expect((await term.find({ type: 'Text', text: /1 to look at/ }))?.text).toContain('1 to look at')
  await term.press({ key: 'lang' })
  expect((await term.find({ type: 'Text', text: /QA aprova/ }))?.text).toContain('QA aprova o próprio trabalho')
  await term.unmount()
})

test('/blueprint-preview checks the file and shows its moments', async ($, on) => {
  engine(on)
  await start($)
  const r = await $.command.run({ command: 'blueprint-preview', args: '/repo/gym.blueprint.yaml' } as any)
  expect(JSON.stringify(r)).toContain('preview pane opened')
  const term = await $.ui.mount(pane('house-lights-recipe', 'terminal'))
  const line = await term.find({ type: 'Text', text: /Signs up/ })
  expect(line?.text).toContain('1. Signs up at the desk — feels 2/5 · 1 pain · On stage: Front desk: Fills the form · Systems: Billing')
  await term.unmount()
  const desk = await $.ui.mount(pane('house-lights-recipe', 'desktop'))
  expect(String(((await desk.find({ type: 'Svg' })) as any)?.props?.source ?? '')).toContain('Signs up at the desk')
  await desk.unmount()
})

test('/cast compares a folder: the summary and the groups, each opening at a press', async ($, on) => {
  engine(on)
  await start($)
  const r = await $.command.run({ command: 'cast', args: 'agents --lang pt' } as any)
  expect(JSON.stringify(r)).toContain('▸ Fora do padrão · 2')
  const term = await $.ui.mount(pane('house-lights-cast', 'terminal'))
  expect((await term.find({ type: 'Text', text: /6 no elenco/ }))?.text).toContain('1 orquestrador')
  await term.press({ key: 'g:Fora do padrão' })
  expect((await term.find({ type: 'Text', text: /não escala/ }))?.text).toContain('bodega-frete')
  await term.unmount()
})

test('after /cast, an agent edited in that folder compares again and a toast says what came to look at', async ($, on) => {
  const toasts: string[] = []
  let now = CAST1
  engine(on, { toasts, cast: () => now })
  await start($)
  await $.command.run({ command: 'cast', args: '/repo/agents --lang pt' } as any)
  now = CAST2_FULL
  await $.tool.call({ tool: 'Write', file_path: '/repo/agents/bodega-pedidos/agent.mcs.yml', content: 'kind: GptComponentMetadata' })
  expect(toasts.join('\n')).toContain('cast-list: +1 para olhar — bodega-pedidos não tem histórico')
  // a file outside the compared folder changes nothing
  const before = toasts.length
  await $.tool.call({ tool: 'Write', file_path: '/repo/other/agent.mcs.yml', content: 'x' })
  expect(toasts.length).toBe(before)
})
