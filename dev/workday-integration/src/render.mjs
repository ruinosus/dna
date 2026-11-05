// A parsed registry as trees, field lists and SOAP envelopes with {{placeholders}}. Port of workday-wws-mcp's render.py.
export const SOAP_ENV = 'http://schemas.xmlsoap.org/soap/envelope/'
export const BSVC = 'urn:com.workday/bsvc'

const XSD_HINT = {
  'xsd:date': 'YYYY-MM-DD', 'xsd:dateTime': 'YYYY-MM-DDThh:mm:ss', 'xsd:boolean': 'true|false', 'xsd:decimal': 'number',
  'xsd:int': 'integer', 'xsd:integer': 'integer', 'xsd:long': 'integer', 'xsd:time': 'hh:mm:ss',
}

const escapeXml = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

export class Node {
  constructor({ name, path, type = null, min = 1, max = '1', doc = '' }) {
    Object.assign(this, { name, path, type, min, max, doc })
    this.leaf = false
    this.value_type = null
    this.enum = null
    this.attrs = []
    this.children = []
    this.choice = null
    this.recursive = false
    this.truncated = false
    this.any = false // an xsd:any here: any element may go in
  }

  get required() {
    return this.min >= 1 && this.choice === null
  }

  get card() {
    const many = this.max !== '1' && this.max !== '0'
    if (this.min >= 1) return many ? '+' : ''
    return many ? '*' : '?'
  }

  /** A Workday *ObjectType: a list of ID elements carrying an @type. */
  get isReference() {
    return this.children.some((c) => c.name === 'ID' && c.attrs.some((a) => a.name === 'type'))
  }

  toDict(maxDepth = null, d = 0) {
    const out = { name: this.name, path: this.path, card: this.card || '1' }
    if (this.type) out.type = this.type
    if (this.value_type) out.value_type = this.value_type
    if (this.doc) out.doc = this.doc
    if (this.enum?.length) out.enum = this.enum
    if (this.attrs.length) out.attrs = this.attrs
    if (this.choice) out.choice = this.choice
    if (this.recursive) out.recursive = true
    if (this.any) out.any = true
    if (this.children.length) {
      if (maxDepth !== null && d >= maxDepth) out.children_truncated = this.children.length
      else out.children = this.children.map((c) => c.toDict(maxDepth, d + 1))
    } else if (this.truncated) out.children_truncated = true
    return out
  }
}

export class TreeBuilder {
  constructor(registry, { maxDepth = 12, maxNodes = 6000 } = {}) {
    this.r = registry
    this.maxDepth = maxDepth
    this.maxNodes = maxNodes
    this.count = 0
    this.choiceSeq = 0
  }

  /** A simpleType chain → [builtin base, enum values]. */
  simpleInfo(tname) {
    const seen = new Set()
    let enumv = null
    let cur = tname
    while (cur && !cur.startsWith('xsd:') && !seen.has(cur)) {
      seen.add(cur)
      const st = this.r.simple[cur]
      if (!st) {
        const ct = this.r.complex[cur]
        if (ct?.simple_content) {
          cur = ct.base ?? null
          continue
        }
        return [cur, enumv]
      }
      if (st.enum?.length && enumv === null) enumv = st.enum
      if (st.union?.length) return ['xsd:string', enumv]
      if (st.list_of) return ['xsd:string', enumv]
      cur = st.base ?? null
    }
    return [cur, enumv]
  }

  attrsOf(ctype, seen = new Set()) {
    const out = []
    const base = ctype.base
    if (base && this.r.complex[base] && !seen.has(base)) {
      seen.add(base)
      out.push(...this.attrsOf(this.r.complex[base], seen))
    }
    for (const a of ctype.attrs ?? []) {
      let info = { ...a }
      if ('ref' in info && !('name' in info)) {
        const top = this.r.attributes[info.ref] ?? {}
        const { ref, ...own } = info
        info = { ...top, ...own, name: ref }
      }
      const [vt, enumv] = this.simpleInfo(info.type)
      const entry = { name: info.name ?? null, use: info.use ?? 'optional' }
      if (vt) entry.type = vt
      if (enumv?.length) entry.enum = enumv
      if (info.doc) entry.doc = info.doc
      out.push(entry)
    }
    return out
  }

  /** Content particles, the base type's first for an extension. */
  contentItems(ctype, seen = new Set()) {
    const items = []
    const base = ctype.base
    if (base && ctype.derivation === 'extension' && this.r.complex[base] && !seen.has(base)) {
      seen.add(base)
      items.push(...this.contentItems(this.r.complex[base], seen))
    }
    items.push(...(ctype.content ?? []))
    return items
  }

  element(name) {
    const info = this.r.elements[name]
    if (!info) throw new Error(`element '${name}' not found in schema`)
    this.count = 0
    return this.expand(name, name, info.type ?? null, 1, '1', info.doc ?? '', [], 0)
  }

  expand(name, path, tname, min, max, doc, stack, depth) {
    this.count++
    const node = new Node({ name, path, type: tname, min, max, doc })
    if (tname === null || tname.startsWith('xsd:')) {
      node.leaf = true
      node.value_type = tname ?? 'xsd:string'
      return node
    }
    const ct = this.r.complex[tname]
    if (!ct) {
      const [vt, enumv] = this.simpleInfo(tname)
      Object.assign(node, { leaf: true, value_type: vt, enum: enumv })
      return node
    }
    if (!node.doc) node.doc = ct.doc ?? ''
    node.attrs = this.attrsOf(ct)
    if (ct.simple_content) {
      const [vt, enumv] = this.simpleInfo(ct.base ?? null)
      Object.assign(node, { leaf: true, value_type: vt, enum: enumv })
      return node
    }
    if (stack.includes(tname)) {
      node.recursive = true
      return node
    }
    if (depth >= this.maxDepth || this.count >= this.maxNodes) {
      node.truncated = true
      return node
    }
    for (const item of this.contentItems(ct)) this.particle(node, item, [...stack, tname], depth, false, null)
    if (!node.children.length && !node.attrs.length && !node.any) {
      node.leaf = true
      node.value_type = ct.content?.length ? null : 'xsd:string'
    }
    return node
  }

  particle(parent, item, stack, depth, optional, choice) {
    const kind = item.kind
    if (kind === 'element') {
      let tname = item.type ?? null
      let doc = item.doc ?? ''
      if (item.ref) {
        const top = this.r.elements[item.ref] ?? {}
        tname = tname ?? top.type ?? null
        doc = doc || top.doc || ''
      }
      const min = optional ? 0 : (item.min ?? 1)
      const child = this.expand(item.name, `${parent.path}/${item.name}`, tname, min, item.max ?? '1', doc, stack, depth + 1)
      child.choice = choice
      parent.children.push(child)
    } else if (kind === 'sequence' || kind === 'all') {
      const opt = optional || (item.min ?? 1) === 0
      for (const sub of item.items ?? []) this.particle(parent, sub, stack, depth, opt, choice)
    } else if (kind === 'choice') {
      this.choiceSeq++
      const cid = `choice${this.choiceSeq}` + ((item.min ?? 1) >= 1 && !optional ? '' : '?')
      for (const sub of item.items ?? []) this.particle(parent, sub, stack, depth, true, cid)
    } else if (kind === 'any') {
      parent.any = true
    } else if (kind === 'group') {
      const grp = this.r.groups[item.ref]
      if (grp) {
        const opt = optional || (item.min ?? 1) === 0
        for (const sub of grp.content ?? []) this.particle(parent, sub, stack, depth, opt, choice)
      }
    }
  }
}

/** A descendant by its slash path, relative to (or including) the root. */
export function findPath(root, path) {
  let parts = path.replace(/^\/+|\/+$/g, '').split('/').filter(Boolean)
  if (parts[0] === root.name) parts = parts.slice(1)
  let cur = root
  for (const part of parts) {
    const next = cur.children.find((c) => c.name === part)
    if (!next) {
      const avail = cur.children.map((c) => c.name).join(', ') || '(no children)'
      throw new LookupError(`'${part}' not under ${cur.path}. Children: ${avail}`)
    }
    cur = next
  }
  return cur
}

/** A name, a path or an operation that is not there: the CLI says it and exits 2. */
export class LookupError extends Error {}

const short = (t) => (t ? t.replace(/xsd:/g, '') : '')

export function renderTree(root, { maxDepth = 4, requiredOnly = false, docChars = 110 } = {}) {
  const lines = []
  const legend = 'card: (none)=1  ?=0..1  *=0..n  +=1..n  |=choice member  @=attribute  ↻=recursive'
  const walk = (n, depth) => {
    if (requiredOnly && depth > 0 && !n.required) return
    const bits = ['  '.repeat(depth) + (n.choice ? '| ' : '') + n.name + n.card]
    if (n.leaf) bits.push(`: ${short(n.value_type)}`)
    else if (n.type) bits.push(`<${n.type}>`)
    if (n.enum?.length) bits.push('{' + n.enum.slice(0, 8).join('|') + (n.enum.length > 8 ? '|…' : '') + '}')
    for (const a of n.attrs) {
      let txt = `@${a.name}${a.use === 'required' ? '' : '?'}`
      if (a.enum?.length) txt += '{' + a.enum.slice(0, 6).join('|') + (a.enum.length > 6 ? '|…' : '') + '}'
      bits.push(txt)
    }
    if (n.recursive) bits.push('↻')
    if (n.doc && docChars) bits.push('— ' + ([...n.doc].length <= docChars ? n.doc : [...n.doc].slice(0, docChars - 1).join('') + '…'))
    lines.push(bits.join(' '))
    if (n.children.length) {
      if (depth >= maxDepth) {
        lines.push('  '.repeat(depth + 1) + `… ${n.children.length} children (increase depth or use path)`)
        return
      }
      for (const c of n.children) walk(c, depth + 1)
    } else if (n.truncated) lines.push('  '.repeat(depth + 1) + '… (expansion limit reached; use path to drill in)')
    if (n.any && depth < maxDepth) lines.push('  '.repeat(depth + 1) + '(any element may go here: xsd:any)')
  }
  walk(root, 0)
  return legend + '\n' + lines.join('\n')
}

function pickIdType(node, enumv) {
  if (!enumv.length) return 'WID'
  const lname = node.name.toLowerCase()
  if (lname.includes('event') || lname.includes('business_process')) return enumv.includes('WID') ? 'WID' : enumv[0]
  // a person: Employee_ID when it is an option (Workday lists Contingent_Worker_ID first)
  if (enumv.includes('Employee_ID')) return 'Employee_ID'
  const nonWid = enumv.filter((e) => e !== 'WID')
  return nonWid[0] ?? enumv[0]
}

/** A SOAP envelope (or only the body) and the variables it needs. mode 'required': only what is required, plus the
 * `include` paths (their ancestors come with them); 'all': every element down to the tree's depth. */
export function buildEnvelope(root, { operationVersion = null, include = [], mode = 'required', withHeader = false, bodyOnly = false } = {}) {
  const forced = new Set()
  for (let p of include) {
    p = p.replace(/^\/+|\/+$/g, '')
    if (!p.startsWith(root.name)) p = `${root.name}/${p}`
    const parts = p.split('/')
    for (let i = 1; i <= parts.length; i++) forced.add(parts.slice(0, i).join('/'))
  }
  const forcedUnder = (path) => [...forced].some((f) => f.startsWith(path + '/'))
  // each choice's members, by the choice's id
  const choices = new Map()
  const collect = (n) => {
    if (n.choice) choices.set(n.choice, [...(choices.get(n.choice) ?? []), n.name])
    n.children.forEach(collect)
  }
  collect(root)
  const variables = []
  const used = new Map()
  const seenChoice = new Set()

  const varName = (n) => {
    const segs = n.path.split('/')
    const parent = segs.length >= 2 ? segs[segs.length - 2] : ''
    let base = n.name !== 'ID' ? n.name : parent || 'ID'
    if (n.name === 'ID') base = base.replace(/_Reference$/, '_ID')
    used.set(base, (used.get(base) ?? 0) + 1)
    return used.get(base) === 1 ? base : `${base}_${used.get(base)}`
  }

  const want = (n) => {
    if (forced.has(n.path) || forcedUnder(n.path)) return true
    if (mode === 'all') return true
    if (n.choice) {
      if (n.choice.endsWith('?') || seenChoice.has(n.choice)) return false
      seenChoice.add(n.choice)
      return true
    }
    return n.min >= 1
  }

  const out = []
  const carried = []
  const emit = (n, depth, isRoot = false) => {
    const pad = '  '.repeat(depth)
    if (carried.includes(n.path)) out.push(`${pad}<!-- optional in the schema, but it holds the required fields -->`)
    const tag = `wd:${n.name}`
    const attrs = isRoot && operationVersion ? ` wd:version="${escapeXml(operationVersion)}"` : ''
    // a choice, as zeep and SoapUI show it: the alternatives by name, one to keep
    if (n.choice) out.push(`${pad}<!-- one of (${n.choice.endsWith('?') ? 'optional' : 'required'}): ${(choices.get(n.choice) ?? []).join(' | ')} — keep one -->`)
    if (n.isReference && !forcedUnder(n.path)) {
      const idNode = n.children.find((c) => c.name === 'ID')
      const typeAttr = idNode.attrs.find((a) => a.name === 'type') ?? {}
      const enumv = typeAttr.enum ?? []
      const chosen = pickIdType(n, enumv)
      const v = varName(new Node({ name: 'ID', path: `${n.path}/ID` }))
      variables.push({ var: v, path: `${n.path}/ID`, xsd_type: 'xsd:string', required: n.required, enum: enumv, doc: n.doc, id_type: chosen })
      if (enumv.length > 1) out.push(`${pad}<!-- ${n.name}: ID @type options: ${enumv.slice(0, 12).join(', ')}${enumv.length > 12 ? '…' : ''} -->`)
      out.push(`${pad}<${tag}>`, `${pad}  <wd:ID wd:type="${chosen}">{{${v}}}</wd:ID>`, `${pad}</${tag}>`)
      return
    }
    if (n.leaf) {
      const v = varName(n)
      const hint = XSD_HINT[n.value_type ?? ''] ?? ''
      variables.push({ var: v, path: n.path, xsd_type: n.value_type, required: n.required, enum: n.enum, doc: n.doc, id_type: null })
      const note = n.enum?.length ? `  <!-- one of: ${n.enum.slice(0, 10).join(', ')} -->` : hint ? `  <!-- ${hint} -->` : ''
      out.push(`${pad}<${tag}${attrs}>{{${v}}}</${tag}>${note}`)
      return
    }
    let kids = n.children.filter(want)
    // Workday often makes the data container optional though it holds the required fields (Add_…_Event_Data): an
    // element that would go empty takes the optional children that have a required field of their own
    const carriers = kids.length || mode === 'all' ? [] : n.children.filter((c) => !c.choice && c.children.some((d) => d.required))
    if (carriers.length) {
      kids = carriers
      carried.push(...carriers.map((c) => c.path))
    }
    if (!kids.length) {
      out.push(n.recursive || n.truncated ? `${pad}<${tag}${attrs}><!-- expand with include=[...] --></${tag}>` : n.any ? `${pad}<${tag}${attrs}><!-- any element may go here (xsd:any) --></${tag}>` : `${pad}<${tag}${attrs}/>`)
      return
    }
    out.push(`${pad}<${tag}${attrs}>`)
    for (const c of kids) emit(c, depth + 1)
    if (n.any) out.push(`${pad}  <!-- any element may go here (xsd:any) -->`)
    out.push(`${pad}</${tag}>`)
  }

  if (bodyOnly) {
    emit(root, 0, true)
    const body = out.join('\n').replace(`<wd:${root.name}`, `<wd:${root.name} xmlns:wd="${BSVC}"`)
    return { xml: body, variables }
  }
  const head = ['<?xml version="1.0" encoding="UTF-8"?>', `<env:Envelope xmlns:env="${SOAP_ENV}" xmlns:wd="${BSVC}">`]
  if (withHeader) {
    head.push(
      '  <env:Header>',
      '    <wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">',
      '      <wsse:UsernameToken>',
      '        <wsse:Username>{{ISU_USER}}@{{TENANT}}</wsse:Username>',
      '        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{{ISU_PASSWORD}}</wsse:Password>',
      '      </wsse:UsernameToken>',
      '    </wsse:Security>',
      '  </env:Header>',
    )
  }
  head.push('  <env:Body>')
  emit(root, 2, true)
  return { xml: [...head, ...out, '  </env:Body>', '</env:Envelope>'].join('\n'), variables }
}

/** The paths worth reading from a response: its references, down to `depth`. */
export function responseHints(root, depth = 3) {
  const hints = []
  const walk = (n, d) => {
    if (n.isReference) {
      hints.push(`${n.path}/ID[@wd:type='WID']`)
      return
    }
    if (d >= depth) return
    for (const c of n.children) walk(c, d + 1)
  }
  walk(root, 0)
  return hints.slice(0, 25)
}
