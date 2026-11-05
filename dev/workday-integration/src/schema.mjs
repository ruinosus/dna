// Parses Workday WSDL/XSD files into a compact registry (elements, complex and simple types, attributes, groups) and the
// service's operations. Workday WSDLs usually carry the schema inline in wsdl:types; some downloads ship a separate .xsd
// that xsd:import/include points at — both are read. No network (a remote schemaLocation is never followed) and no
// entities (a DOCTYPE is refused): a WSDL is untrusted input. Port of workday-wws-mcp's schema.py.
import { existsSync, readFileSync } from 'node:fs'
import { basename, dirname, extname, resolve, sep } from 'node:path'
import { SaxesParser } from 'saxes'

export const XSD = 'http://www.w3.org/2001/XMLSchema'
export const WSDL = 'http://schemas.xmlsoap.org/wsdl/'

/** One XML file as a small tree: { uri, local, attrs, ns (in-scope prefixes), children (elements and text) }. */
export function parseXml(text, name = 'XML') {
  const parser = new SaxesParser({ xmlns: true, position: true })
  const stack = []
  let root = null
  parser.on('doctype', () => {
    throw new Error(`${name}: a DOCTYPE is not read (no entities in a WSDL)`)
  })
  parser.on('opentag', (tag) => {
    const parentNs = stack.length ? stack[stack.length - 1].ns : {}
    const declared = {}
    for (const [k, v] of Object.entries(tag.ns ?? {})) declared[k === '' ? '' : k] = v
    const attrs = {}
    for (const a of Object.values(tag.attributes)) if (a.prefix !== 'xmlns' && a.name !== 'xmlns') attrs[a.name] = a.value
    const node = { uri: tag.uri, local: tag.local, attrs, ns: { ...parentNs, ...declared }, children: [] }
    if (stack.length) stack[stack.length - 1].children.push(node)
    else root = node
    stack.push(node)
  })
  // each node keeps only its own text; textOf joins a node's and its descendants' (lxml's itertext)
  parser.on('text', (t) => {
    if (stack.length) stack[stack.length - 1].children.push(t)
  })
  parser.on('cdata', (t) => {
    if (stack.length) stack[stack.length - 1].children.push(t)
  })
  parser.on('closetag', () => stack.pop())
  parser.on('error', (e) => {
    throw new Error(`${name}: ${e.message}`)
  })
  parser.write(text).close()
  if (!root) throw new Error(`${name}: no root element`)
  return root
}

const clean = (t) => (t ?? '').replace(/\s+/g, ' ').trim()
const textOf = (el) => el.children.map((c) => (typeof c === 'string' ? c : textOf(c))).join('')
const elems = (el) => el.children.filter((c) => typeof c !== 'string')
const kids = (el, uri, local) => elems(el).filter((c) => c.uri === uri && (local === undefined || c.local === local))
const first = (el, uri, local) => kids(el, uri, local)[0]

/** A QName resolved against the element's prefixes: 'wd:Worker_ObjectType' → 'Worker_ObjectType', an XSD builtin →
 * 'xsd:string' whatever its prefix. */
export function localNs(el, qname) {
  if (!qname) return null
  const i = qname.indexOf(':')
  if (i >= 0) {
    const [prefix, name] = [qname.slice(0, i), qname.slice(i + 1)]
    return el.ns[prefix] === XSD ? `xsd:${name}` : name
  }
  return el.ns[''] === XSD ? `xsd:${qname}` : qname
}

/** The documentation of xsd:annotation/xsd:documentation (the first that says something). */
function docOf(el) {
  for (const a of kids(el, XSD, 'annotation')) {
    for (const d of kids(a, XSD, 'documentation')) {
      const t = clean(textOf(d))
      if (t) return t
    }
  }
  return ''
}

const occurs = (el) => [Number.parseInt(el.attrs.minOccurs ?? '1', 10), el.attrs.maxOccurs ?? '1']

class SchemaReader {
  constructor(target, baseDir) {
    this.t = target
    this.baseDir = baseDir
    this.seen = new Set()
    this.anon = 0
  }

  readSchema(schema) {
    for (const child of elems(schema)) {
      const tag = child.local
      if (child.uri !== XSD) continue
      if (tag === 'import' || tag === 'include') this.follow(child.attrs.schemaLocation)
      else if (tag === 'element') this.topElement(child)
      else if (tag === 'complexType') this.t.complex[child.attrs.name] = this.complex(child)
      else if (tag === 'simpleType') this.t.simple[child.attrs.name] = this.simple(child)
      else if (tag === 'attribute') this.t.attributes[child.attrs.name] = this.attribute(child)
      else if (tag === 'group') this.t.groups[child.attrs.name] = { doc: docOf(child), content: this.contentOf(child) }
    }
  }

  follow(location) {
    if (!location || location.includes('://')) return // never fetch a remote schema while parsing
    const path = resolve(this.baseDir, location)
    if (this.seen.has(path) || !existsSync(path)) return
    this.seen.add(path)
    const root = parseXml(readFileSync(path, 'utf8'), basename(path))
    if (root.local === 'schema') this.readSchema(root)
  }

  topElement(el) {
    const name = el.attrs.name
    const info = { doc: docOf(el) }
    const typ = localNs(el, el.attrs.type)
    if (typ) info.type = typ
    else {
      const inline = this.inlineType(el, name)
      if (inline) info.type = inline
    }
    this.t.elements[name] = info
  }

  inlineType(el, hint) {
    const ct = first(el, XSD, 'complexType')
    if (ct) {
      const name = `${hint}__inline${++this.anon}`
      this.t.complex[name] = this.complex(ct)
      return name
    }
    const st = first(el, XSD, 'simpleType')
    if (st) {
      const name = `${hint}__inline${++this.anon}`
      this.t.simple[name] = this.simple(st)
      return name
    }
    return null
  }

  attribute(at) {
    const info = { doc: docOf(at) }
    if (at.attrs.ref) info.ref = localNs(at, at.attrs.ref)
    if (at.attrs.name) info.name = at.attrs.name
    const typ = localNs(at, at.attrs.type)
    if (typ) info.type = typ
    else {
      const st = first(at, XSD, 'simpleType')
      if (st) {
        const name = `${at.attrs.name ?? 'attr'}__inline${++this.anon}`
        this.t.simple[name] = this.simple(st)
        info.type = name
      }
    }
    info.use = at.attrs.use ?? 'optional'
    return info
  }

  simple(st) {
    const info = { doc: docOf(st) }
    const r = first(st, XSD, 'restriction')
    if (r) {
      info.base = localNs(r, r.attrs.base)
      const enums = kids(r, XSD, 'enumeration').map((e) => e.attrs.value)
      // Workday lists a reference's ID types (WID, Employee_ID…) as <wd:enumeration> inside xsd:annotation/xsd:appinfo,
      // not as xsd:enumeration: read both
      if (!enums.length) {
        for (const ann of kids(r, XSD, 'annotation')) for (const app of kids(ann, XSD, 'appinfo')) for (const e of elems(app)) if (e.local === 'enumeration' && e.attrs.value !== undefined) enums.push(e.attrs.value)
      }
      if (enums.length) info.enum = enums
      for (const facet of ['maxLength', 'minLength', 'pattern', 'totalDigits', 'fractionDigits']) {
        const f = first(r, XSD, facet)
        if (f) info[facet] = f.attrs.value
      }
    }
    const u = first(st, XSD, 'union')
    if (u) info.union = (u.attrs.memberTypes ?? '').split(/\s+/).filter(Boolean).map((m) => localNs(u, m))
    const list = first(st, XSD, 'list')
    if (list) info.list_of = localNs(list, list.attrs.itemType)
    return info
  }

  complex(ct) {
    const info = { doc: docOf(ct), content: [], attrs: [] }
    if (ct.attrs.mixed === 'true') info.mixed = true
    const sc = first(ct, XSD, 'simpleContent')
    const cc = first(ct, XSD, 'complexContent')
    let holder = ct
    if (sc || cc) {
      const wrap = sc ?? cc
      const ext = first(wrap, XSD, 'extension') ?? first(wrap, XSD, 'restriction')
      if (ext) {
        info.base = localNs(ext, ext.attrs.base)
        info.derivation = ext.local
        holder = ext
      }
      if (sc) info.simple_content = true
    }
    info.content = this.contentOf(holder)
    for (const at of kids(holder, XSD, 'attribute')) info.attrs.push(this.attribute(at))
    return info
  }

  contentOf(holder) {
    const out = []
    for (const child of elems(holder)) {
      if (child.uri !== XSD) continue
      if (['sequence', 'choice', 'all'].includes(child.local)) out.push(this.compositor(child))
      else if (child.local === 'group' && child.attrs.ref) {
        const [min, max] = occurs(child)
        out.push({ kind: 'group', ref: localNs(child, child.attrs.ref), min, max })
      }
    }
    return out
  }

  compositor(comp) {
    const [min, max] = occurs(comp)
    const node = { kind: comp.local, min, max, items: [] }
    for (const child of elems(comp)) {
      if (child.uri !== XSD) continue
      const tag = child.local
      if (tag === 'element') node.items.push(this.particleElement(child))
      else if (['sequence', 'choice', 'all'].includes(tag)) node.items.push(this.compositor(child))
      else if (tag === 'group' && child.attrs.ref) {
        const [gmin, gmax] = occurs(child)
        node.items.push({ kind: 'group', ref: localNs(child, child.attrs.ref), min: gmin, max: gmax })
      } else if (tag === 'any') {
        const [amin, amax] = occurs(child)
        node.items.push({ kind: 'any', min: amin, max: amax })
      }
    }
    return node
  }

  particleElement(el) {
    const [min, max] = occurs(el)
    if (el.attrs.ref) {
      const name = localNs(el, el.attrs.ref)
      return { kind: 'element', name, ref: name, min, max, doc: docOf(el) }
    }
    const name = el.attrs.name
    const item = { kind: 'element', name, min, max, doc: docOf(el) }
    const typ = localNs(el, el.attrs.type)
    if (typ) item.type = typ
    else item.type = this.inlineType(el, name) ?? 'xsd:string'
    if (el.attrs.nillable === 'true') item.nillable = true
    return item
  }
}

const VERSION = /^v\d+(?:\.\d+)?$/

/** The version from a folder of the path (…/v47.0/…) or from the file name. */
export function guessVersion(path) {
  for (const part of path.split(sep).reverse()) if (VERSION.test(part)) return part
  return /v\d+(?:\.\d+)?/.exec(basename(path))?.[0] ?? null
}

/** A WSDL (or a bare XSD) as { service, version, operations, elements, complex, simple, attributes, groups }. */
export function parseWsdl(path, { service, version } = {}) {
  const root = parseXml(readFileSync(path, 'utf8'), basename(path))
  const stem = basename(path, extname(path))
  const target = {
    service: (service || root.attrs.name || stem).replace(/[\s-]+/g, '_'),
    version: version || guessVersion(path),
    operations: {}, elements: {}, complex: {}, simple: {}, attributes: {}, groups: {},
  }
  const reader = new SchemaReader(target, dirname(path))
  if (root.local === 'schema') {
    reader.readSchema(root)
    return target
  }
  if (root.local !== 'definitions') throw new Error(`${basename(path)}: not a WSDL or XSD (root element <${root.local}>)`)
  for (const types of kids(root, WSDL, 'types')) for (const schema of kids(types, XSD, 'schema')) reader.readSchema(schema)
  // a sibling .xsd with the same name is common in Workday downloads
  const sibling = `${stem}.xsd`
  if (existsSync(resolve(dirname(path), sibling)) && !Object.keys(target.complex).length) reader.follow(sibling)

  const messages = {}
  for (const msg of kids(root, WSDL, 'message')) {
    const part = first(msg, WSDL, 'part')
    messages[msg.attrs.name] = part ? localNs(part, part.attrs.element) : null
  }
  for (const pt of kids(root, WSDL, 'portType')) {
    for (const op of kids(pt, WSDL, 'operation')) {
      const docEl = first(op, WSDL, 'documentation')
      const inp = first(op, WSDL, 'input')
      const out = first(op, WSDL, 'output')
      target.operations[op.attrs.name] = {
        name: op.attrs.name,
        doc: docEl ? clean(textOf(docEl)) : '',
        request_element: inp ? (messages[localNs(inp, inp.attrs.message)] ?? null) : null,
        response_element: out ? (messages[localNs(out, out.attrs.message)] ?? null) : null,
      }
    }
  }
  return target
}

/** The part of a parsed service that trees are built from. */
export const registryOf = (s) => ({ elements: s.elements, complex: s.complex, simple: s.simple, attributes: s.attributes, groups: s.groups })
