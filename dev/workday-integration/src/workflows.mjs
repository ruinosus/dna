// What the commands answer: an operation's tree, its envelope, a use case traced to the chain of operations, and the
// spec of the Copilot Studio Workday connector's «Execute SOAP operation». Port of workday-wws-mcp's workflows.py.
import { NOTES } from './notes.mjs'
import { buildEnvelope, findPath, renderTree, responseHints, TreeBuilder } from './render.mjs'

// the business process's lifecycle (all in the Integrations service)
export const BP_LIFECYCLE = [
  ['track', 'Get_Event_Detail', "Status of the event: step, who it's awaiting, state."],
  ['approve', 'Approve_Business_Process', 'Approver acts on the event WID (runs as the approver).'],
  ['deny', 'Deny_Business_Process', 'Approver denies.'],
  ['send_back', 'Send_Back_Business_Process', 'Approver returns it to a completed step.'],
  ['cancel', 'Cancel_Business_Process', 'Initiator cancels while in progress.'],
  ['rescind', 'Rescind_Business_Process', 'Undo a completed event, if rescindable.'],
  ['reassign', 'Reassign_Business_Process_Step', 'Move a step to another qualified user.'],
]

// the Microsoft Workday connector's own (REST, Preview) actions that fill the SOAP's gaps
export const CONNECTOR_NATIVE = {
  me: ['GetWorkerMe', 'Get my worker profile (Preview)', "Resolve the signed-in user's worker ID; needs an OAuth-based connection."],
  inbox: ['GetWorkerInboxTasks', 'Get worker inbox tasks (Preview)', "List pending inbox tasks for a worker (e.g. approvals) — there is no SOAP 'Get Inbox'."],
  reports: ['GetWorkerDirectReports', 'Get worker direct reports (Preview)', 'Who the manager can approve for (advisees).'],
  search: ['SearchWorkers', 'Search workers (Preview)', 'Find a worker by name.'],
}

const BP_VERBS = ['Add', 'Request', 'Change', 'Submit', 'End', 'Terminate', 'Hire', 'Enter', 'Assign', 'Start', 'Edit', 'Manage', 'Create', 'Close', 'Contract']

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
  if (NOTES[row.op]) out.notes = NOTES[row.op]
  if (!root) {
    out.schema = null
    out.hint = missingSchema(row)
    return out
  }
  const node = path ? findPath(root, path) : root
  out.schema = fmt === 'json' ? node.toDict(depth) : renderTree(node, { maxDepth: depth, requiredOnly })
  return out
}

export function makeEnvelope(ix, op, { service, version, mode = 'required', include = [], withHeader = false, bodyOnly = false } = {}) {
  // 'all' on a huge request (Get_Workers) would flood the context: the depth is capped
  let depth = mode === 'required' ? 12 : 6
  if (include.length) depth = Math.max(depth, ...include.map((p) => (p.replace(/^\/+|\/+$/g, '').match(/\//g) ?? []).length + 2))
  const { row, root } = treeFor(ix, op, service, version, 'request', depth)
  if (!root) return { operation: row.op, service: row.service, version: row.version, xml: null, hint: missingSchema(row) }
  const { xml, variables } = buildEnvelope(root, { operationVersion: row.version, include, mode, withHeader, bodyOnly })
  return {
    operation: row.op, service: row.service, version: row.version,
    endpoint: `https://<host>/ccx/service/<tenant>/${row.service}/${row.version}`,
    xml, variables,
  }
}

const exists = (ix, op) => {
  const r = ix.data.operations.find((x) => x.op === op)
  return r ? ix.operationSummary(op, r.service) : null
}

export function traceUseCase(ix, goal, { scope = 'hr', limit = 6 } = {}) {
  const hits = ix.search(goal, { scope, limit })
  if (!hits.length) return { goal, steps: [], hint: "No matches. Try English Workday terms (e.g. 'time off', 'job change') or scope='all'." }
  const primary = hits[0]
  const op = primary.operation
  const verb = op.split('_')[0]
  const isBp = primary.description.toLowerCase().includes('business process') || BP_VERBS.includes(verb)
  const steps = [
    { role: 'identify_user', kind: 'connector', action: CONNECTOR_NATIVE.me[1], operation_id: CONNECTOR_NATIVE.me[0], why: CONNECTOR_NATIVE.me[2] },
    { role: 'action', kind: 'soap', operation: op, service: primary.service, why: primary.description },
  ]
  if (isBp) {
    steps.push({ role: 'approver_inbox', kind: 'connector', action: CONNECTOR_NATIVE.inbox[1], operation_id: CONNECTOR_NATIVE.inbox[0], why: CONNECTOR_NATIVE.inbox[2] })
    for (const [role, name, why] of BP_LIFECYCLE) {
      const s = exists(ix, name)
      if (s) steps.push({ role, kind: 'soap', operation: name, service: s.service, why })
    }
    const hist = exists(ix, 'Get_Worker_Event_History')
    if (hist) steps.push({ role: 'find_events', kind: 'soap', operation: 'Get_Worker_Event_History', service: hist.service, why: "Find a worker's events (filter by event type and dates) to get event WIDs." })
  }
  const related = ix.related(op)
  const notes = [...(NOTES[op] ?? [])]
  if (!related.some((r) => r.verb === 'Get') && verb !== 'Get') {
    notes.push(`No Get_ counterpart found for '${op.split('_').slice(1).join('_') || op}': plan reads via a RaaS custom report (connector action 'Execute RaaS operation').`)
  }
  return { goal, primary, business_process: isBp, steps, related, alternatives: hits.slice(1), notes }
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
export function copilotActionSpec(ix, op, { service, version, include = [], mode = 'required', bodyStyle = 'body', variablePrefix = 'Topic.' } = {}) {
  const env = makeEnvelope(ix, op, { service, version, mode, include, bodyOnly: bodyStyle === 'body' })
  const row = ix.resolve(op, service, version)
  const spec = {
    connector: 'Workday (Microsoft, Premium)',
    action: 'Execute SOAP operation',
    operation_id: 'SOAP_Operation',
    parameters: { service: row.service, version: row.version, requestBody: '<see power_fx / xml_template>' },
    operation: row.op,
  }
  const notes = [
    "Identity: self-service and approval run as the signed-in user — a per-user OAuth connection (Microsoft Entra ID Integrated, the one Microsoft's simplified Employee Self-Service setup for Workday uses; or Entra ID Integrated with API Management, 'oauthapim'). With an integration system user (ISU, Basic) Workday sees the ISU as the initiator: routing, the 'self' rules and the no-self-approval rule stop reflecting the real person.",
    "Access, as the user: the employees' security group needs Get (or Put, to write) under Integration Permissions on the domain that governs the data, in Workday's domain security; the API client's scopes do not replace it. An operation that works with an ISU can answer 'Task not authorized' for an employee: find the domain and grant it.",
    'Connections are not shareable: each user creates their own.',
    'Throttling: 200 calls per connection per 60 s.',
    "requestBody is the operation's element alone (no SOAP envelope, no WS-Security header: the connection authenticates), as Microsoft's ESS templates send it; confirm once in your environment.",
    "Turn on Secure inputs and Secure outputs on the SOAP action: the run history keeps the responses. Give the agent back only the fields it uses, never the raw XML.",
    ...(NOTES[row.op] ?? []),
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
  return Object.assign(spec, { inputs, xml_template: env.xml, power_fx: powerFx(env.xml, env.variables, variablePrefix), response, notes })
}

const xmlAttr = (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

/** The operation as a template of Microsoft's Employee Self-Service Workday pack (workdayEntityConfigurationTemplate):
 * a scenario whose apiRequest names the request template, the service and the version, with what to read back as
 * local-name() XPaths; and the request template, the element alone with {Placeholders}. */
export function essTemplate(ix, op, { service, version, include = [], mode = 'required' } = {}) {
  const env = makeEnvelope(ix, op, { service, version, mode, include, bodyOnly: true })
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
  return { operation: env.operation, service: env.service, version: env.version, placeholders: env.variables.map((v) => v.var), response_properties: properties, xml }
}
