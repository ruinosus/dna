// What the guards share: the plugin's name in their messages, and an Edit applied in memory to the file as it is.
import type { EngineInterface } from 'claude-code'

export const PLUGIN = 'house-lights'

/** The file's text after an Edit, as the tool would leave it; undefined when it cannot be told (no file, no match). */
export async function afterEdit($: EngineInterface, e: { file_path: string; old_string: string; new_string: string; replace_all?: boolean }): Promise<string | undefined> {
  const before = await $.fs.read(e.file_path).catch(() => undefined)
  if (typeof before !== 'string') return undefined
  const at = before.indexOf(e.old_string)
  if (at < 0) return undefined
  return e.replace_all ? before.split(e.old_string).join(e.new_string) : before.slice(0, at) + e.new_string + before.slice(at + e.old_string.length)
}
