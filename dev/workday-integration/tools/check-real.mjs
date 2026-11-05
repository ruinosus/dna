// Checks against an index of Workday's real WSDLs (the repository has only synthetic ones) the curated notes and the
// size of the answers an agent reads. The notes:
// each «schema» note's evidence is a name the WSDLs have (an element, a type, an attribute, an enumeration value or an
// operation), each operation it says is absent is absent, and no field of the request is named after what it says the
// request lacks; each «description» note's quote is in Workday's description of the operation. Every note has a kind.
//
// The sizes: each answer of a few operations, as compact JSON (what the MCP sends), within MAX — an MCP client may cut a
// long answer (VS Code's cut the 0.2.2 spec, 11 KB indented).
//
//   node dev/workday-integration/tools/check-real.mjs [--index <folder>]   (the default index otherwise)
import { defaultIndexDir, Index } from '../src/index.mjs'
import { CONNECTOR_ACTIONS } from '../src/connector.mjs'
import { NOTES } from '../src/notes.mjs'
import { TreeBuilder } from '../src/render.mjs'
import { copilotActionSpec, essTemplate, getOperation, getRestEndpoint, makeEnvelope, relatedOperations, restActionSpec } from '../src/workflows.mjs'

const at = process.argv.indexOf('--index')
const ix = new Index(at > 0 ? process.argv[at + 1] : defaultIndexDir())
if (ix.empty) {
  console.error(`✗ nothing indexed in ${ix.dir}: fetch or ingest Workday's WSDLs first`)
  process.exit(2)
}
const names = new Set(ix.data.operations.map((r) => r.op))
const services = Object.values(ix.data.schemas)
for (const s of services) {
  const reg = ix.registry(s.service, s.version)
  for (const k of ['elements', 'complex', 'simple', 'attributes', 'groups']) for (const n of Object.keys(reg[k])) names.add(n)
  for (const st of Object.values(reg.simple)) for (const v of st.enum ?? []) names.add(v)
  const walk = (items) => {
    for (const it of items ?? []) {
      if (it.kind === 'element' && it.name) names.add(it.name)
      walk(it.items)
    }
  }
  for (const ct of Object.values(reg.complex)) {
    walk(ct.content)
    for (const a of ct.attrs ?? []) if (a.name) names.add(a.name)
  }
}
const KINDS = new Set(['schema', 'description', 'inferred', 'sensitive', 'tenant'])
let bad = 0
let checked = 0
for (const [op, notes] of Object.entries(NOTES)) {
  for (const n of notes) {
    const off = []
    if (!KINDS.has(n.kind)) off.push(`kind ${n.kind}`)
    for (const e of n.evidence ?? []) if (!names.has(e)) off.push(`${e} is not in the WSDLs`)
    for (const a of n.absent ?? []) if (ix.data.operations.some((r) => r.op === a)) off.push(`${a} exists`)
    if (n.absentFields) {
      const row = ix.data.operations.find((r) => r.op === op && r.request_element)
      const reg = row && ix.registry(row.service, row.version)
      if (!reg) off.push(`${op}'s WSDL is not indexed`)
      else {
        const stack = [new TreeBuilder(reg).element(row.request_element)]
        while (stack.length) {
          const x = stack.pop()
          for (const f of n.absentFields) if (x.name.includes(f)) off.push(`${x.path} is named after ${f}`)
          stack.push(...x.children)
        }
      }
    }
    if (n.kind === 'schema' && !n.evidence && !n.absent && !n.absentFields) off.push('a schema note with nothing to check it by')
    if (n.kind === 'description') {
      const desc = ix.data.operations.filter((r) => r.op === op).map((r) => r.description).join(' ')
      if (!n.quote) off.push('a description note with no quote')
      else if (!desc.includes(n.quote)) off.push(`Workday's description does not say «${n.quote}»`)
    }
    checked++
    if (off.length) {
      bad++
      console.log(`✗ ${op}: «${n.text.slice(0, 80)}» — ${off.join('; ')}`)
    }
  }
}
console.log(`${bad ? '✗' : '✓'} ${checked - bad}/${checked} notes hold against ${ix.dir} (${services.length} WSDLs)`)

const MAX = 9000
const OPS = ['Add_Flexible_Work_Arrangement', 'End_Flexible_Work_Arrangement', 'Approve_Business_Process', 'Get_Workers', 'Get_Event_Detail', 'Hire_Employee', 'Change_Job']
const ANSWERS = { copilot: copilotActionSpec, ess: essTemplate, envelope: makeEnvelope, related: relatedOperations, show: getOperation, 'show --json': (i, o) => getOperation(i, o, { fmt: 'json' }) }
let big = 0
let largest = ['', 0]
for (const op of OPS.filter((o) => ix.data.operations.some((r) => r.op === o && r.request_element))) {
  for (const [name, fn] of Object.entries(ANSWERS)) {
    const n = JSON.stringify(fn(ix, op)).length
    if (n > largest[1]) largest = [`${name} ${op}`, n]
    if (n > MAX) {
      big++
      console.log(`✗ ${name} ${op}: ${n} characters (more than ${MAX})`)
    }
  }
}
console.log(`${big ? '✗' : '✓'} every answer of ${OPS.length} operations within ${MAX / 1000} KB (the largest: ${largest[0]}, ${(largest[1] / 1000).toFixed(1)} KB)`)

// REST: a known endpoint says its domains and scope; the REST answers fit too
let restBad = 0
if (ix.data.rest.endpoints.length) {
  const tp = getRestEndpoint(ix, 'GET', '/workers/{ID}/timeOffPlans/{subresourceID}', { service: 'common' })
  const ok = tp.domains.includes('Self-Service: Time Off Balances') && tp.scope.includes('Time Off and Leave') && tp.params[0].accepts?.named.includes('me')
  if (!ok) restBad++
  console.log(`${ok ? '✓' : '✗'} REST: GET common/v1 /workers/{ID}/timeOffPlans/{subresourceID} — its domains, its scope, an ID that accepts me`)
  const ENDS = [['GET', '/workers/{ID}/timeOffPlans', 'common'], ['GET', '/workers/{ID}/inboxTasks', 'common'], ['GET', '/events', 'businessProcess'], ['POST', '/workers/{ID}/organizationAssignmentChanges', 'staffing'], ['GET', '/workers/{ID}', 'common']]
  let lr = ['', 0]
  for (const [m, p, svc] of ENDS) {
    if (!ix.data.rest.endpoints.some((e) => e.method === m && e.path === p && e.service === svc)) continue
    for (const [name, fn] of [['rest', () => getRestEndpoint(ix, m, p, { service: svc })], ['rest --json', () => getRestEndpoint(ix, m, p, { service: svc, fmt: 'json' })], ['copilot-rest', () => restActionSpec(ix, m, p, { service: svc })]]) {
      const n = JSON.stringify(fn()).length
      if (n > lr[1]) lr = [`${name} ${m} ${p}`, n]
      if (n > MAX) {
        restBad++
        console.log(`✗ ${name} ${m} ${p}: ${n} characters (more than ${MAX})`)
      }
    }
  }
  // the inbox, as the VS Code test asks it (0.3.1): read takes the paths rest shows; paging is a decision, include adds it
  if (ix.data.rest.endpoints.some((e) => e.service === 'common' && e.path === '/workers/{ID}/inboxTasks')) {
    const shownPaths = JSON.stringify(getRestEndpoint(ix, 'GET', '/workers/{ID}/inboxTasks', { service: 'common', fmt: 'json' })).match(/data\[\]\.due/g) ?? []
    const plain = restActionSpec(ix, 'GET', '/workers/{ID}/inboxTasks', { service: 'common', idForms: { ID: 'me' }, read: ['data[].descriptor', 'data.status.descriptor'] })
    const paged = restActionSpec(ix, 'GET', '/workers/{ID}/inboxTasks', { service: 'common', idForms: { ID: 'me' }, include: ['limit', 'offset'] })
    const pg = plain.decisions.find((d) => d.kind === 'optional_query')
    const inboxOk = shownPaths.length > 0 && plain.response.reads.every((r) => r.repeats && r.json_path.startsWith('data[]')) && pg?.left_out.some((q) => q.name === 'limit' && /maximum is 100/i.test(q.description)) && pg.left_out.some((q) => q.name === 'offset') && paged.parameters.relativePath === 'common/v1/{tenant}/workers/me/inboxTasks?limit={{Limit}}&offset={{Offset}}'
    if (!inboxOk) restBad++
    console.log(`${inboxOk ? '✓' : '✗'} REST: the inbox as the VS Code test asks it — read with the paths rest shows, paging (limit at most 100, offset) a decision, include adds it`)
  }
  // the endpoints the connector's ready-made actions likely call (inferred notes) are in the index, by service and path
  const missing = CONNECTOR_ACTIONS.flatMap((x) => (x.notes ?? []).filter((n) => n.endpoint)).map((n) => n.endpoint).filter((ep) => {
    const [m, sv, p] = ep.split(' ')
    return !ix.data.rest.endpoints.some((e) => e.method === m && `${e.service}/` === sv.replace(/v\d+$/, '') && e.path === p)
  })
  if (missing.length) restBad++
  console.log(`${missing.length ? '✗' : '✓'} connector: the endpoints its ready-made actions likely call are in the index${missing.length ? ` — not: ${missing.join('; ')}` : ''}`)
  console.log(`${restBad ? '✗' : '✓'} REST answers within ${MAX / 1000} KB (the largest: ${lr[0]}, ${(lr[1] / 1000).toFixed(1)} KB)`)
} else console.log('• no REST indexed (fetch --rest): its checks skipped')
process.exit(bad || big || restBad ? 1 : 0)
