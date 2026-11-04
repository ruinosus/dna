// /agent-review: agent-review's comparison of a folder of cloned Copilot Studio agents, in a pane — the summary and «to look at» in
// its groups, a button each to open — by agent-review's own --check (nothing written). After it, an agent's .mcs.yml that
// Claude writes or edits in that folder runs the comparison again, and a toast says what came to look at or went away;
// it never refuses the edit, the YAML is Copilot Studio's.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import type { CastGroup } from '../../types'
import { pathOf, scriptOf } from '../recipes/run'

export const CAST_PANE = 'dna-cast'
const cast = atom({ plugin: 'dna', key: 'cast' } as const, null, { shape: 'cast-1' })
const openGroup = atom({ plugin: 'dna', key: 'castOpen' } as const, '' as string)

/** agent-review's --check output, read: the summary lines and «to look at» by group. */
export function parseCast(out: string): { summary: string[]; groups: CastGroup[] } {
  const summary: string[] = []
  const groups: CastGroup[] = []
  for (const line of out.split('\n')) {
    const g = /^▸ (.+) · (\d+)$/.exec(line)
    if (g) groups.push({ name: g[1]!, looks: [] })
    else if (/^! /.test(line) && groups.length) groups[groups.length - 1]!.looks.push(line.replace(/^! [^:]+: /, ''))
    else if (/^✓ /.test(line) && !groups.length) summary.push(line.slice(2))
  }
  return { summary, groups }
}

/** The folder to compare: the one given, the last one, or the working folder when agents are right under it. */
async function folderOf($: EngineInterface, given: string): Promise<string | undefined> {
  if (given) return pathOf($, given)
  const last = await read($, cast)
  if (last) return last.folder
  const entries = await $.fs.list('.').catch(() => [])
  for (const e of entries) if (e.kind === 'dir' && (await $.fs.exists(`${e.name}/agent.mcs.yml`))) return '.'
  return undefined
}

/** The team's profiles (kind AgentStandard, or format cast-list/profile-v1 from before) beside the agents: in the folder and in the one above it. */
async function profilesNear($: EngineInterface, folder: string): Promise<string[]> {
  const found: string[] = []
  const up = folder.replace(/\/+$/, '').split('/').slice(0, -1).join('/') || '.'
  for (const dir of folder === '.' ? ['.'] : [folder, up]) {
    for (const e of await $.fs.list(dir).catch(() => [])) {
      if (e.kind !== 'file' || !/\.cast\.ya?ml$/i.test(e.name)) continue
      const path = `${dir.replace(/\/+$/, '')}/${e.name}`
      const text = await $.fs.read(path).catch(() => '')
      if ((/^format:\s*cast-list\/profile-v1\b/m.test(String(text)) || /^kind:\s*AgentStandard\s*$/m.test(String(text))) && !found.includes(path)) found.push(path)
    }
  }
  return found
}

async function compare($: EngineInterface, folder: string, lang: 'en' | 'pt', profile?: string) {
  const run = await $.process.run(['node', scriptOf($, 'agent-review'), folder, '--check', '--lang', lang, ...(profile ? ['--profile', profile] : [])], { timeoutMs: 7000 })
  if (run.exitCode !== 0) return { error: (run.stderr || run.stdout).trim().split('\n').slice(0, 6).join('\n') }
  const real = (await $.fs.stat(folder, { resolve: true }).catch(() => undefined))?.realPath ?? folder
  return { doc: { folder: real, lang, ...(profile ? { profile } : {}), ...parseCast(run.stdout), at: await $.clock.now() } }
}

const count = (gs: CastGroup[]) => gs.reduce((n, g) => n + g.looks.length, 0)

// an agent edited in the compared folder: compare again, and say what changed
async function after($: EngineInterface, path: string) {
  const doc = await read($, cast)
  if (!doc || !/\.mcs\.ya?ml$/i.test(path) || !path.startsWith(`${doc.folder}/`)) return
  const r = await compare($, doc.folder, doc.lang, doc.profile)
  if ('error' in r) return
  const before = new Set(doc.groups.flatMap((g) => g.looks))
  const now = r.doc.groups.flatMap((g) => g.looks)
  const added = now.filter((l) => !before.has(l))
  const gone = count(doc.groups) - (now.length - added.length)
  await update($, cast, () => r.doc)
  const pt = doc.lang === 'pt'
  if (added.length) $.ui.toast(`agent-review: +${added.length} ${pt ? 'para olhar' : 'to look at'} — ${added[0]!.slice(0, 90)}`)
  else if (gone > 0) $.ui.toast(`agent-review: ${gone} ${pt ? 'a menos para olhar' : 'fewer to look at'}`)
}

export function castCommand(on: On) {
  on('command.run', { command: 'agent-review' }, async ($, e) => {
    const args = e.args.trim().split(/\s+/).filter(Boolean)
    const lang = args.includes('--lang') && args[args.indexOf('--lang') + 1] === 'pt' ? 'pt' : 'en'
    const flag = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined)
    const given = args.filter((a, i) => !a.startsWith('--') && args[i - 1] !== '--lang' && args[i - 1] !== '--profile')[0] ?? ''
    const folder = await folderOf($, given)
    if (!folder) return { text: `name a folder of cloned agents, for example /agent-review agents/ --profile team.cast.yaml --lang pt` }
    if (!(await $.fs.exists(folder))) return { text: `could not read ${given}: no such folder` }
    // the team's profile: the one given, or the only one beside the agents (said so); two or more, the person chooses
    let profile: string | undefined
    let note = ''
    const typed = flag('--profile')
    if (typed) {
      profile = await pathOf($, typed)
      if (!(await $.fs.exists(profile))) return { text: `could not read ${typed}: no such file` }
    } else if (!given && (await read($, cast))?.profile) {
      profile = (await read($, cast))!.profile
    } else {
      const near = await profilesNear($, folder)
      if (near.length === 1) {
        profile = near[0]
        note = lang === 'pt' ? `perfil: ${profile} (o único ao lado dos agentes)` : `profile: ${profile} (the only one beside the agents)`
      } else if (near.length > 1) {
        return { text: `${lang === 'pt' ? 'há mais de um perfil; escolha com --profile' : 'there is more than one profile; choose with --profile'}:\n${near.map((p) => `  ${p}`).join('\n')}` }
      }
    }
    const r = await compare($, folder, lang, profile).catch((err) => ({ error: String(err) }))
    if ('error' in r) return { text: `agent-review could not compare ${folder}:\n${r.error}` }
    await update($, cast, () => r.doc)
    await update($, openGroup, () => '')
    await $.ui.open({ id: CAST_PANE, title: 'agent-review' })
    const text = [...(note ? [note] : []), ...r.doc.summary, ...r.doc.groups.map((g) => `▸ ${g.name} · ${g.looks.length}`)].join('\n')
    return { text, context: [`The person ran /agent-review on ${folder}. agent-review says:\n${text}`] }
  })

  on('ui.render', { component: 'Pane', requestId: CAST_PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const doc = await read($, cast)
    const opened = await read($, openGroup)
    if (!doc) return <Text dimColor>Run /agent-review with a folder of cloned agents.</Text>
    return (
      <Box flexDirection="column" gap={1}>
        <Text bold>{doc.folder.split('/').pop()}</Text>
        {doc.summary.map((s) => <Text dimColor>{s}</Text>)}
        {doc.groups.length ? doc.groups.map((g) => (
          <Box flexDirection="column">
            <Button key={`g:${g.name}`} label={`${opened === g.name ? '▾' : '▸'} ${g.name} · ${g.looks.length}`} onPress={() => update($, openGroup, (o) => (o === g.name ? '' : g.name))} />
            {opened === g.name ? g.looks.slice(0, 14).map((l) => <Text>{`  ! ${l}`}</Text>) : []}
          </Box>
        )) : <Text>{doc.lang === 'pt' ? '✓ nada para olhar' : '✓ nothing to look at'}</Text>}
      </Box>
    )
  })

  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran && ran.deny === undefined && ran.isError !== true) await after($, e.file_path).catch(() => undefined)
    return ran
  })
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran && ran.deny === undefined && ran.isError !== true) await after($, e.file_path).catch(() => undefined)
    return ran
  })
}
