// What the commands answer, from the index: an operation's tree, its surroundings (facts only), a service's operations,
// a type, where an element appears, the envelope with every choice it made, and the spec of the Copilot Studio Workday
// connector's «Execute SOAP operation». Port of workday-wws-mcp's workflows.py, without its verdicts (0.2.0).
import { CONNECTOR_SOURCES, curatedNotes, NOTES } from './notes.mjs'
import { buildEnvelope, findPath, LookupError, renderTree, responseHints, TreeBuilder } from './render.mjs'

export const camel = (v) => v.split(/[_\W]+/).filter(Boolean).map((p) => p[0].toUpperCase() + p.slice(1)).join('') || 'Value'

function treeFor(ix, op, service, version, which = 'request', depth = 12) {
  const row = ix.resolve(op, service, version)
  const element = which === 'request' ? row.request_element : row.response_element
  if (!element) return { row, root: null, element: null }
  const reg = ix.registry(row.service, row.version)
  if (!reg || !reg.elements[element]) return { row, root: null, element }
  return { row, root: new TreeBuilder(reg, { maxDepth: depth }).element(element), element }
}

const missingSchema = (row) =>
  `No WSDL ingested for ${row.service} (operation known from the directory only). ` +
  `Run: node scripts/wws.mjs ingest <path/to/${row.service}.wsdl>  ` +
  `(download it from Workday Community, or: node scripts/wws.mjs fetch --services ${row.service} --version ${row.version})`

export function getOperation(ix, op, { service, version, which = 'request', path, depth = 4, requiredOnly = false, fmt = 'text' } = {}) {
  const { row, root } = treeFor(ix, op, service, version, which, Math.max(depth + (path ? (path.match(/\//g) ?? []).length + 2 : 0), 6))
  const summary = ix.operationSummary(row.op, row.service) ?? {}
  const out = {
    operation: row.op, service: row.service, version: row.version,
    description: summary.description ?? '', also_in: summary.also_in ?? [], deprecated: summary.deprecated ?? false,
    request_element: row.request_element, response_element: row.response_element,
  }
  if (NOTES[row.op]) out.notes = curatedNotes(row.op)
  if (!root) {
    out.schema = null
    out.hint = missingSchema(row)
    return out
  }
  const node = path ? findPath(root, path) : root
  out.schema = fmt === 'json' ? node.toDict(depth) : renderTree(node, { maxDepth: depth, requiredOnly })
  return out
}

export function makeEnvelope(ix, op, { service, version, mode = 'required', include = [], withHeader = false, bodyOnly = false, idTypes = {}, choose = [] } = {}) {
  // 'all' on a huge request (Get_Workers) would flood the context: the depth is capped
  let depth = mode === 'required' ? 12 : 6
  if (include.length) depth = Math.max(depth, ...include.map((p) => (p.replace(/^\/+|\/+$/g, '').match(/\//g) ?? []).length + 2))
  const { row, root } = treeFor(ix, op, service, version, 'request', depth)
  if (!root) return { operation: row.op, service: row.service, version: row.version, xml: null, hint: missingSchema(row) }
  const { xml, variables, decisions } = buildEnvelope(root, { operationVersion: row.version, include, mode, withHeader, bodyOnly, idTypes, choose })
  return {
    operation: row.op, service: row.service, version: row.version,
    endpoint: `https://<host>/ccx/service/<tenant>/${row.service}/${row.version}`,
    xml, variables, decisions,
  }
}

/** What the index says about an operation's surroundings — facts, no verdict: the business process its description names
 * (quoted), the operations on the same noun (Add_/End_/Get_…), whether a Get_ for it exists among what is indexed, and
 * the operations that act on business process events, with Workday's own descriptions. The agent decides the chain. */
export function relatedOperations(ix, op, { service, version } = {}) {
  const row = ix.resolve(op, service, version)
  const summary = ix.operationSummary(row.op, row.service) ?? {}
  const description = summary.description ?? ''
  const bp = /Uses the (.+?) business process/i.exec(description)
  const noun = /^[A-Za-z]+?_(.+)$/.exec(row.op)?.[1] ?? row.op
  const sameNoun = ix.related(row.op).map((r) => ({ ...r, description: ix.operationSummary(r.operation, r.service)?.description ?? '' }))
  const indexed = [...new Set(ix.data.operations.map((r) => r.service))]
  const withSchema = Object.values(ix.data.schemas).map((x) => x.service)
  const events = [...new Map(ix.data.operations.filter((r) => /_Business_Process(_Step)?$|^Get_Event_Detail$|^Get_Worker_Event_History$/.test(r.op)).map((r) => [r.op, r])).values()]
    .map((r) => ({ operation: r.op, service: r.service, description: ix.operationSummary(r.op, r.service)?.description ?? '' }))
  const facts = []
  facts.push(bp ? `Workday's description says it uses the «${bp[1]}» business process.` : /business process/i.test(description) ? "Workday's description mentions a business process." : "Workday's description names no business process.")
  if (row.op.split('_')[0] !== 'Get') {
    facts.push(sameNoun.some((r) => r.verb === 'Get')
      ? `A Get_ on the same noun is indexed: ${sameNoun.filter((r) => r.verb === 'Get').map((r) => r.operation).join(', ')}.`
      : `No Get_${noun} (or Get_${noun}s) among the ${indexed.length} services indexed (${withSchema.length} with their WSDL); reading it may need another way (a report, an event's details) — check.`)
  }
  return {
    operation: row.op, service: row.service, version: row.version, description,
    business_process: bp ? bp[1] : null,
    same_noun: sameNoun,
    business_process_events: events,
    facts,
    notes: curatedNotes(row.op),
  }
}

/** Every operation of a service, with Workday's description and whether its WSDL is in. */
export function listOperations(ix, service, { filter } = {}) {
  const rows = ix.data.operations.filter((r) => r.service === service)
  if (!rows.length) throw new LookupError(`No service ${service} indexed; the services: ${[...new Set(ix.data.operations.map((r) => r.service))].sort().join(', ')}`)
  const re = filter ? new RegExp(filter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') : null
  const ops = [...new Map(rows.map((r) => [r.op, r])).keys()].sort()
    .map((o) => ix.operationSummary(o, service))
    .filter((o) => !re || re.test(o.operation) || re.test(o.description))
    .map(({ operation, description, deprecated, schema_versions }) => ({ operation, description, deprecated, schema: schema_versions.length > 0 }))
  return { service, operations: ops }
}

/** A type (complex or simple) as a tree, wherever it is defined among the indexed WSDLs. */
export function getType(ix, name, { service, depth = 3, fmt = 'text' } = {}) {
  const regs = Object.values(ix.data.schemas).filter((x) => !service || x.service === service)
  for (const s of regs) {
    const reg = ix.registry(s.service, s.version)
    if (!reg || !(reg.complex[name] || reg.simple[name])) continue
    const tb = new TreeBuilder(reg, { maxDepth: depth + 2 })
    const root = tb.expand(name, name, name, 1, '1', '', [], 0)
    const defined = regs.filter((x) => { const r = ix.registry(x.service, x.version); return r && (r.complex[name] || r.simple[name]) }).map((x) => x.service)
    return { type: name, service: s.service, version: s.version, also_defined_in: defined.filter((x) => x !== s.service), schema: fmt === 'json' ? root.toDict(depth) : renderTree(root, { maxDepth: depth }) }
  }
  throw new LookupError(`No type ${name} in the indexed WSDLs${service ? ` of ${service}` : ''}`)
}

/** The elements directly inside a complex type (its base's first, for an extension; groups opened). */
function elementsOf(reg, tname, seen = new Set()) {
  const ct = reg.complex[tname]
  if (!ct) return []
  const out = []
  if (ct.base && ct.derivation === 'extension' && reg.complex[ct.base] && !seen.has(ct.base)) out.push(...elementsOf(reg, ct.base, new Set([...seen, ct.base])))
  const walk = (items) => {
    for (const it of items ?? []) {
      if (it.kind === 'element') out.push({ name: it.name, type: it.type ?? (it.ref ? reg.elements[it.ref]?.type : null) ?? null })
      else if (it.kind === 'group') walk(reg.groups[it.ref]?.content)
      else walk(it.items)
    }
  }
  walk(ct.content)
  return out
}

/** Where an element or a type appears: in which operations' request or response, and by which paths (a few). */
export function findElement(ix, name, { service, limit = 40 } = {}) {
  const hits = []
  for (const s of Object.values(ix.data.schemas).filter((x) => !service || x.service === service)) {
    const reg = ix.registry(s.service, s.version)
    if (!reg) continue
    const has = new Map() // does a type hold `name`, at any depth (memoised; a cycle counts as no)
    const holds = (t, stack = new Set()) => {
      if (!t || t.startsWith('xsd:') || !reg.complex[t]) return false
      if (has.has(t)) return has.get(t)
      if (stack.has(t)) return false
      stack.add(t)
      const v = elementsOf(reg, t).some((e) => e.name === name || e.type === name || holds(e.type, stack))
      stack.delete(t)
      has.set(t, v)
      return v
    }
    const pathsTo = (t, prefix, out, stack = new Set()) => {
      for (const e of elementsOf(reg, t)) {
        if (out.length >= 3) return
        const p = `${prefix}/${e.name}`
        if (e.name === name || e.type === name) out.push(p)
        else if (holds(e.type) && !stack.has(e.type)) pathsTo(e.type, p, out, new Set([...stack, e.type]))
      }
    }
    for (const row of ix.data.operations.filter((r) => r.service === s.service && r.version === s.version)) {
      for (const [which, el] of [['request', row.request_element], ['response', row.response_element]]) {
        const t = el && reg.elements[el]?.type
        if (!t || !holds(t)) continue
        const paths = []
        pathsTo(t, el, paths, new Set([t]))
        hits.push({ operation: row.op, service: s.service, in: which, paths })
      }
    }
  }
  return { name, found: hits.length, operations: hits.slice(0, limit), ...(hits.length > limit ? { more: hits.length - limit } : {}) }
}

/** An XML template with {{Var}} as a Power Fx concatenation: free text escaped, dates, booleans and numbers as text. */
export function powerFx(xml, variables, prefix) {
  const byVar = Object.fromEntries(variables.map((v) => [v.var, v]))
  const lit = (s) => '"' + s.replace(/"/g, '""') + '"'
  const parts = []
  let pos = 0
  for (const m of xml.matchAll(/\{\{([A-Za-z0-9_]+)\}\}/g)) {
    if (m.index > pos) parts.push(lit(xml.slice(pos, m.index)))
    let ref = `${prefix}${camel(m[1])}`
    const v = byVar[m[1]] ?? {}
    if (!v.enum?.length && [undefined, null, 'xsd:string'].includes(v.xsd_type) && !v.id_type) ref = `Substitute(Substitute(Substitute(${ref}, "&", "&amp;"), "<", "&lt;"), ">", "&gt;")`
    else if (v.xsd_type === 'xsd:date') ref = `Text(${ref}, "yyyy-mm-dd")`
    else if (v.xsd_type === 'xsd:boolean') ref = `If(${ref}, "true", "false")`
    else if (['xsd:decimal', 'xsd:int', 'xsd:integer', 'xsd:long'].includes(v.xsd_type)) ref = `Text(${ref})`
    parts.push(ref)
    pos = m.index + m[0].length
  }
  if (pos < xml.length) parts.push(lit(xml.slice(pos)))
  return parts.join(' &\n')
}

const INPUT_TYPE = { 'xsd:date': 'Date', 'xsd:boolean': 'Boolean', 'xsd:decimal': 'Number', 'xsd:int': 'Number', 'xsd:integer': 'Number', 'xsd:long': 'Number' }

// The connector's requestBody is the operation's element, without the envelope and without WS-Security: the connection
// authenticates (Microsoft's own ESS Workday templates send the element alone). bodyStyle 'envelope' for the whole one.
export function copilotActionSpec(ix, op, { service, version, include = [], mode = 'required', bodyStyle = 'body', variablePrefix = 'Topic.', idTypes = {}, choose = [] } = {}) {
  const env = makeEnvelope(ix, op, { service, version, mode, include, bodyOnly: bodyStyle === 'body', idTypes, choose })
  const row = ix.resolve(op, service, version)
  const spec = {
    connector: 'Workday (Microsoft, Premium)',
    action: 'Execute SOAP operation',
    operation_id: 'SOAP_Operation',
    parameters: { service: row.service, version: row.version, requestBody: '<see power_fx / xml_template>' },
    operation: row.op,
  }
  const notes = [
    { kind: 'documentation', text: "Identity: self-service and approval run as the signed-in user — a per-user OAuth connection (Microsoft Entra ID Integrated, the one Microsoft's simplified Employee Self-Service setup for Workday uses; or Entra ID Integrated with API Management, 'oauthapim'). With an integration system user (ISU, Basic) Workday sees the ISU as the initiator: routing, the 'self' rules and the no-self-approval rule stop reflecting the real person.", source: CONNECTOR_SOURCES.ess },
    { kind: 'documentation', text: "Access, as the user: the employees' security group needs Get under Integration Permissions (Put, to write — confirm in the tenant) on the domain that governs the data, in Workday's domain security; the API client's scopes do not replace it. An operation that works with an ISU can answer 'Task not authorized' for an employee: find the domain and grant it.", source: CONNECTOR_SOURCES.ess },
    { kind: 'documentation', text: 'Connections are not shareable: each user creates their own.', source: CONNECTOR_SOURCES.connector },
    { kind: 'documentation', text: 'Throttling: 200 calls per connection per 60 s.', source: CONNECTOR_SOURCES.connector },
    { kind: 'documentation', text: "requestBody is the operation's element alone (no SOAP envelope, no WS-Security header: the connection authenticates), as Microsoft's ESS templates send it; confirm once in your environment.", source: CONNECTOR_SOURCES.ess },
    { kind: 'practice', text: "Turn on Secure inputs and Secure outputs on the SOAP action: the run history keeps the responses. Give the agent back only the fields it uses, never the raw XML.", source: 'curated: Power Platform practice — the run history keeps inputs and outputs unless they are secured' },
    ...curatedNotes(row.op),
  ]
  if (env.xml === null) {
    spec.warning = env.hint
    spec.notes = notes
    return spec
  }
  const inputs = env.variables.map((v) => {
    const entry = { name: camel(v.var), copilot_variable: `${variablePrefix}${camel(v.var)}`, xml_path: v.path, type: INPUT_TYPE[v.xsd_type ?? ''] ?? 'String', required: v.required }
    if (v.enum?.length && !v.id_type) entry.allowed_values = v.enum.slice(0, 30)
    if (v.id_type) {
      entry.id_type = v.id_type
      entry.id_type_options = (v.enum ?? []).slice(0, 15)
    }
    if (v.doc) entry.description = [...v.doc].slice(0, 300).join('')
    return entry
  })
  const { root: respRoot, element: respEl } = treeFor(ix, op, row.service, row.version, 'response', 4)
  const response = { element: respEl }
  if (respRoot) {
    response.read_paths = responseHints(respRoot)
    if (response.read_paths.some((p) => p.includes('Event_Reference'))) response.tip = 'Keep the Event_Reference WID: it drives Get_Event_Detail and Approve/Deny/Cancel_Business_Process.'
  }
  return Object.assign(spec, { inputs, xml_template: env.xml, power_fx: powerFx(env.xml, env.variables, variablePrefix), decisions: env.decisions, response, notes })
}

const xmlAttr = (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

/** The operation as a template of Microsoft's Employee Self-Service Workday pack (workdayEntityConfigurationTemplate):
 * a scenario whose apiRequest names the request template, the service and the version, with what to read back as
 * local-name() XPaths; and the request template, the element alone with {Placeholders}. */
export function essTemplate(ix, op, { service, version, include = [], mode = 'required', idTypes = {}, choose = [] } = {}) {
  const env = makeEnvelope(ix, op, { service, version, mode, include, bodyOnly: true, idTypes, choose })
  if (env.xml === null) return { operation: env.operation, service: env.service, version: env.version, xml: null, hint: env.hint }
  const name = `Template_${env.operation}`
  const body = env.xml
    .split('\n')
    .filter((l) => !/^\s*<!--.*-->\s*$/.test(l))
    .map((l) => l.replace(/\s*<!--.*?-->/g, ''))
    .join('\n')
    .replace(/xmlns:wd=/g, 'xmlns:bsvc=')
    .replace(/(<\/?)wd:/g, '$1bsvc:')
    .replace(/ wd:/g, ' bsvc:')
    .replace(/\{\{([A-Za-z0-9_]+)\}\}/g, '{$1}')
  const { root } = treeFor(ix, op, env.service, env.version, 'response', 4)
  const keys = new Set()
  const properties = (root ? responseHints(root) : []).map((p) => {
    const m = /([A-Za-z0-9_]+)\/ID\[@wd:type='([^']+)'\]$/.exec(p)
    let key = `${camel(m[1].replace(/_Reference$/, ''))}${m[2]}`
    for (let n = 2; keys.has(key); n++) key = `${camel(m[1].replace(/_Reference$/, ''))}${m[2]}${n}`
    keys.add(key)
    return { key, extractPath: `//*[local-name()='${m[1]}']/*[local-name()='ID' and @*[local-name()='type']='${m[2]}']/text()` }
  })
  const pad = (n, s) => '  '.repeat(n) + s
  const xml = [
    '<?xml version="1.0" encoding="utf-8" ?>',
    '<workdayEntityConfigurationTemplate>',
    pad(1, `<scenario name="${xmlAttr(env.operation)}">`),
    pad(2, '<apiRequests>'),
    pad(3, '<apiRequest>'),
    pad(4, '<authType>User</authType>'),
    pad(4, '<endpoint>'),
    pad(5, `<request>${name}</request>`),
    pad(5, `<serviceName>${env.service}</serviceName>`),
    pad(5, `<version>${env.version}</version>`),
    pad(4, '</endpoint>'),
    pad(4, '<responseProperties>'),
    ...properties.flatMap((p) => [pad(5, '<property>'), pad(6, `<extractPath>${p.extractPath.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</extractPath>`), pad(6, `<key>${p.key}</key>`), pad(5, '</property>')]),
    pad(4, '</responseProperties>'),
    pad(3, '</apiRequest>'),
    pad(2, '</apiRequests>'),
    pad(1, '</scenario>'),
    pad(1, '<requestTemplates>'),
    pad(2, `<requestTemplate name="${name}">`),
    ...body.split('\n').map((l) => pad(3, l)),
    pad(2, '</requestTemplate>'),
    pad(1, '</requestTemplates>'),
    '</workdayEntityConfigurationTemplate>',
  ].join('\n')
  return { operation: env.operation, service: env.service, version: env.version, placeholders: env.variables.map((v) => v.var), decisions: env.decisions, response_properties: properties, xml }
}
