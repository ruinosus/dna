// A Chrome, Chromium or Edge without a window: opens a built page in one of its modes (#review, #snapshot) and reads
// back what the page wrote in <pre id="chalk-<mode>">. Used by build.mjs and by the repository's tools.
import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

/** The browser to use: CHROME_PATH, then the usual places on macOS and Windows, then `which` on Linux. */
export function browser() {
  const env = process.env.CHROME_PATH
  if (env && existsSync(env)) return env
  const mac = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ]
  const win = ['C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe']
  for (const p of [...mac, ...win]) if (existsSync(p)) return p
  for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge']) {
    try {
      const p = execFileSync('which', [name], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
      if (p) return p
    } catch {}
  }
  return null
}

/** Opens `file` at `#mode` and returns what the page wrote, parsed; null without a browser, { error } when it failed. */
export function runPage(file, mode) {
  const exe = browser()
  if (!exe) return null
  const profile = mkdtempSync(join(tmpdir(), 'chalk-talk-'))
  try {
    const dom = execFileSync(exe, [
      '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--allow-file-access-from-files',
      `--user-data-dir=${profile}`, '--virtual-time-budget=30000', '--dump-dom', `${pathToFileURL(file).href}#${mode}`,
    ], { encoding: 'utf8', timeout: 90000, stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 64 * 1024 * 1024 })
    const found = dom.match(new RegExp(`<pre id="chalk-${mode}">([^<]*)</pre>`))
    return found ? JSON.parse(decodeURIComponent(found[1])) : { error: `the page did not finish the ${mode}` }
  } catch (e) {
    return { error: e.message.split('\n')[0] }
  } finally {
    rmSync(profile, { recursive: true, force: true })
  }
}
