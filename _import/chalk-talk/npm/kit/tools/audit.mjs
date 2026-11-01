// Before a push: no name that must not be in a public repository is in the files git tracks. The names themselves live
// outside every repository — ~/.config/skill-kit/audit.txt, one pattern per line (a regular expression, matched
// without case; # starts a comment) — since writing them in a public repository would publish them. Without that file
// it says so and passes. Part of the skills kit (chalk-talk/kit).
//
//   node audit.mjs [<repository>] [--skip <glob> …]   exit 1 when a name is found
import { execFileSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const AUDIT_LIST = join(homedir(), '.config/skill-kit/audit.txt')

/** The tracked text files that match a pattern of the list, as "file:line" — skipping the `skip` pathspecs (generated
 * and minified files). null when there is no list. */
export function audit(repo, skip = []) {
  if (!existsSync(AUDIT_LIST)) return null
  const patterns = readFileSync(AUDIT_LIST, 'utf8').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'))
  if (!patterns.length) return []
  try {
    const out = execFileSync('git', ['-C', repo, 'grep', '-I', '-n', '-i', '-E', patterns.join('|'), '--', '.', ...skip.map((s) => `:!${s}`)], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 })
    // only where, never what: the matched text is not printed
    return out.trim().split('\n').filter(Boolean).map((l) => l.split(':').slice(0, 2).join(':'))
  } catch (e) {
    if (e.status === 1) return []
    throw e
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2)
  const skip = args.flatMap((a, i) => (args[i - 1] === '--skip' ? [a] : []))
  const repo = resolve(args.find((a, i) => !a.startsWith('--') && args[i - 1] !== '--skip') ?? '.')
  const found = audit(repo, skip)
  if (found === null) console.log(`• audit     no list at ${AUDIT_LIST}: nothing checked`)
  else if (!found.length) console.log('✓ audit     no listed name in the tracked files')
  else {
    for (const f of found) console.log(`✗ audit     ${f}`)
    process.exit(1)
  }
}
