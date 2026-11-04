import { expect, test } from 'claude-code/testing'

const CAFE = [
  'sim "Corner café"',
  'horizon 1 day',
  'arrive customer 30/hour during 7h-15h peak 8h-10h x2',
  'pool baristas $baristas shift 7h-15h',
  'step order by baristas time ~3min cost 4',
  'end served',
  'end gave_up',
  'order -> served',
  'order abandon after 15min -> gave_up',
  'knob baristas 1..4 = 2',
  'show wait p90 at order',
  'show count end gave_up',
].join('\n')

const BROKEN = CAFE.replace('order -> served', 'order ->\n  served 60%\n  gave_up 30%')

const PANE = {
  plugin: 'house-lights',
  component: 'Pane',
  requestId: 'box-office-preview',
  props: { title: 'Process preview', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

function engine(on: any, files: Record<string, string> = {}) {
  on('command.register', (_: any, e: any) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000_000 }))
  on('fs.read', (_: any, e: any) => {
    const hit = Object.keys(files).find(k => String(e.path ?? e.args?.[0] ?? '').endsWith(k))
    return hit ? { value: files[hit] } : { deny: 'ENOENT ' + JSON.stringify(e) }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
}

test('the guard refuses a .sim write with errors and says why', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const out = await $.tool.call({ tool: 'Write', file_path: '/w/cafe.sim', content: BROKEN })
  const said = JSON.stringify(out)
  expect(said).toContain('not a valid .sim recipe')
  expect(said).toContain('add up to 90%')
})

test('the guard lets other files through untouched', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const out = await $.tool.call({ tool: 'Write', file_path: '/w/notes.md', content: 'order ->' })
  expect(JSON.stringify(out)).not.toContain('not a valid')
})

test('an edit that breaks the recipe is refused', async ($, on) => {
  engine(on, { '/w/cafe.sim': CAFE })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const out = await $.tool.call({ tool: 'Edit', file_path: '/w/cafe.sim', old_string: 'order -> served', new_string: 'order -> nowhere' })
  expect(JSON.stringify(out)).toContain('nowhere')
})

test('a valid write reaches the preview, as SVG on desktop and text in the terminal', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const out = await $.tool.call({ tool: 'Write', file_path: '/w/cafe.sim', content: CAFE })
  expect(JSON.stringify(out)).not.toContain('not a valid')

  const desk = await $.ui.mount({ ...PANE, surface: 'desktop' })
  const svg = await desk.find({ type: 'Svg' })
  expect(String((svg as any)?.props?.source ?? '')).toContain('<svg')
  await desk.unmount()

  const term = await $.ui.mount({ ...PANE, surface: 'terminal' })
  const line = await term.find({ type: 'Text', text: /arrive/ })
  expect(line?.text).toContain('order')
  await term.unmount()
})

test('/sim runs a recipe and prints each metric', async ($, on) => {
  engine(on, { 'cafe.sim': CAFE })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const out = await $.command.run({ command: 'sim', args: 'cafe.sim --seeds 2 --set baristas=3' } as any)
  expect(out.text).toContain('Corner café')
  expect(out.text).toContain('wait p90 at order')
  expect(out.text).toContain('baristas=3')
})

test('/sim reports errors instead of running', async ($, on) => {
  engine(on, { 'bad.sim': BROKEN })
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const out = await $.command.run({ command: 'sim', args: 'bad.sim' } as any)
  expect(out.text).toContain('has errors')
})
