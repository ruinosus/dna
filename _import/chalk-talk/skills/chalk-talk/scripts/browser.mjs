// A Chrome, Chromium or Edge without a window: opens a built page in one of its modes (#review, #snapshots, #svg…) and
// reads back what the page wrote in <pre id="chalk-<mode>">. It talks to the browser over the DevTools protocol on a
// pipe (--remote-debugging-pipe) and waits for that <pre> itself: --dump-dom hangs on some machines, the pipe does not.
// The browsers are tried in order; one that does not start or does not answer in time gives way to the next.
// Used by build.mjs and by the repository's tools. Node only, no dependency.
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readdirSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

/** Playwright's own Chromium: the package's answer when it is installed here, else what it downloaded. */
function playwright() {
  const found = []
  const req = createRequire(join(process.cwd(), 'noop.js'))
  for (const name of ['playwright', 'playwright-core']) {
    try {
      const p = req(name).chromium.executablePath()
      if (p) found.push(p)
    } catch {}
  }
  const caches = [process.env.PLAYWRIGHT_BROWSERS_PATH, join(homedir(), '.cache/ms-playwright'), join(homedir(), 'Library/Caches/ms-playwright'), '/opt/pw-browsers'].filter(Boolean)
  const inside = ['chrome-linux64/chrome', 'chrome-linux/chrome', 'chrome-linux-arm64/chrome', 'chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing', 'chrome-mac/Chromium.app/Contents/MacOS/Chromium']
  for (const cache of caches) {
    let dirs = []
    try {
      dirs = readdirSync(cache).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse()
    } catch {}
    for (const d of dirs) for (const p of inside) found.push(join(cache, d, p))
  }
  return found
}

/** Every browser worth trying, in order: CHROME_PATH, PUPPETEER_EXECUTABLE_PATH, Playwright's Chromium, the usual places
 * on macOS and Windows, then `which` on Linux. Only paths that exist, each once. */
export function candidates() {
  const paths = [process.env.CHROME_PATH, process.env.PUPPETEER_EXECUTABLE_PATH, ...playwright(),
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe']
  if (process.platform !== 'win32') {
    for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge']) {
      try {
        paths.push(execFileSync('which', [name], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim())
      } catch {}
    }
  }
  return [...new Set(paths.filter((p) => p && existsSync(p)))]
}

/** The first browser there is, or null. */
export function browser() {
  return candidates()[0] ?? null
}

/** What the browser needs besides the usual: on Linux no sandbox as root (Chromium refuses to start otherwise) and no
 * /dev/shm (small in containers). */
export function launchFlags(platform = process.platform, uid = process.getuid?.()) {
  const flags = ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--allow-file-access-from-files',
    '--disable-background-networking', '--disable-component-update', '--disable-sync', '--remote-debugging-pipe']
  if (platform === 'linux') flags.push('--disable-dev-shm-usage')
  if (platform === 'linux' && uid === 0) flags.push('--no-sandbox')
  return flags
}

class BrowserFailed extends Error {}

// A wait that never keeps Node running by itself.
const pause = (ms) => new Promise((ok) => setTimeout(ok, ms).unref())

/** One browser, started with a profile of its own, spoken to over the pipe. */
async function start(exe) {
  const profile = mkdtempSync(join(tmpdir(), 'chalk-talk-'))
  const child = spawn(exe, [...launchFlags(), `--user-data-dir=${profile}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] })
  const waiting = new Map()
  let id = 0
  let dead
  // a failure of the whole browser rejects every call still waiting
  const fail = (why) => {
    dead ??= why
    for (const { reject } of waiting.values()) reject(new BrowserFailed(dead))
    waiting.clear()
  }
  child.on('error', (e) => fail(e.message))
  const exited = new Promise((ok) => child.once('exit', (code) => (fail(`it stopped (exit ${code})`), ok())))
  let buf = Buffer.alloc(0)
  child.stdio[4].on('data', (d) => {
    buf = Buffer.concat([buf, d])
    let at
    while ((at = buf.indexOf(0)) >= 0) {
      const msg = JSON.parse(buf.subarray(0, at).toString('utf8'))
      buf = buf.subarray(at + 1)
      const call = msg.id && waiting.get(msg.id)
      if (!call) continue
      waiting.delete(msg.id)
      if (msg.error) call.reject(new Error(msg.error.message))
      else call.ok(msg.result)
    }
  })
  child.stdio[3].on('error', (e) => fail(e.message))
  const send = (method, params = {}, sessionId) => new Promise((ok, reject) => {
    if (dead) return reject(new BrowserFailed(dead))
    const n = ++id
    waiting.set(n, { ok, reject })
    child.stdio[3].write(JSON.stringify({ id: n, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0')
  })
  const close = async () => {
    if (!dead) {
      send('Browser.close').catch(() => {})
      await Promise.race([exited, pause(3000)])
    }
    child.kill()
    await Promise.race([exited, pause(2000)])
    rmSync(profile, { recursive: true, force: true })
  }
  return { send, close }
}

/** Opens `file` at `#mode` (with `query`) in a tab of its own and returns what the page wrote, parsed — { error } when
 * the page could not be opened or wrote nothing in `ms`. */
async function open(b, file, mode, query, ms) {
  const until = Date.now() + ms
  let sessionId
  // Every call waits at most until the page's time is up: a page busy forever does not hold the build.
  const ask = (method, params, wait = until - Date.now()) => {
    let timer
    const late = new Promise((_, reject) => (timer = setTimeout(() => reject(new BrowserFailed(`no answer in ${Math.round(ms / 1000)} s`)), Math.max(0, wait))))
    return Promise.race([b.send(method, params, sessionId), late]).finally(() => clearTimeout(timer))
  }
  const { targetId } = await ask('Target.createTarget', { url: 'about:blank' })
  try {
    ;({ sessionId } = await ask('Target.attachToTarget', { targetId, flatten: true }))
    const nav = await ask('Page.navigate', { url: `${pathToFileURL(file).href}${query ? `?${query}` : ''}#${mode}` })
    if (nav.errorText) return { error: `the page did not open (${nav.errorText})` }
    while (Date.now() < until) {
      const r = await ask('Runtime.evaluate', { expression: `document.getElementById('chalk-${mode}')?.textContent ?? null`, returnByValue: true })
      const text = r.result?.value
      if (typeof text === 'string' && text) return JSON.parse(decodeURIComponent(text))
      await pause(50)
    }
    const at = await ask('Runtime.evaluate', { expression: 'location.href', returnByValue: true }, 1000).catch(() => undefined)
    throw new BrowserFailed(`no answer in ${Math.round(ms / 1000)} s${at?.result?.value ? ` at ${at.result.value}` : ''}`)
  } finally {
    sessionId = undefined
    b.send('Target.closeTarget', { targetId }).catch(() => {})
  }
}

/** Runs `jobs` ({ file, mode, query }) in one browser and returns their results in order, with the browser used —
 * `results` null when there is no browser at all. A browser that fails (does not start, stops, or a page gets no answer
 * in `timeout` seconds) gives way to the next one, which runs every job again; when none works, each result is
 * { error } naming what was tried. */
export async function runPages(jobs, { timeout = 20 } = {}) {
  const list = candidates()
  if (!list.length) return { results: null, tried: [] }
  const tried = []
  for (const exe of list) {
    let b
    try {
      b = await start(exe)
      const results = []
      for (const { file, mode, query = '' } of jobs) results.push(await open(b, file, mode, query, timeout * 1000))
      return { results, used: exe, tried }
    } catch (e) {
      tried.push(`${exe}: ${e instanceof BrowserFailed ? e.message : e.message.split('\n')[0]}`)
    } finally {
      await b?.close()
    }
  }
  const error = `no browser answered — ${tried.join('; ')}. Point CHROME_PATH at another one, or give it more time with --review-timeout`
  return { results: jobs.map(() => ({ error })), tried }
}

/** One page: what it wrote, parsed; null without a browser, { error } when it failed. */
export async function runPage(file, mode, query = '', opts) {
  const { results } = await runPages([{ file, mode, query }], opts)
  return results ? results[0] : null
}
