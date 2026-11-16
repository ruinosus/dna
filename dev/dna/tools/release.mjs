// The release rules, with no dependency (run by check.mjs and by CI on every pull request):
// - Claude Code and claude.ai update a marketplace plugin only when the version in .claude-plugin/plugin.json changes.
//   A change to what the plugin ships (skills/, hooks/, kit/, types/, .claude-plugin/) since main must raise it.
// - plugin.json, npm/dna/package.json and the CHANGELOG's latest version say the same version.
// - dna alone, nothing nested: a plugin with source "./" that holds another .claude-plugin/plugin.json is skipped by claude.ai.
// main is the remote's that points at ruinosus/dna (origin in CI); DNA_BASE=<ref> picks another.
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const git = (...args) => execFileSync('git', ['-C', repo, ...args], { encoding: 'utf8' }).trim()
const SHIPPED = ['skills/', 'hooks/', 'kit/', 'types/', '.claude-plugin/']
let failed = 0
const expect = (ok, what) => {
  console.log(`${ok ? '✓' : '✗'} ${what}`)
  if (!ok) failed++
}
const json = (text) => JSON.parse(text)
const version = json(readFileSync(join(repo, '.claude-plugin/plugin.json'), 'utf8')).version
const newer = (a, b) => {
  const [x, y] = [a, b].map((v) => v.split('.').map(Number))
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] > y[i]
  return false
}

// one version
const npm = json(readFileSync(join(repo, 'npm/dna/package.json'), 'utf8')).version
const logged = readFileSync(join(repo, 'CHANGELOG.md'), 'utf8').match(/^## (\d+\.\d+\.\d+)/m)?.[1]
expect(npm === version && logged === version, `one version: plugin.json ${version}, npm/dna ${npm}, CHANGELOG ${logged ?? 'none'}`)

// a change to what the plugin ships raises the version
const remote = git('remote', '-v').split('\n').find((l) => /ruinosus\/dna(\.git)?\s/.test(l))?.split(/\s/)[0]
const base = process.env.DNA_BASE ?? (remote && `${remote}/main`)
let mainVersion
try {
  mainVersion = base && json(git('show', `${base}:.claude-plugin/plugin.json`)).version
} catch {}
if (!mainVersion) console.log(`• no ${base ?? 'remote of ruinosus/dna'} here (git fetch it): the version bump was not checked`)
else {
  const changed = git('diff', '--name-only', git('merge-base', base, 'HEAD')).split('\n').filter((f) => SHIPPED.some((p) => f.startsWith(p)))
  expect(!changed.length || newer(version, mainVersion),
    changed.length
      ? `what the plugin ships changed (${changed.length} files, e.g. ${changed.slice(0, 3).join(', ')}): the version goes above main's ${mainVersion} (it is ${version}) — otherwise nobody gets the change`
      : `nothing the plugin ships changed since ${base} (${mainVersion})`)
}

// dna alone, nothing nested
const nested = git('ls-files').split('\n').filter((f) => f.endsWith('.claude-plugin/plugin.json') && f !== '.claude-plugin/plugin.json')
expect(!nested.length, `dna alone, nothing nested${nested.length ? ` — not: ${nested.join(', ')}` : ''}`)

if (failed) process.exit(1)
