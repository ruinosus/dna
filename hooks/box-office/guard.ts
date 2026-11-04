// Feature 1: checks every .sim file Claude writes or edits, and refuses the write
// with the validator's messages when the recipe has errors, so Claude fixes it first.
import { atom, update } from 'claude-code'
import type { EngineInterface, On } from 'claude-code'

import { PANE, PLUGIN, check, isSim } from './core'

const last = atom({ plugin: 'house-lights', key: 'last' } as const, null, { shape: 'last-1' })

let openedPreview = false

async function judge($: EngineInterface, path: string, src: string, go: () => Promise<any>) {
  const c = check(src)
  if (!c.ok) {
    const list = c.errors.map(d => `- ${d.text}`).join('\n')
    const more = c.warnings.length ? '\nWarnings:\n' + c.warnings.map(d => `- ${d.text}`).join('\n') : ''
    return {
      deny: `${PLUGIN}: ${path} is not a valid .sim recipe yet (${c.errors.length} error${c.errors.length === 1 ? '' : 's'}). Fix these and write it again:\n${list}${more}`,
    }
  }
  const ran = await go()
  if (ran && ran.deny === undefined && ran.isError !== true) {
    const at = await $.clock.now()
    await update($, last, () => ({ path, src, at }))
    if (c.warnings.length) $.ui.toast(`${PLUGIN}: ${c.warnings.length} warning${c.warnings.length === 1 ? '' : 's'} in ${path.split('/').pop()}`)
    if (!openedPreview) {
      openedPreview = true
      void $.ui.open({ id: PANE, title: 'Process preview' })
    }
  }
  return ran
}

export function guard(on: On) {
  on('tool.call', { tool: 'Write' }, async ($, e, next) => {
    if (!isSim(e.file_path)) return next(e)
    return judge($, e.file_path, e.content, () => next(e))
  }).catch(($, e, next) => next(e))

  on('tool.call', { tool: 'Edit' }, async ($, e, next) => {
    if (!isSim(e.file_path)) return next(e)
    const before = await $.fs.read(e.file_path).catch(() => undefined)
    if (typeof before !== 'string') return next(e)
    const at = before.indexOf(e.old_string)
    if (at < 0) return next(e)
    const after = e.replace_all
      ? before.split(e.old_string).join(e.new_string)
      : before.slice(0, at) + e.new_string + before.slice(at + e.old_string.length)
    return judge($, e.file_path, after, () => next(e))
  }).catch(($, e, next) => next(e))
}
