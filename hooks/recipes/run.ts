// Running a skill's own script from the mod, which has no Node: `node skills/<skill>/scripts/build.mjs …` on the host,
// on a copy of a text in a folder of its own (removed after), so a recipe is checked before it is written.
import type { EngineInterface } from 'claude-code'

export function scriptOf($: EngineInterface, skill: string): string {
  return `${$.plugin.root}/skills/${skill}/scripts/build.mjs`
}
const base = (p: string) => p.split('/').pop() || 'recipe'

export type Ran = { exitCode: number; stdout: string; stderr: string; dir: string }

/** Writes `text` as a file of `path`'s name in a fresh folder, runs the skill's script with `args(file, dir)`, removes
 * the folder, and gives back what it printed (the folder's path taken out by the caller). */
export async function runOnCopy($: EngineInterface, skill: string, path: string, text: string, args: (file: string, dir: string) => string[], timeoutMs = 7000): Promise<Ran> {
  const tmp = ((await $.env.get('TMPDIR')) ?? '/tmp').replace(/\/$/, '')
  const dir = `${tmp}/house-lights-guard-${Math.round(await $.clock.now())}-${Math.random().toString(36).slice(2, 8)}`
  const file = `${dir}/${base(path)}`
  try {
    await $.fs.write(file, text)
    const run = await $.process.run(['node', scriptOf($, skill), ...args(file, dir)], { timeoutMs })
    return { exitCode: run.exitCode, stdout: run.stdout, stderr: run.stderr, dir }
  } finally {
    await $.process.run(['rm', '-rf', dir]).catch(() => undefined)
  }
}

/** The ✗ lines (and the indented «write it like» under them) a check printed, with the copy's folder taken out. */
export function problemLines(r: Ran, path: string): string[] {
  const lines = `${r.stderr}\n${r.stdout}`.split('\n').map((l) => l.trimEnd()).filter((l) => /^✗|^\s+\S/.test(l) && !/^✗ \d+ check/.test(l))
  return lines.length ? lines.map((l) => l.split(r.dir + '/').join('')) : [`${base(path)}: the check refused it (exit 1)`]
}
