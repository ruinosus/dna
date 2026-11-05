// The catalog on disk: operations (from the Operation Directory text and from WSDLs), each service's schema registry,
// and a search with SQLite FTS5's bm25 over the same columns and weights the Python port used (operation words 10,
// description 2, services 0.5, field names 0.7), Porter stems, PT/EN synonyms and stopwords. JSON files in a folder —
// index.json and schemas/<service>-<version>.json — never inside the skill. Port of workday-wws-mcp's index.py.
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { HR_SERVICES, STOPWORDS, SYNONYMS } from './config.mjs'
import { stem } from './porter.mjs'
import { LookupError, TreeBuilder } from './render.mjs'
import { registryOf } from './schema.mjs'

/** The default folder: $WWS_INDEX, else $XDG_CACHE_HOME/dna/workday-integration, else ~/.cache/dna/workday-integration. */
export function defaultIndexDir() {
  if (process.env.WWS_INDEX) return process.env.WWS_INDEX
  return join(process.env.XDG_CACHE_HOME || join(homedir(), '.cache'), 'dna', 'workday-integration')
}

/** Lowercase, no accents. */
export const fold = (text) => text.toLowerCase().normalize('NFKD').replace(/\p{M}/gu, '')
export const opWords = (op) => op.replace(/_/g, ' ').replace(/-/g, ' ')
const versionKey = (v) => (v.match(/\d+/g) ?? ['0']).map(Number)
const cmpVersion = (a, b) => {
  const [x, y] = [versionKey(a), versionKey(b)]
  for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] ?? -1) !== (y[i] ?? -1)) return (x[i] ?? -1) - (y[i] ?? -1)
  return 0
}
const latest = (rows) => rows.reduce((a, b) => (cmpVersion(b.version, a.version) > 0 ? b : a))
const unique = (xs) => [...new Set(xs)]

const ENTITIES = { nbsp: ' ', amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }
const plain = (html) => html.replace(/<[^>]+>/g, ' ').replace(/&(#\d+|#x[0-9a-f]+|\w+);/gi, (m, e) => (e[0] === '#' ? String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : Number(e.slice(1))) : ENTITIES[e] ?? m)).replace(/~/g, '').replace(/\s+/g, ' ').trim()

/** The Operation Directory page itself (its HTML, as fetch downloads it): a row per operation — its name (and
 * DEPRECATED), its description and the services it is in. */
export function parseDirectoryHtml(html) {
  const version = /Operation Directory:\s*\((v\d+(?:\.\d+)?)/.exec(html)?.[1] ?? null
  const entries = []
  for (const row of html.match(/<tr\b[\s\S]*?<\/tr>/gi) ?? []) {
    const cells = row.match(/<td\b[\s\S]*?<\/td>/gi)
    if (!cells || cells.length < 3) continue
    const name = /<a\b[^>]*>([\s\S]*?)<\/a>/i.exec(cells[0])?.[1]?.trim()
    if (!name || !/^[A-Za-z0-9_-]+$/.test(name)) continue
    const services = [...cells[2].matchAll(/<a\b[^>]*>([\s\S]*?)<\/a>/gi)].map((m) => plain(m[1])).filter((x) => /^[A-Za-z0-9_]+$/.test(x))
    entries.push({ op: name, description: plain(cells[1]), services, deprecated: /DEPRECATED/.test(cells[0]) })
  }
  return { version, entries }
}

/** The text of the Workday «Operation Directory» page: header lines, then «Operation<TAB>Description<TAB>Web Service(s)»
 * and a line per operation; one exposed by several services lists the others on the lines after it, with no tab. */
export function parseDirectory(text) {
  if (/<table/i.test(text) && /Operation Directory/.test(text)) return parseDirectoryHtml(text)
  const version = /Operation Directory:\s*\((v\d+(?:\.\d+)?)/.exec(text)?.[1] ?? null
  const entries = []
  let started = false
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\r$/, '')
    if (!started) {
      if (line.startsWith('Operation\t') && line.includes('Web Service')) started = true
      continue
    }
    if (!line.trim()) continue
    if (line.includes('\t')) {
      const cols = line.split('\t').map((c) => c.trim())
      if (cols.length < 2) continue
      let name = cols[0]
      let deprecated = false
      if (name.endsWith(' DEPRECATED')) {
        name = name.slice(0, -' DEPRECATED'.length).trim()
        deprecated = true
      }
      if (!/^[A-Za-z0-9_-]+$/.test(name)) continue
      entries.push({ op: name, description: cols[1] ?? '', services: cols[2] ? [cols[2]] : [], deprecated })
    } else if (entries.length && /^[A-Za-z0-9_]+$/.test(line.trim())) entries[entries.length - 1].services.push(line.trim())
  }
  return { version, entries }
}

// FTS5's unicode61 tokenizer (remove_diacritics 2), then porter
const tokens = (text) => (fold(text).match(/[\p{L}\p{N}]+/gu) ?? []).map(stem)

export class Index {
  constructor(dir = defaultIndexDir()) {
    this.dir = dir
    this.file = join(dir, 'index.json')
    this.data = existsSync(this.file) ? JSON.parse(readFileSync(this.file, 'utf8')) : { format: 'dna/workday-integration/index-v1', operations: [], schemas: {}, fields: {}, meta: {} }
    this.cache = new Map()
  }

  get empty() {
    return !this.data.operations.length
  }

  save() {
    mkdirSync(this.dir, { recursive: true })
    const tmp = `${this.file}.tmp`
    writeFileSync(tmp, JSON.stringify(this.data))
    renameSync(tmp, this.file)
  }

  rows(op, service, version) {
    return this.data.operations.filter((r) => (op === undefined || r.op === op) && (service === undefined || r.service === service) && (version === undefined || r.version === version))
  }

  ingestDirectory(text, version) {
    const { version: dver, entries } = parseDirectory(text)
    const ver = version || dver || 'unknown'
    for (const e of entries) {
      for (const svc of e.services.length ? e.services : ['Unknown']) {
        const row = this.rows(e.op, svc, ver)[0]
        if (row) {
          if (e.description !== '') row.description = e.description
          row.deprecated = e.deprecated
        } else this.data.operations.push({ op: e.op, service: svc, version: ver, description: e.description, deprecated: e.deprecated, source: 'directory', request_element: null, response_element: null })
      }
    }
    this.data.meta.directory_version = ver
    this.save()
    return entries.length
  }

  ingestSchema(ss, sourcePath = null) {
    if (!ss.version) throw new Error(`Could not infer version for ${ss.service}; pass --version (e.g. v47.0)`)
    const reg = registryOf(ss)
    mkdirSync(join(this.dir, 'schemas'), { recursive: true })
    const file = `schemas/${ss.service}-${ss.version}.json`
    writeFileSync(join(this.dir, file), JSON.stringify(reg))
    this.data.schemas[`${ss.service}|${ss.version}`] = { service: ss.service, version: ss.version, file, source_path: sourcePath, ingested_at: new Date().toISOString() }
    const builder = new TreeBuilder(reg, { maxDepth: 3, maxNodes: 400 })
    for (const op of Object.values(ss.operations)) {
      const row = this.rows(op.name, ss.service, ss.version)[0]
      if (row) {
        if (row.description === '') row.description = op.doc
        row.request_element = op.request_element
        row.response_element = op.response_element
      } else this.data.operations.push({ op: op.name, service: ss.service, version: ss.version, description: op.doc, deprecated: false, source: 'wsdl', request_element: op.request_element, response_element: op.response_element })
      const names = new Set()
      if (op.request_element && reg.elements[op.request_element]) {
        try {
          const stack = [builder.element(op.request_element)]
          while (stack.length) {
            const n = stack.pop()
            names.add(opWords(n.name))
            stack.push(...n.children)
          }
        } catch {
          // never block an ingest on one operation's tree
        }
      }
      this.data.fields[`${op.name}|${ss.service}`] = [...names].sort().join(' ')
    }
    this.cache.delete(`${ss.service}|${ss.version}`)
    this.save()
    return Object.keys(ss.operations).length
  }

  /** The search documents, one per operation and service, as FTS5 held them. */
  documents() {
    const keys = unique(this.data.operations.map((r) => `${r.op}|${r.service}`))
    return keys.map((key) => {
      const [op, svc] = key.split('|')
      const desc = latest(this.rows(op, svc)).description
      const services = unique(this.rows(op).map((r) => r.service)).join(' ')
      const cols = [opWords(op), desc, opWords(services), this.data.fields[key] ?? ''].map(tokens)
      return { key, cols, length: cols.reduce((n, c) => n + c.length, 0) }
    })
  }

  /** The words as they are: folded, without stopwords and repeats. */
  static plainTerms(query) {
    return unique((fold(query).match(/[\p{L}\p{N}_]+/gu) ?? []).filter((t) => !STOPWORDS.has(t) && t.length >= 2))
  }

  /** Fold, drop stopwords, add the PT/EN synonyms (and a Portuguese word's inflections). */
  static expandTerms(query) {
    let q = fold(query)
    for (const [phrase, repl] of [['home office', 'homeoffice'], ['caixa de entrada', 'inbox'], ['trabalho remoto', 'remoto'], ['trabalho flexivel', 'fwa'], ['flexible work', 'fwa']]) q = q.split(phrase).join(repl)
    const terms = []
    for (const tok of q.match(/[\p{L}\p{N}_]+/gu) ?? []) {
      if (STOPWORDS.has(tok) || tok.length < 2) continue
      terms.push(tok)
      const syn = SYNONYMS[tok]
      if (syn === undefined && tok.length >= 6) {
        // inflections: solicita/solicitou → solicitar, aprova → aprovar
        for (const [key, vals] of Object.entries(SYNONYMS)) if (key.length >= 6 && key.slice(0, 6) === tok.slice(0, 6)) terms.push(...vals)
      } else if (syn) terms.push(...syn)
    }
    return unique(terms)
  }

  /** FTS5's bm25 for an OR of phrases ("term"* for 4 letters or more), with its weights: the lower, the better. */
  bm25(terms) {
    const docs = this.documents()
    terms = terms.filter((t) => tokens(t.replace(/"/g, '')).length)
    const phrases = terms.map((t) => ({ words: tokens(t.replace(/"/g, '')), prefix: t.replace(/"/g, '').length >= 4 }))
    const matches = (col, p) => {
      let n = 0
      for (let i = 0; i + p.words.length <= col.length; i++) {
        if (p.words.every((w, j) => (p.prefix && j === p.words.length - 1 ? col[i + j].startsWith(w) : col[i + j] === w))) n++
      }
      return n
    }
    const W = [10, 2, 0.5, 0.7]
    const N = docs.length
    const avg = docs.reduce((n, d) => n + d.length, 0) / Math.max(1, N)
    const counts = docs.map((d) => phrases.map((p) => d.cols.map((c) => matches(c, p))))
    const idf = phrases.map((_, i) => {
      const n = counts.filter((c) => c[i].some((x) => x > 0)).length
      const v = Math.log((N - n + 0.5) / (n + 0.5))
      return v <= 0 ? 1e-6 : v
    })
    const out = []
    docs.forEach((d, k) => {
      if (!counts[k].some((c) => c.some((x) => x > 0))) return
      let score = 0
      phrases.forEach((_, i) => {
        const f = counts[k][i].reduce((s, x, c) => s + W[c] * x, 0)
        score += idf[i] * ((f * (1.2 + 1)) / (f + 1.2 * (1 - 0.75 + (0.75 * d.length) / avg)))
      })
      const COLS = ['operation name', 'description', 'services', 'fields']
      const matched = phrases.map((p, i) => ({ term: terms[i], in: counts[k][i].map((x, c) => (x ? COLS[c] : null)).filter(Boolean) })).filter((m) => m.in.length)
      out.push({ key: d.key, score: -score, matched })
    })
    return out.sort((a, b) => a.score - b.score).slice(0, 400)
  }

  /** The operations the words find, best first, each with what it matched and where. By default the words are taken as
   * they are (in Workday's English, as the agent translates them); expand: true adds the Portuguese synonyms and the
   * verb boost of the Python port. */
  search(query, { scope = 'hr', services = [], limit = 10, includeDeprecated = false, expand = false } = {}) {
    const terms = expand ? Index.expandTerms(query) : Index.plainTerms(query)
    let allowed = new Set(services)
    if (!allowed.size && scope === 'hr') allowed = new Set(HR_SERVICES)
    const exact = new Set((query.match(/[A-Za-z0-9_]+/g) ?? []).filter((t) => t.includes('_')).map((t) => t.toLowerCase()))
    const intent = new Set(terms)
    const scored = new Map()
    const matchedBy = new Map()
    for (const r of terms.length ? this.bm25(terms) : []) {
      const [op, svc] = r.key.split('|')
      if (allowed.size && !allowed.has(svc)) continue
      let s = r.score
      if (exact.has(op.toLowerCase())) s -= 100
      if (expand && intent.has(op.split('_')[0].toLowerCase())) s -= 3 // the operation's verb is the intent (add, end, get, approve…)
      if (!scored.has(r.key) || s < scored.get(r.key)) {
        scored.set(r.key, s)
        matchedBy.set(r.key, r.matched)
      }
    }
    // an exact name, even when the tokens miss it
    for (const name of exact) {
      for (const key of unique(this.data.operations.filter((r) => r.op.toLowerCase() === name).map((r) => `${r.op}|${r.service}`))) {
        if (allowed.size && !allowed.has(key.split('|')[1])) continue
        if (!scored.has(key)) {
          scored.set(key, -1000)
          matchedBy.set(key, [{ term: name, in: ['the exact name'] }])
        }
      }
    }
    const results = []
    for (const [key, score] of [...scored].sort((a, b) => a[1] - b[1])) {
      const [op, svc] = key.split('|')
      const info = this.operationSummary(op, svc)
      if (!info || (info.deprecated && !includeDeprecated)) continue
      info.score = Math.round(-score * 1000) / 1000
      info.matched = matchedBy.get(key) ?? []
      results.push(info)
      if (results.length >= limit) break
    }
    return results
  }

  operationSummary(op, service) {
    const rows = this.rows(op, service)
    if (!rows.length) return null
    const last = latest(rows)
    return {
      operation: op,
      service,
      also_in: unique(this.rows(op).filter((r) => r.service !== service).map((r) => r.service)),
      description: last.description,
      deprecated: Boolean(last.deprecated),
      versions: unique(rows.map((r) => r.version)).sort((a, b) => cmpVersion(b, a)),
      schema_versions: unique(rows.filter((r) => r.request_element).map((r) => r.version)).sort((a, b) => cmpVersion(b, a)),
    }
  }

  /** The operation to use (case-insensitive); a row with a schema first, then the latest version. */
  resolve(op, service, version) {
    const rows = this.data.operations.filter((r) => r.op.toLowerCase() === op.toLowerCase() && (!service || r.service === service) && (!version || r.version === version))
    if (!rows.length) {
      const hint = this.search(op.replace(/_/g, ' '), { scope: 'all', limit: 5 })
      const names = hint.map((h) => `${h.operation} (${h.service})`).join(', ') || 'none'
      throw new LookupError(`Operation '${op}' not found${service ? ' in ' + service : ''}${version ? ' ' + version : ''}. Closest: ${names}`)
    }
    const withSchema = rows.filter((r) => r.request_element)
    return latest(withSchema.length ? withSchema : rows)
  }

  registry(service, version) {
    const key = `${service}|${version}`
    if (this.cache.has(key)) return this.cache.get(key)
    const s = this.data.schemas[key]
    if (!s || !existsSync(join(this.dir, s.file))) return null
    const reg = JSON.parse(readFileSync(join(this.dir, s.file), 'utf8'))
    this.cache.set(key, reg)
    return reg
  }

  /** The operations on the same noun (Add_X, End_X, Get_X…). */
  related(op) {
    const m = /^(?:[A-Za-z]+?)_(.+)$/.exec(op)
    if (!m) return []
    const noun = m[1]
    const stems = new Set([noun, noun.replace(/s+$/, ''), noun + 's'])
    const out = []
    const seen = new Set()
    for (const r of this.data.operations) {
      const mm = /^([A-Za-z]+?)_(.+)$/.exec(r.op)
      const key = `${r.op}|${r.service}`
      if (!mm || r.op === op || seen.has(key)) continue
      if (stems.has(mm[2])) {
        seen.add(key)
        out.push({ operation: r.op, service: r.service, verb: mm[1] })
      }
    }
    return out
  }

  status() {
    const perService = new Map()
    for (const r of this.data.operations) {
      const s = perService.get(r.service) ?? { service: r.service, ops: new Set(), versions: [] }
      s.ops.add(r.op)
      if (!s.versions.includes(r.version)) s.versions.push(r.version)
      perService.set(r.service, s)
    }
    return {
      index: this.dir,
      operations: unique(this.data.operations.map((r) => `${r.op}|${r.service}`)).length,
      services: [...perService.values()].sort((a, b) => b.ops.size - a.ops.size || (a.service < b.service ? -1 : 1)).map((s) => ({ service: s.service, operations: s.ops.size, versions: s.versions.join(',') })),
      schemas: Object.values(this.data.schemas).sort((a, b) => (a.service < b.service ? -1 : 1)).map(({ service, version, source_path, ingested_at }) => ({ service, version, source_path, ingested_at })),
      meta: this.data.meta,
    }
  }
}
