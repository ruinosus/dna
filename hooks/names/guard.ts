// The names' guard: in a repository that runs the names audit before it publishes (its package.json has an `audit`
// script calling audit.mjs, as house-lights does), a Write or Edit whose new text has a name of the person's own list
// (~/.config/skill-kit/audit.txt, the one `npm run audit` reads) is refused, saying which pattern and on which line of
// the new text — never repeating the text. With no list, or anywhere else, it does nothing. /names says what it watches.
// It fails open, in its own code: if the list or git cannot be read, the write goes through.
import type { EngineInterface, On } from 'claude-code'

import { PLUGIN } from '../recipes/text'

/** The list's patterns, as the audit reads them: one a line, `#` a comment, no case. */
export function patternsOf(list: string): { source: string; re: RegExp }[] {
  return list.split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#')).flatMap((source) => {
    try {
      return [{ source, re: new RegExp(source, 'i') }]
    } catch {
      return [] // a pattern JavaScript cannot read: the audit still has it
    }
  })
}

/** Each pattern found in `text`, with the lines of the text it is on. */
export function namesIn(text: string, patterns: { source: string; re: RegExp }[]): { source: string; lines: number[] }[] {
  const lines = text.split('\n')
  return patterns.flatMap((p) => {
    const at = lines.flatMap((l, i) => (p.re.test(l) ? [i + 1] : []))
    return at.length ? [{ source: p.source, lines: at }] : []
  })
}

const LIST = '.config/skill-kit/audit.txt'
async function listOf($: EngineInterface): Promise<{ path: string; patterns: { source: string; re: RegExp }[] } | undefined> {
  const home = await $.env.get('HOME')
  if (!home) return undefined
  const path = `${home}/${LIST}`
  const text = await $.fs.read(path).catch(() => undefined)
  return typeof text === 'string' ? { path, patterns: patternsOf(text) } : undefined
}

// the repository of a folder, and whether it runs the audit: asked of git once per folder
const repos = new Map<string, string | null>()
async function watchedRepo($: EngineInterface, file: string): Promise<string | null> {
  let dir = file.includes('/') ? file.slice(0, file.lastIndexOf('/')) || '/' : '.'
  while (dir !== '/' && dir !== '.' && !(await $.fs.exists(dir))) dir = dir.slice(0, dir.lastIndexOf('/')) || '/'
  if (repos.has(dir)) return repos.get(dir)!
  let root: string | null = null
  const top = await $.process.run(['git', '-C', dir, 'rev-parse', '--show-toplevel']).catch(() => undefined)
  if (top && top.exitCode === 0) {
    const pkg = await $.fs.read(`${top.stdout.trim()}/package.json`).catch(() => undefined)
    try {
      if (typeof pkg === 'string' && /audit\.mjs/.test(JSON.parse(pkg).scripts?.audit ?? '')) root = top.stdout.trim()
    } catch {}
  }
  repos.set(dir, root)
  return root
}

async function judge($: EngineInterface, file: string, text: string, go: () => Promise<any>) {
  // never throws: what cannot be read lets the write through (a hook that throws would stop this plugin's other guards)
  const verdict = await (async () => {
    const list = await listOf($)
    if (!list || !list.patterns.length) return undefined
    const root = await watchedRepo($, file)
    if (!root) return undefined
    const found = namesIn(text, list.patterns)
    return found.length ? { root, found } : undefined
  })().catch(() => undefined)
  if (!verdict) return go()
  const { root, found } = verdict
  const where = found.map((f) => `- the pattern «${f.source}», line${f.lines.length === 1 ? '' : 's'} ${f.lines.slice(0, 8).join(', ')} of the new text`).join('\n')
  return {
    deny: `${PLUGIN}: ${file} would put a name of your private list (${LIST}) in ${root.split('/').pop()}, which is published. Write it without:\n${where}\nUse a made-up name instead (as the examples do), or keep the text out of this repository.`,
  }
}

export function namesGuard(on: On) {
  on('tool.call', { tool: 'Write' }, async ($, e, next) => judge($, e.file_path, e.content, () => next(e)))
  // an Edit: only what it adds is checked, so a name already there (and being removed) does not block the edit
  on('tool.call', { tool: 'Edit' }, async ($, e, next) => judge($, e.file_path, e.new_string, () => next(e)))
}

/** /names: the list, how many patterns, and whether the working folder's repository is watched. */
export function namesCommand(on: On) {
  on('command.run', { command: 'names' }, async ($) => {
    const list = await listOf($)
    if (!list) return { text: `${PLUGIN}: no list at ~/${LIST}: the names guard does nothing.` }
    const root = await watchedRepo($, './x')
    return {
      text: `${PLUGIN}: ${list.patterns.length} pattern${list.patterns.length === 1 ? '' : 's'} in ~/${LIST}. ${root ? `This repository (${root.split('/').pop()}) runs the audit: a write with one of them is refused.` : 'This folder is not in a repository that runs the audit: nothing is checked here.'}`,
    }
  })
}
