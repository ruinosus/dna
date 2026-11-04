// Publishes the site (docs/, made by npm run site) to the gh-pages branch, which GitHub Pages serves. The branch holds
// the site and nothing else, as one commit replaced on every publish, so main — what Claude Code and the Copilot clone
// to install the plugin — never carries the pictures and pages.
//
//   node dev/house-lights/tools/pages.mjs [--remote github]   (npm run pages)
import { execFileSync } from 'node:child_process'
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const args = process.argv.slice(2)
const remote = args.includes('--remote') ? args[args.indexOf('--remote') + 1] : 'github'
const docs = join(repo, 'docs')
if (!existsSync(join(docs, 'index.html')) || !existsSync(join(docs, '.nojekyll'))) {
  console.error('✗ docs/ is not built: run npm run site first')
  process.exit(1)
}
const version = JSON.parse(readFileSync(join(repo, '.claude-plugin/plugin.json'), 'utf8')).version
const main = execFileSync('git', ['-C', repo, 'rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim()
const git = (cwd, ...a) => execFileSync('git', ['-C', cwd, ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] })

// a fresh repository with only the site, pushed over the branch
const work = mkdtempSync(join(tmpdir(), 'house-lights-pages-'))
try {
  git(work, 'init', '-q', '-b', 'gh-pages')
  cpSync(docs, work, { recursive: true })
  git(work, 'add', '-A')
  git(work, '-c', `user.name=${git(repo, 'config', 'user.name').trim()}`, '-c', `user.email=${git(repo, 'config', 'user.email').trim()}`, 'commit', '-q', '-m', `site: house-lights ${version} (main ${main})`)
  const url = git(repo, 'remote', 'get-url', remote).trim()
  git(work, 'push', '-q', '--force', url, 'gh-pages')
  const files = git(work, 'ls-files').trim().split('\n').length
  console.log(`✓ gh-pages: the site of house-lights ${version} (main ${main}), ${files} files, pushed to ${remote}`)
} finally {
  rmSync(work, { recursive: true, force: true })
}
