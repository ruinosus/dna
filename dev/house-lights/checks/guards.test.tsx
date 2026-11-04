// The mod's guards in Claude Code's own harness: the recipes' guard (each skill's check, run by node on a copy) and the
// names' guard (the private list, in a repository that runs the audit). The engine beneath is a fake: files in memory,
// git and node answered here — the skills' checks themselves are tested by each skill's own battery.
import { expect, test } from 'claude-code/testing'

const ROOT = '/repo'
type Fake = { files?: Record<string, string>; audited?: boolean; node?: 'ok' | 'missing'; runs?: string[][] }

function engine(on: any, f: Fake = {}) {
  const files: Record<string, string> = { ...(f.files ?? {}) }
  if (f.audited !== false) files[`${ROOT}/package.json`] = JSON.stringify({ scripts: { audit: 'node kit/tools/audit.mjs .' } })
  on('command.register', (_: any, e: any) => ({ value: { command: e.name } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('clock.now', () => ({ value: 1_000_000 }))
  on('env.get', (_: any, e: any) => ({ value: ({ HOME: '/home/me', TMPDIR: '/tmp/' } as Record<string, string>)[e.name] }))
  on('fs.read', (_: any, e: any) => (e.path in files ? { value: files[e.path] } : { deny: `ENOENT ${e.path}` }))
  on('fs.write', (_: any, e: any) => {
    files[e.path] = e.text
    return { value: undefined }
  })
  on('fs.exists', (_: any, e: any) => ({ value: e.path === ROOT || e.path.startsWith(`${ROOT}/`) || e.path === '/elsewhere' || e.path in files }))
  on('process.run', (_: any, e: any) => {
    const argv: string[] = [...e.argv]
    f.runs?.push(argv)
    if (argv[0] === 'git') return { value: argv[2]?.startsWith(ROOT) || argv[2] === '.' ? { exitCode: 0, stdout: `${ROOT}\n`, stderr: '' } : { exitCode: 128, stdout: '', stderr: 'not a git repository' } }
    if (argv[0] === 'rm') return { value: { exitCode: 0, stdout: '', stderr: '' } }
    if (argv[0] === 'node') {
      if (f.node === 'missing') return { deny: 'spawn node ENOENT' }
      const text = files[argv[2]!] ?? ''
      const name = argv[2]!.split('/').pop()
      const dir = argv[2]!.slice(0, argv[2]!.lastIndexOf('/'))
      return { value: text.includes('BROKEN') ? { exitCode: 1, stdout: '', stderr: `✗ ${name}:3: the gate «x» is after a stage that is not there\n✗ ${dir}/${name}: one more\n` } : { exitCode: 0, stdout: '✓ ok', stderr: '' } }
    }
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
}
const start = ($: any) => $.session.start({ cwd: ROOT, surface: 'terminal', isInteractive: true })
const denied = (out: unknown) => JSON.stringify(out)

// the recipes
test('a way of working that breaks its format is refused with its check\'s messages', async ($, on) => {
  const runs: string[][] = []
  engine(on, { runs })
  await start($)
  const out = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/team.way.yaml`, content: 'stages: BROKEN' })
  expect(denied(out)).toContain('is not a valid way of working yet')
  expect(denied(out)).toContain('team.way.yaml:3: the gate')
  expect(denied(out)).not.toContain('/tmp/house-lights-guard') // the temporary folder is never shown
  expect(runs.some((r) => r[0] === 'node' && r[1]!.endsWith('/skills/gates-and-handoffs/scripts/build.mjs') && r.includes('--check'))).toBe(true)
  expect(runs.some((r) => r[0] === 'rm')).toBe(true)
})

test('a valid recipe of each skill goes through', async ($, on) => {
  engine(on)
  await start($)
  for (const file of ['team.way.yaml', 'returns.blueprint.yaml', 'checkout.drill.yaml', 'coin-jar.chalk']) {
    const out = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/${file}`, content: 'fine' })
    expect(denied(out)).not.toContain('is not a valid')
  }
})

test('a .json is checked only when it is a chalk-talk recipe', async ($, on) => {
  const runs: string[][] = []
  engine(on, { runs })
  await start($)
  const plain = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/package.json`, content: '{"name": "BROKEN"}' })
  expect(denied(plain)).not.toContain('is not a valid')
  expect(runs.some((r) => r[0] === 'node')).toBe(false)
  const lesson = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/juros.json`, content: '{"title": "Juros", "steps": [{"type": "BROKEN"}]}' })
  expect(denied(lesson)).toContain('is not a valid chalk-talk lesson yet')
})

test('an edit that breaks a blueprint is refused', async ($, on) => {
  engine(on, { files: { [`${ROOT}/returns.blueprint.yaml`]: 'name: Returns\nmoments: []\n' } })
  await start($)
  const out = await $.tool.call({ tool: 'Edit', file_path: `${ROOT}/returns.blueprint.yaml`, old_string: 'moments: []', new_string: 'moments: BROKEN' })
  expect(denied(out)).toContain('is not a valid service blueprint yet')
})

test('when the check cannot run, the write goes through', async ($, on) => {
  engine(on, { node: 'missing' })
  await start($)
  const out = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/team.way.yaml`, content: 'stages: BROKEN' })
  expect(denied(out)).not.toContain('is not a valid')
})

// the names
const LIST = { '/home/me/.config/skill-kit/audit.txt': '# names that must not be published\n\\bcoi\\b\nacme corp\n' }

test('in a repository that runs the audit, a name of the list is refused, saying which pattern and line', async ($, on) => {
  engine(on, { files: LIST })
  await start($)
  const out = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/docs/notes.md`, content: 'Line one\nO agente do COI responde\nend' })
  const text = denied(out)
  expect(text).toContain('would put a name of your private list')
  expect(text).toContain('«\\\\bcoi\\\\b», line 2')
  expect(text).not.toContain('O agente do COI responde') // the text itself is never repeated
})

test('the names guard does nothing with no list, outside the repository, or where the audit does not run', async ($, on) => {
  engine(on, { files: LIST, audited: false })
  await start($)
  const unaudited = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/notes.md`, content: 'COI' })
  expect(denied(unaudited)).not.toContain('private list')
  const outside = await $.tool.call({ tool: 'Write', file_path: '/elsewhere/notes.md', content: 'COI' })
  expect(denied(outside)).not.toContain('private list')
})

test('with no list, nothing is checked', async ($, on) => {
  engine(on)
  await start($)
  const out = await $.tool.call({ tool: 'Write', file_path: `${ROOT}/notes.md`, content: 'COI' })
  expect(denied(out)).not.toContain('private list')
})

test('an edit is checked on what it adds, so removing a name is never blocked', async ($, on) => {
  engine(on, { files: { ...LIST, [`${ROOT}/notes.md`]: 'about COI here' } })
  await start($)
  const removing = await $.tool.call({ tool: 'Edit', file_path: `${ROOT}/notes.md`, old_string: 'about COI here', new_string: 'about it here' })
  expect(denied(removing)).not.toContain('private list')
  const adding = await $.tool.call({ tool: 'Edit', file_path: `${ROOT}/notes.md`, old_string: 'about COI here', new_string: 'Acme Corp and COI' })
  expect(denied(adding)).toContain('«acme corp», line 1')
})

test('/names says the list and whether this repository is watched', async ($, on) => {
  engine(on, { files: LIST })
  await start($)
  const r = await $.command.run({ command: 'names', args: '' } as any)
  expect(JSON.stringify(r)).toContain('2 patterns')
  expect(JSON.stringify(r)).toContain('runs the audit')
})
