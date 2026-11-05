// node scripts/wws.mjs — the catalog of Workday Web Services (SOAP) on this machine: index the Operation Directory text
// and the WSDLs a person has, then search by intent, trace a use case, show an operation, write its SOAP envelope or the
// Copilot Studio «Execute SOAP operation» spec. It calls no tenant and asks for no credential; only `fetch` goes to the
// network (Workday Community), and only when asked.
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { COMMUNITY_DIRECTORY_URL, COMMUNITY_WSDL_URL, DEFAULT_VERSION, HR_SERVICES } from './config.mjs'
import { defaultIndexDir, Index } from './index.mjs'
import { LookupError } from './render.mjs'
import { parseWsdl } from './schema.mjs'
import { copilotActionSpec, essTemplate, getOperation, makeEnvelope, traceUseCase } from './workflows.mjs'

const USAGE = `usage: node scripts/wws.mjs <command> [options]   (--json on any command; --index <folder> for another index)
  ingest <files or folders>…   the Operation Directory text (.txt) and the WSDL/XSD files you have
  status                       what is indexed
  search "<intent>"            [--scope hr|all] [--limit N]
  trace "<use case>"           the chain: who the user is, the operation, the approver's inbox, the business process
  show <Operation>             [--path A/B] [--depth N] [--response] [--service S] [--version V]
  envelope <Operation>         [--include A/B/C]… [--all] [--wsse] [--body-only]
  copilot <Operation>          [--include A/B/C]… [--envelope]   the Copilot Studio Execute SOAP operation spec
                               (requestBody is the element alone; --envelope for the whole SOAP envelope)
  ess <Operation>              [--include A/B/C]…   a template of Microsoft's Employee Self-Service Workday pack
  fetch [--services hr|all|A,B] [--version ${DEFAULT_VERSION}]   downloads the Operation Directory and the WSDLs from
                               Workday Community and indexes them (the only command that uses the network)`

const VALUED = new Set(['--index', '--scope', '--limit', '--path', '--depth', '--service', '--version', '--include', '--services'])
const FLAGS = new Set(['--json', '--response', '--all', '--wsse', '--body-only', '--envelope'])

function parseArgs(argv) {
  const opts = { include: [] }
  const rest = []
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (VALUED.has(a)) {
      const v = argv[++i]
      if (v === undefined) throw new LookupError(`${a} needs a value`)
      if (a === '--include') opts.include.push(v)
      else opts[a.slice(2)] = v
    } else if (FLAGS.has(a)) opts[a.slice(2)] = true
    else if (a.startsWith('--')) throw new LookupError(`${a} is not an option`)
    else rest.push(a)
  }
  return { cmd: rest[0], args: rest.slice(1), opts }
}

const say = (s) => process.stdout.write(s + '\n')
const json = (v) => say(JSON.stringify(v, null, 2))

/** The WSDL, .txt and .html files under the paths (a folder is walked; .xsd files are read through their WSDL). */
function filesOf(paths) {
  const out = []
  const walk = (p) => {
    if (statSync(p).isDirectory()) for (const f of readdirSync(p).sort()) walk(join(p, f))
    else if (/\.(wsdl|txt|html?)$/i.test(p)) out.push(p)
  }
  for (const p of paths) {
    if (!existsSync(p)) throw new LookupError(`${p} is not there`)
    if (statSync(p).isDirectory()) walk(p)
    else out.push(p)
  }
  return out
}

function ingest(ix, paths, opts) {
  const lines = []
  let ops = 0
  let schemas = 0
  // the directory first: its descriptions win over a WSDL's, as in the Python port
  const files = filesOf(paths.map((p) => resolve(p)))
  const isDirectory = (f) => /\.(txt|html?)$/i.test(f)
  for (const f of [...files.filter(isDirectory), ...files.filter((x) => !isDirectory(x))]) {
    try {
      if (isDirectory(f)) {
        const n = ix.ingestDirectory(readFileSync(f, 'utf8'), opts.version)
        lines.push(`✓ directory  ${n} operations  (${f})`)
        ops += n
      } else {
        const ss = parseWsdl(f, { service: opts.service, version: opts.version })
        const n = ix.ingestSchema(ss, f)
        lines.push(`✓ ${ss.service} ${ss.version}: ${n} operations, ${Object.keys(ss.complex).length} complex types  (${f})`)
        schemas += n
      }
    } catch (e) {
      lines.push(`✗ ${f}: ${e.message}`)
    }
  }
  return { lines, ops, schemas }
}

async function fetchServices(ix, opts) {
  const version = opts.version ?? DEFAULT_VERSION
  const got = []
  const get = (url) => fetch(url, { headers: { 'User-Agent': 'dna-workday-integration (developer catalog)' } })
  // the Operation Directory first (the current production version's): every operation, its services, what is deprecated
  const dir = await get(COMMUNITY_DIRECTORY_URL)
  if (dir.ok) {
    mkdirSync(join(ix.dir, 'wsdl'), { recursive: true })
    const file = join(ix.dir, 'wsdl', 'operation-directory.html')
    const html = Buffer.from(await dir.arrayBuffer())
    writeFileSync(file, html)
    // indexed now, so --services all knows every service
    say(`↓ ${file}: ${ix.ingestDirectory(html.toString('utf8'))} operations`)
  } else say(`✗ the Operation Directory: ${COMMUNITY_DIRECTORY_URL} answered ${dir.status}`)
  const known = [...new Set(ix.data.operations.map((r) => r.service))].sort()
  const services = opts.services === 'all' ? known : !opts.services || opts.services === 'hr' ? [...HR_SERVICES] : opts.services.split(',').map((s) => s.trim()).filter(Boolean)
  for (const service of services) {
    const folder = join(ix.dir, 'wsdl', service, version)
    mkdirSync(folder, { recursive: true })
    for (const ext of ['wsdl', 'xsd']) {
      const url = COMMUNITY_WSDL_URL.replace(/\{service\}/g, service).replace('{version}', version).replace('{ext}', ext)
      const r = await get(url)
      if (!r.ok) {
        if (ext === 'xsd' && r.status === 404) continue // the schema is inside the WSDL
        say(`✗ ${service} ${version}: ${url} answered ${r.status}`)
        break
      }
      const file = join(folder, `${service}.${ext}`)
      writeFileSync(file, Buffer.from(await r.arrayBuffer()))
      if (ext === 'wsdl') got.push(file)
    }
  }
  return got
}

function traceText(t) {
  if (!t.primary) return t.hint
  const lines = [`${t.goal}`, '', `→ ${t.primary.operation} (${t.primary.service})${t.business_process ? ' — a business process' : ''}`, '', 'Steps:']
  for (const s of t.steps) lines.push(`  ${s.role.padEnd(14)} ${s.kind === 'connector' ? `connector: ${s.action}` : `${s.operation} (${s.service})`} — ${s.why}`)
  if (t.related.length) lines.push('', 'Related: ' + t.related.map((r) => `${r.operation} (${r.service})`).join(', '))
  if (t.alternatives.length) lines.push('', 'Also matched: ' + t.alternatives.map((r) => r.operation).join(', '))
  if (t.notes.length) lines.push('', 'Notes:', ...t.notes.map((n) => `  • ${n}`))
  return lines.join('\n')
}

function showText(o) {
  const lines = [`${o.operation} (${o.service} ${o.version})${o.deprecated ? ' — DEPRECATED' : ''}`, o.description]
  if (o.also_in.length) lines.push(`also in: ${o.also_in.join(', ')}`)
  if (o.notes) lines.push('', 'Notes:', ...o.notes.map((n) => `  • ${n}`))
  lines.push('', o.schema ?? o.hint)
  return lines.join('\n')
}

export async function main(argv) {
  let parsed
  try {
    parsed = parseArgs(argv)
  } catch (e) {
    console.error(`✗ ${e.message}\n${USAGE}`)
    return 2
  }
  const { cmd, args, opts } = parsed
  if (!cmd || cmd === 'help') {
    say(USAGE)
    return cmd ? 0 : 2
  }
  const ix = new Index(opts.index ? resolve(opts.index) : defaultIndexDir())
  try {
    if (cmd === 'ingest') {
      if (!args.length) throw new LookupError('name the files or folders to ingest')
      const r = ingest(ix, args, opts)
      if (opts.json) json(r)
      else say([...r.lines, `indexed ${r.ops} operations from the directory, ${r.schemas} with schemas, in ${ix.dir}`].join('\n'))
      return r.lines.some((l) => l.startsWith('✗')) ? 3 : 0
    }
    if (cmd === 'fetch') {
      const got = await fetchServices(ix, opts)
      const r = got.length ? ingest(ix, got, opts) : { lines: [], ops: 0, schemas: 0 }
      if (opts.json) json({ downloaded: got, ...r })
      else say([...got.map((f) => `↓ ${f}`), ...r.lines].join('\n') || 'nothing downloaded')
      return got.length ? 0 : 3
    }
    if (cmd === 'status') {
      const s = ix.status()
      if (opts.json) json(s)
      else if (ix.empty) say(`Nothing indexed in ${ix.dir} yet. Run: node scripts/wws.mjs ingest <the Operation Directory .txt and the WSDLs you have>`)
      else say([`${s.operations} operations in ${s.index}`, ...s.services.map((x) => `  ${x.service.padEnd(28)} ${String(x.operations).padStart(5)}  ${x.versions}`), `schemas: ${s.schemas.map((x) => `${x.service} ${x.version}`).join(', ') || 'none'}`].join('\n'))
      return 0
    }
    if (ix.empty) {
      console.error(`✗ nothing indexed in ${ix.dir} yet. Run: node scripts/wws.mjs ingest <the Operation Directory .txt and the WSDLs you have>`)
      return 2
    }
    const need = (what) => {
      if (!args[0]) throw new LookupError(`${cmd} needs ${what}`)
      return args.join(' ')
    }
    if (cmd === 'search') {
      const r = ix.search(need('what to look for'), { scope: opts.scope ?? 'hr', limit: Number(opts.limit ?? 10) })
      if (opts.json) json(r)
      else say(r.length ? r.map((x) => `${x.schema_versions.length ? 'S' : ' '} ${x.operation.padEnd(50)} ${x.service.padEnd(22)} ${x.description.slice(0, 90)}`).join('\n') : 'No matches. Try Workday terms in English (time off, job change, business process) or --scope all.')
      return 0
    }
    if (cmd === 'trace') {
      const t = traceUseCase(ix, need('the use case'), { scope: opts.scope ?? 'hr' })
      say(opts.json ? JSON.stringify(t, null, 2) : traceText(t))
      return 0
    }
    const op = need('an operation')
    if (cmd === 'show') {
      const o = getOperation(ix, op, { service: opts.service, version: opts.version, which: opts.response ? 'response' : 'request', path: opts.path, depth: Number(opts.depth ?? 4), fmt: opts.json ? 'json' : 'text' })
      say(opts.json ? JSON.stringify(o, null, 2) : showText(o))
      return o.schema ? 0 : 3
    }
    if (cmd === 'envelope') {
      const e = makeEnvelope(ix, op, { service: opts.service, version: opts.version, mode: opts.all ? 'all' : 'required', include: opts.include, withHeader: Boolean(opts.wsse), bodyOnly: Boolean(opts['body-only']) })
      say(opts.json ? JSON.stringify(e, null, 2) : e.xml ?? e.hint)
      return e.xml ? 0 : 3
    }
    if (cmd === 'copilot') {
      const s = copilotActionSpec(ix, op, { service: opts.service, version: opts.version, include: opts.include, bodyStyle: opts.envelope ? 'envelope' : 'body' })
      json(s)
      return s.warning ? 3 : 0
    }
    if (cmd === 'ess') {
      const t = essTemplate(ix, op, { service: opts.service, version: opts.version, include: opts.include })
      say(opts.json ? JSON.stringify(t, null, 2) : t.xml ?? t.hint)
      return t.xml ? 0 : 3
    }
    throw new LookupError(`${cmd} is not a command`)
  } catch (e) {
    if (!(e instanceof LookupError)) throw e
    console.error(`✗ ${e.message}`)
    return 2
  }
}
