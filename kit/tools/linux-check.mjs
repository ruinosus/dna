// A skill's build as in a cloud sandbox: Linux, as root, with Playwright's Chromium and no other browser. Each case is
// a file to build and the exit code it must give — never «not checked» from a browser that did not answer. Needs
// Docker; downloads node:22-slim and Playwright's Chromium (~150 MB). Part of the skills kit (chalk-talk/kit).
import { execFileSync } from 'node:child_process'
import { basename } from 'node:path'

/** `skill`: the skill's folder; `cases`: [{ file, args?, exit }]. Returns true when every case gave its exit code. */
export function linuxCheck(skill, cases) {
  const name = `skill-linux-check-${process.pid}`
  const sh = (cmd) => execFileSync('docker', ['exec', name, 'bash', '-c', cmd], { encoding: 'utf8' })
  try {
    execFileSync('docker', ['run', '-d', '--name', name, 'node:22-slim', 'sleep', '1800'], { stdio: 'ignore' })
    sh('mkdir -p /work/skill /work/files')
    for (const dir of ['scripts', 'assets']) execFileSync('docker', ['cp', `${skill}/${dir}`, `${name}:/work/skill/`])
    for (const c of cases) execFileSync('docker', ['cp', c.file, `${name}:/work/files/`])
    sh('cd /work && npm init -y >/dev/null && npm i playwright >/dev/null 2>&1 && npx playwright install --with-deps chromium >/dev/null 2>&1')
    let ok = true
    for (const c of cases) {
      const args = (c.args ?? []).map((a) => `'${a}'`).join(' ')
      const out = sh(`cd /work && node skill/scripts/build.mjs files/${basename(c.file)} ${args}; echo "exit=$?"`)
      const exit = Number(out.match(/exit=(\d+)\s*$/)?.[1])
      const unchecked = /not checked|could not run|no Chrome/.test(out)
      const good = exit === c.exit && !unchecked
      ok &&= good
      console.log(`${good ? '✓' : '✗'} linux as root: ${basename(c.file)} exit ${exit} (expected ${c.exit})${unchecked ? ', the review did not run' : ''}`)
    }
    return ok
  } finally {
    execFileSync('docker', ['rm', '-f', name], { stdio: 'ignore' })
  }
}
