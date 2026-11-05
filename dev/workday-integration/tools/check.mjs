// Checks workday-integration on the synthetic examples: the parser, the trees, the envelopes, the search and the
// Copilot Studio spec (the Python port's tests, ported), the same answers as the Python port on the same files
// (checks/golden.json), the CLI (no index, errors, --json), no network outside `fetch`, the notes, and the skill.
import { spawnSync } from 'node:child_process'
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { Index, parseDirectory } from '../src/index.mjs'
import { NOTES } from '../src/notes.mjs'
import { buildEnvelope, findPath, LookupError, TreeBuilder } from '../src/render.mjs'
import { parseWsdl, parseXml, registryOf } from '../src/schema.mjs'
import { copilotActionSpec, essTemplate, getOperation, makeEnvelope, traceUseCase } from '../src/workflows.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const repo = join(here, '../../..')
const plugin = join(repo, 'plugins/workday-integration')
const skill = join(plugin, 'skills/workday-integration')
const ex = join(skill, 'examples')
const HR = join(ex, 'Human_Resources/v47.0/Human_Resources.wsdl')
const INT = join(ex, 'Integrations/v47.0/Integrations.wsdl')
const work = mkdtempSync(join(tmpdir(), 'wws-check-'))
let failed = 0
const ok = (cond, what, detail = '') => {
  console.log(`${cond ? '✓' : '✗'} ${what}`)
  if (!cond) {
    failed++
    if (detail) console.log(String(detail).slice(0, 1500))
  }
}
const throws = (fn, re) => {
  try {
    fn()
    return false
  } catch (e) {
    return re.test(e.message)
  }
}

// ---------- the directory and the parser ----------
{
  const { version, entries } = parseDirectory(readFileSync(join(ex, 'operation-directory-sample.txt'), 'utf8'))
  const by = Object.fromEntries(entries.map((e) => [e.op, e]))
  ok(version === 'v47.0' && entries.length === 15, `the directory: v47.0, ${entries.length} operations`)
  ok(JSON.stringify(by.Change_Preferred_Name.services) === '["Human_Resources","Staffing"]', 'an operation in two services lists both')
  ok(by.Submit_Expense_Sheet.deprecated === true, 'DEPRECATED is read off the name')
}
{
  const hr = parseWsdl(HR)
  ok(hr.service === 'Human_Resources' && hr.version === 'v47.0', 'the service and the version from the WSDL and its folder')
  ok(hr.operations.Add_Flexible_Work_Arrangement.request_element === 'Add_Flexible_Work_Arrangement_Request', 'an operation and its request element (schema inline)')
  ok(hr.operations.Get_Worker_Event_History.request_element === 'Worker_Event_History_Get', 'a request element not named _Request')
  const int = parseWsdl(INT)
  ok(int.operations.Approve_Business_Process.request_element === 'Approve_Business_Process_Request', 'the schema imported from an .xsd, with other prefixes')
  const root = new TreeBuilder(registryOf(int)).element('Approve_Business_Process_Request')
  ok(JSON.stringify(root.children.map((c) => c.name)) === '["Event_Reference","Comment_Data"]' && root.children[0].isReference, 'its tree, with a reference')
  ok(throws(() => parseXml('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>', 'evil.wsdl'), /DOCTYPE/), 'a DOCTYPE (entities) is refused')
}
{
  const tb = new TreeBuilder(registryOf(parseWsdl(HR)))
  const root = tb.element('Add_Flexible_Work_Arrangement_Request')
  ok(root.attrs.some((a) => a.name === 'version'), 'the root carries @version')
  const data = findPath(root, 'Arrangement_Data')
  const worker = findPath(data, 'Worker_Reference')
  ok(worker.isReference && worker.required, 'a required reference')
  ok(JSON.stringify(worker.children[0].attrs[0].enum) === '["WID","Employee_ID","Contingent_Worker_ID"]', 'the @type options of its ID')
  ok(JSON.stringify(data.children.filter((c) => c.choice).map((c) => c.name).sort()) === '["Job_Reference","Position_Reference"]', 'the members of a choice')
  const days = findPath(data, 'Weekdays')
  ok(days.card === '*' && days.enum.includes('Friday'), 'a repeated enumeration')
  const filter = findPath(tb.element('Get_Organizations_Request'), 'Filter')
  ok(JSON.stringify(filter.children.map((c) => c.name)) === '["Also_Inactive","Organization_Kind"]', "an extension: the base type's content first")
  ok(findPath(tb.element('Get_Organizations_Response'), 'Organization/Parent_Organization').recursive, 'a recursion is marked, not expanded')
  ok(throws(() => findPath(root, 'Nope'), /'Nope' not under .*Children: Business_Process_Parameters, Arrangement_Data/), 'a path that is not there names the children')
}

// ---------- the envelope ----------
const fill = (xml) => parseXml(xml.replace(/\{\{/g, 'X').replace(/\}\}/g, 'X'), 'envelope')
const find = (node, local) => {
  if (typeof node === 'string') return null
  if (node.local === local) return node
  for (const c of node.children) {
    const f = find(c, local)
    if (f) return f
  }
  return null
}
{
  const root = new TreeBuilder(registryOf(parseWsdl(HR))).element('Add_Flexible_Work_Arrangement_Request')
  const { xml, variables } = buildEnvelope(root, { operationVersion: 'v47.0' })
  const doc = fill(xml)
  ok(find(doc, 'Add_Flexible_Work_Arrangement_Request').attrs['wd:version'] === 'v47.0', 'the envelope: the request with wd:version')
  ok(!find(doc, 'Planned_Last_Day') && !find(doc, 'Business_Process_Parameters'), 'only what is required')
  ok(find(find(doc, 'Worker_Reference'), 'ID').attrs['wd:type'] === 'Employee_ID', 'a reference with its chosen @type')
  const names = new Set(variables.map((v) => v.var))
  ok(['Worker_ID', 'First_Day', 'Arrangement_Kind_ID'].every((n) => names.has(n)), 'its variables')
  const more = buildEnvelope(root, { operationVersion: 'v47.0', include: ['Business_Process_Parameters/Run_Now', 'Arrangement_Data/Planned_Last_Day'], withHeader: true })
  const d2 = fill(more.xml)
  ok(find(find(d2, 'Business_Process_Parameters'), 'Run_Now') && find(d2, 'Planned_Last_Day') && more.xml.includes('wsse:Security'), '--include brings an optional field and its parents; --wsse the header')
  const body = buildEnvelope(new TreeBuilder(registryOf(parseWsdl(INT))).element('Approve_Business_Process_Request'), { operationVersion: 'v47.0', bodyOnly: true })
  ok(fill(body.xml).local === 'Approve_Business_Process_Request' && body.variables[0].id_type === 'WID', '--body-only: the element alone, standalone XML; an event goes by WID')
}

// ---------- the index, the search, trace, show, copilot ----------
const ix = new Index(join(work, 'index'))
ix.ingestDirectory(readFileSync(join(ex, 'operation-directory-sample.txt'), 'utf8'))
for (const f of [HR, INT]) ix.ingestSchema(parseWsdl(f), f)
{
  const top = (q, opts) => ix.search(q, { limit: 3, ...opts }).map((r) => r.operation)
  for (const [q, want] of [
    ['quero aprovar o home office do meu advisee', 'Flexible_Work_Arrangement'],
    ['encerrar trabalho remoto', 'End_Flexible_Work_Arrangement'],
    ['saldo de férias', 'Get_Time_Off_Plan_Balances'],
    ['Approve_Business_Process', 'Approve_Business_Process'],
    ['histórico de eventos do colaborador', 'Get_Worker_Event_History'],
  ]) ok(top(q).some((o) => o.includes(want)), `search «${q}» → ${want}`, top(q).join(', '))
  ok(!ix.search('journals').length && top('journals', { scope: 'all' })[0] === 'Get_Journals', 'the HR scope by default; --scope all for the rest')
  ok(!ix.search('expense sheet', { scope: 'all' }).length && ix.search('expense sheet', { scope: 'all', includeDeprecated: true }).length, 'a deprecated operation is left out')
  const none = getOperation(ix, 'Enter_Time_Off')
  ok(none.schema === null && /node scripts\/wws\.mjs ingest/.test(none.hint), 'known from the directory only: the hint says what to ingest')
  ok(throws(() => ix.resolve('Add_Flexible_Work'), /not found/), 'an operation that is not there')
  const t = traceUseCase(ix, 'colaborador solicita trabalho híbrido e o gestor aprova')
  const roles = Object.fromEntries(t.steps.map((s) => [s.role, s]))
  ok(t.primary.operation === 'Add_Flexible_Work_Arrangement' && roles.approve.operation === 'Approve_Business_Process' && roles.approver_inbox.operation_id === 'GetWorkerInboxTasks', 'trace: the operation, the approver\'s inbox and the approval')
  ok(roles.track?.operation === 'Get_Event_Detail', 'trace: the event tracked by Get_Event_Detail (its request element is Get_Event_Details_Request)')
  ok(t.related.some((r) => r.operation === 'End_Flexible_Work_Arrangement') && t.notes.some((n) => n.includes('RaaS')), 'trace: the related operations, and no Get_ → RaaS')
  const spec = copilotActionSpec(ix, 'Add_Flexible_Work_Arrangement', { include: ['Arrangement_Data/Note'] })
  const inputs = Object.fromEntries(spec.inputs.map((i) => [i.name, i]))
  ok(spec.operation_id === 'SOAP_Operation' && JSON.stringify(spec.parameters) === '{"service":"Human_Resources","version":"v47.0","requestBody":"<see power_fx / xml_template>"}', 'copilot: Execute SOAP operation, its service and version')
  ok(inputs.WorkerID.id_type === 'Employee_ID' && inputs.FirstDay.type === 'Date', 'copilot: typed inputs')
  ok(spec.power_fx.includes('Text(Topic.FirstDay, "yyyy-mm-dd")') && spec.power_fx.includes('Substitute(Substitute(Substitute(Topic.Note') && spec.power_fx.includes('version=""v47.0""'), 'copilot: Power Fx — dates as text, free text escaped, quotes doubled')
  ok(spec.notes.some((n) => /signed-in user/.test(n) && /Entra ID Integrated/.test(n)) && spec.notes.some((n) => /Integration Permissions/.test(n) && /Task not authorized/.test(n)) && spec.notes.some((n) => /200 calls/.test(n)) && spec.notes.some((n) => /Secure inputs and Secure outputs/.test(n)) && spec.response.read_paths.length, 'copilot: the identity as the signed-in user, the domain security, the limit, Secure inputs/outputs, what to read back')
  ok(!/<env:Envelope|wsse:/.test(spec.xml_template) && /^<wd:Add_Flexible_Work_Arrangement_Request xmlns:wd=/.test(spec.xml_template), 'copilot: requestBody is the element alone by default (no envelope, no WS-Security)')
  ok(/<env:Envelope/.test(copilotActionSpec(ix, 'Add_Flexible_Work_Arrangement', { bodyStyle: 'envelope' }).xml_template), 'copilot --envelope: the whole envelope, when asked')
  const nospec = copilotActionSpec(ix, 'Enter_Time_Off')
  ok(nospec.parameters.service === 'Absence_Management' && nospec.warning, 'copilot without a WSDL: a warning, not a guess')
  ok(throws(() => getOperation(ix, 'Add_Flexible_Work_Arrangement', { path: 'Nope' }), /not under/) && LookupError, 'show --path that is not there')
}

// ---------- the same answers as the Python port (checks/golden.json) ----------
{
  const golden = JSON.parse(readFileSync(join(here, '../checks/golden.json'), 'utf8'))
  // notes are rewritten here and hints name this CLI: left out of the comparison
  // and a choice's comment now names its alternatives (it said «alternatives exist»): those comment lines too
  const noChoice = (v) => (typeof v === 'string' ? v.split('\n').filter((l) => !/^\s*<!-- (choice |one of )/.test(l)).join('\n').replace(/<!-- (choice |one of )[^>]*-->\n?/g, '') : v)
  const strip = (o) => (Array.isArray(o) ? o.map(strip) : o && typeof o === 'object' ? Object.fromEntries(Object.entries(o).filter(([k]) => !['notes', 'score', 'hint', 'warning'].includes(k)).map(([k, v]) => [k, strip(v)])) : noChoice(o))
  const run = (c) => {
    const a = c.args
    try {
      if (c.cmd === 'search') return ix.search(a.query, { scope: a.scope, limit: 10 })
      if (c.cmd === 'show') return getOperation(ix, a.operation, { which: a.which, path: a.path, depth: a.depth, fmt: a.fmt })
      if (c.cmd === 'envelope') return makeEnvelope(ix, a.operation, { include: a.include, mode: a.mode, withHeader: a.with_header, bodyOnly: a.body_only })
      if (c.cmd === 'trace') return traceUseCase(ix, a.goal)
      if (c.cmd === 'copilot') return copilotActionSpec(ix, a.operation, { include: a.include, bodyStyle: a.body_style ?? 'envelope' })
    } catch (e) {
      if (e instanceof LookupError) return { error: e.message }
      throw e
    }
  }
  const off = []
  for (const c of golden.cases) {
    const got = JSON.parse(JSON.stringify(run(c)))
    // search: the same operations with the same bm25 scores; equal scores may come in any order (the Python's did)
    const same = c.cmd === 'search'
      ? JSON.stringify(c.out.map((r, i) => [c.scores[i], JSON.stringify(strip(r))]).sort()) === JSON.stringify(got.map((r) => [r.score, JSON.stringify(strip(r))]).sort())
      : JSON.stringify(strip(c.out)) === JSON.stringify(strip(got))
    if (!same) off.push(`${c.cmd} ${JSON.stringify(c.args)}`)
  }
  ok(!off.length, `the same answers as the Python port on the examples (${golden.cases.length - off.length}/${golden.cases.length}: search with its bm25 scores, show, envelope, trace, copilot)`, off.join('\n'))
}

// ---------- the notes ----------
{
  const all = Object.values(NOTES).flat().join('\n')
  ok(!/Staffing functional area security|self-approval is blocked by BP security|Approval routing follows the supervisory organization/.test(all) && /To confirm in the tenant/.test(all), 'the notes the schema does not show are marked «to confirm in the tenant»')
  ok(['Get_Workers', 'Get_Worker_Event_History', 'Get_Event_Detail'].every((op) => NOTES[op].some((n) => n.startsWith('Sensitive:'))), 'what may come back about a person is said (Sensitive:)')
}

// ---------- the CLI (the bundled scripts/wws.mjs): no index, errors, --json, no network ----------
{
  const wws = join(skill, 'scripts/wws.mjs')
  // a preload that makes any network use fail loudly: only `fetch` (the command) may go out
  const guard = join(work, 'no-network.mjs')
  writeFileSync(guard, "globalThis.fetch = () => { throw new Error('NETWORK') }\n")
  const cli = (...args) => spawnSync(process.execPath, ['--import', guard, wws, ...args], { encoding: 'utf8' })
  const idx = join(work, 'cli-index')
  const empty = cli('search', 'férias', '--index', idx)
  ok(empty.status === 2 && /nothing indexed .* Run: node scripts\/wws\.mjs ingest/.test(empty.stderr), 'no index: it says what to run, and exits 2', empty.stderr)
  const ing = cli('ingest', ex, '--index', idx)
  ok(ing.status === 0 && /indexed 15 operations from the directory, 10 with schemas/.test(ing.stdout), 'ingest a folder: the directory and the WSDLs', ing.stdout + ing.stderr)
  const steps = [['status'], ['search', 'aprovar home office'], ['trace', 'colaborador solicita trabalho híbrido e o gestor aprova'], ['show', 'Add_Flexible_Work_Arrangement', '--path', 'Arrangement_Data'], ['envelope', 'Approve_Business_Process', '--body-only'], ['copilot', 'Approve_Business_Process']]
  const outs = steps.map((s) => cli(...s, '--json', '--index', idx))
  ok(outs.every((o) => o.status === 0 && JSON.parse(o.stdout) && !/NETWORK/.test(o.stderr)), 'status, search, trace, show, envelope, copilot: --json, and no network', outs.map((o) => o.stderr).join('\n'))
  ok(JSON.parse(outs[5].stdout).parameters.service === 'Integrations', 'copilot by the CLI: the service of the operation')
  const bad = cli('show', 'Nope_Operation', '--index', idx)
  ok(bad.status === 2 && /not found/.test(bad.stderr), 'an operation that is not there: exit 2', bad.stderr)
  const nos = cli('envelope', 'Enter_Time_Off', '--index', idx)
  ok(nos.status === 3 && /No WSDL ingested for Absence_Management/.test(nos.stdout), 'no WSDL for its service: exit 3, with what to ingest', nos.stdout)
  const code = readFileSync(wws, 'utf8')
  ok(!/from ["']node:(http|https|net|tls|dgram)["']|require\(["'](http|https|net)/.test(code) && (code.match(/\bfetch\(/g) ?? []).length === 1, 'the bundle: no http/net module, one fetch (the fetch command)')
}

// ---------- the Operation Directory page, fetch (with a fake network), xsd:any, a choice, the ESS template ----------
{
  // a synthetic page in the shape of Workday Community's Operation Directory
  const row = (op, desc, svcs, dep = false) => `<tr><td><a class="link" href="../${svcs[0]}/v47.0/${op}.html">${op}</a>${dep ? '<span class="deprecated"> DEPRECATED</span>' : ''}</td><td>${desc}&nbsp;</td><td>${svcs.map((x) => `<a class="link" href="../${x}/v47.0/${x}.html">${x}</a><br />`).join('')}</td></tr>`
  const html = `<html><body><h3 class="ws-title">Operation Directory: (v47.0 / 2026R2)</h3><table class="typetable"><thead><tr><th>Operation</th><th>Description</th><th>Web Service(s)</th></tr></thead><tbody>
${row('Add_Flexible_Work_Arrangement', 'Starts a ~flexible work~ arrangement &amp; its\n   business process.', ['Human_Resources'])}
${row('Change_Preferred_Name', 'Changes the name a person goes by.', ['Human_Resources', 'Staffing'])}
${row('Submit_Expense_Sheet', 'Sends an expense sheet.', ['Resource_Management'], true)}
</tbody></table></body></html>`
  const { version, entries } = parseDirectory(html)
  const by = Object.fromEntries(entries.map((e) => [e.op, e]))
  ok(version === 'v47.0' && entries.length === 3 && by.Add_Flexible_Work_Arrangement.description === 'Starts a flexible work arrangement & its business process.', 'the Operation Directory page (HTML): the version, each row, its text without markup')
  ok(JSON.stringify(by.Change_Preferred_Name.services) === '["Human_Resources","Staffing"]' && by.Submit_Expense_Sheet.deprecated, 'the page: an operation in two services, and DEPRECATED')

  // fetch, with the network answered by a preload: what it asks for, and that it indexes it
  const served = join(work, 'served.json')
  writeFileSync(served, JSON.stringify({ html, hr: readFileSync(HR, 'utf8') }))
  const fake = join(work, 'fake-network.mjs')
  writeFileSync(fake, `import { readFileSync, appendFileSync } from 'node:fs'
const s = JSON.parse(readFileSync(${JSON.stringify(served)}, 'utf8'))
globalThis.fetch = async (url) => {
  appendFileSync(${JSON.stringify(join(work, 'asked.txt'))}, url + '\\n')
  const body = url.endsWith('/operations/index.html') ? s.html : url.endsWith('/Human_Resources.wsdl') ? s.hr : null
  return { ok: body !== null, status: body === null ? 404 : 200, arrayBuffer: async () => new TextEncoder().encode(body ?? '').buffer }
}
`)
  const wws = join(skill, 'scripts/wws.mjs')
  const f = spawnSync(process.execPath, ['--import', fake, wws, 'fetch', '--services', 'Human_Resources', '--index', join(work, 'fetched')], { encoding: 'utf8' })
  const asked = readFileSync(join(work, 'asked.txt'), 'utf8').trim().split('\n')
  ok(f.status === 0 && /3 operations/.test(f.stdout) && /Human_Resources v47.0: 4 operations/.test(f.stdout), 'fetch: the Operation Directory page and the WSDL, indexed', f.stdout + f.stderr)
  ok(asked.length === 3 && asked.every((u) => u.startsWith('https://community.workday.com/sites/default/files/file-hosting/productionapi/')), `fetch asks only Workday Community (${asked.length} files: the directory, the WSDL, its XSD)`, asked.join('\n'))

  // xsd:any and a required choice, on a small synthetic schema
  const xsd = join(work, 'Choice_Any.xsd')
  writeFileSync(xsd, `<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:wd="urn:com.workday/bsvc" targetNamespace="urn:com.workday/bsvc">
  <xs:element name="Pick_Request"><xs:complexType><xs:sequence>
    <xs:choice><xs:element name="By_Name" type="xs:string"/><xs:element name="By_Code" type="xs:string"/></xs:choice>
    <xs:element name="Extra"><xs:complexType><xs:sequence><xs:any minOccurs="0" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>`)
  const pick = new TreeBuilder(registryOf(parseWsdl(xsd, { version: 'v1.0' }))).element('Pick_Request')
  const env = buildEnvelope(pick, { bodyOnly: true }).xml
  ok(findPath(pick, 'Extra').any && /<!-- any element may go here \(xsd:any\) -->/.test(env), 'xsd:any is marked, in the tree and in the envelope')
  ok(/<!-- one of \(required\): By_Name \| By_Code — keep one -->\n\s*<wd:By_Name>/.test(env) && !/By_Code>/.test(env), 'a required choice: its alternatives named, the first kept')

  // a reference's ID types as Workday writes them: <wd:enumeration> in xsd:annotation/xsd:appinfo
  const app = join(work, 'Appinfo.xsd')
  writeFileSync(app, `<?xml version="1.0"?>
<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:wd="urn:com.workday/bsvc" targetNamespace="urn:com.workday/bsvc">
  <xsd:element name="Find_Request"><xsd:complexType><xsd:sequence><xsd:element name="Person_Reference" type="wd:PersonObjectType"/></xsd:sequence></xsd:complexType></xsd:element>
  <xsd:complexType name="PersonObjectType"><xsd:sequence><xsd:element name="ID" type="wd:PersonObjectIDType" minOccurs="0" maxOccurs="unbounded"/></xsd:sequence></xsd:complexType>
  <xsd:complexType name="PersonObjectIDType"><xsd:simpleContent><xsd:extension base="xsd:string"><xsd:attribute name="type" type="wd:PersonReferenceEnumeration" use="required"/></xsd:extension></xsd:simpleContent></xsd:complexType>
  <xsd:simpleType name="PersonReferenceEnumeration"><xsd:restriction base="xsd:string"><xsd:annotation><xsd:appinfo><wd:enumeration value="WID"/><wd:enumeration value="Person_Code"/></xsd:appinfo></xsd:annotation></xsd:restriction></xsd:simpleType>
</xsd:schema>`)
  const person = new TreeBuilder(registryOf(parseWsdl(app, { version: 'v1.0' }))).element('Find_Request')
  ok(JSON.stringify(findPath(person, 'Person_Reference/ID').attrs[0].enum) === '["WID","Person_Code"]' && /<wd:ID wd:type="Person_Code">/.test(buildEnvelope(person).xml), "a reference's ID types as Workday writes them (wd:enumeration in xsd:appinfo), and the one chosen")

  // an optional container that holds the required fields (Workday's Add_…_Event_Data) is not left out
  const box = join(work, 'Box.xsd')
  writeFileSync(box, `<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:com.workday/bsvc">
  <xs:element name="Put_Request"><xs:complexType><xs:sequence>
    <xs:element name="Options" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Quiet" type="xs:boolean" minOccurs="0"/></xs:sequence></xs:complexType></xs:element>
    <xs:element name="Event_Data" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Start" type="xs:date"/><xs:element name="Note" type="xs:string" minOccurs="0"/></xs:sequence></xs:complexType></xs:element>
  </xs:sequence></xs:complexType></xs:element>
</xs:schema>`)
  const put = buildEnvelope(new TreeBuilder(registryOf(parseWsdl(box, { version: 'v1.0' }))).element('Put_Request'), { bodyOnly: true }).xml
  ok(/<!-- optional in the schema, but it holds the required fields -->\n\s*<wd:Event_Data>\n\s*<wd:Start>/.test(put) && !/Options|Note/.test(put), 'an optional container with required fields comes (said so); one with none, and optional fields, do not', put)

  // the ESS template
  const t = essTemplate(ix, 'Add_Flexible_Work_Arrangement')
  const doc = parseXml(t.xml, 'ess')
  ok(doc.local === 'workdayEntityConfigurationTemplate' && /<authType>User<\/authType>/.test(t.xml) && /<serviceName>Human_Resources<\/serviceName>/.test(t.xml) && /<version>v47\.0<\/version>/.test(t.xml), 'ess: a workdayEntityConfigurationTemplate — the scenario, as the user, its service and version')
  ok(/<requestTemplate name="Template_Add_Flexible_Work_Arrangement">\s*<bsvc:Add_Flexible_Work_Arrangement_Request xmlns:bsvc="urn:com.workday\/bsvc" bsvc:version="v47.0">/.test(t.xml) && /\{Worker_ID\}/.test(t.xml) && !/\{\{|<!--/.test(t.xml), 'ess: the request template, the element alone with {Placeholders}, no comments')
  ok(/<extractPath>\/\/\*\[local-name\(\)='Arrangement_Event_Reference'\]\/\*\[local-name\(\)='ID' and @\*\[local-name\(\)='type'\]='WID'\]\/text\(\)<\/extractPath>/.test(t.xml), 'ess: what to read back, as local-name() XPaths')
}

// ---------- the MCP server (scripts/mcp.mjs, alone in a folder: nothing from node_modules) ----------
{
  const alone = join(work, 'mcp-alone')
  mkdirSync(alone)
  copyFileSync(join(skill, 'scripts/mcp.mjs'), join(alone, 'mcp.mjs'))
  const idx = join(work, 'mcp-index')
  spawnSync(process.execPath, [join(skill, 'scripts/wws.mjs'), 'ingest', ex, '--index', idx], { encoding: 'utf8' })
  const talk = (calls) => {
    const lines = calls.map((c, i) => JSON.stringify({ jsonrpc: '2.0', id: i + 1, ...c }))
    const input = [JSON.stringify({ jsonrpc: '2.0', id: 0, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'check', version: '1' } } }), JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }), ...lines].join('\n') + '\n'
    const r = spawnSync(process.execPath, ['--import', join(work, 'no-network.mjs'), join(alone, 'mcp.mjs')], { input, encoding: 'utf8', env: { ...process.env, WWS_INDEX: idx }, timeout: 20000 })
    return Object.fromEntries(r.stdout.split('\n').filter(Boolean).map((l) => JSON.parse(l)).map((m) => [m.id, m]))
  }
  const out = talk([
    { method: 'tools/list', params: {} },
    { method: 'tools/call', params: { name: 'wws_search_operations', arguments: { query: 'aprovar home office' } } },
    { method: 'tools/call', params: { name: 'wws_get_operation', arguments: { operation: 'Add_Flexible_Work_Arrangement', path: 'Arrangement_Data' } } },
    { method: 'tools/call', params: { name: 'wws_get_operation', arguments: { operation: 'Nope_Operation' } } },
    { method: 'tools/call', params: { name: 'wws_copilot_action_spec', arguments: { operation: 'Approve_Business_Process' } } },
    { method: 'tools/call', params: { name: 'wws_ess_template', arguments: { operation: 'Approve_Business_Process' } } },
  ])
  const text = (n) => out[n]?.result?.content?.[0]?.text ?? ''
  const tools = out[1]?.result?.tools ?? []
  const WANT = ['wws_search_operations', 'wws_trace_use_case', 'wws_get_operation', 'wws_build_envelope', 'wws_copilot_action_spec', 'wws_ess_template', 'wws_list_services', 'wws_index_status']
  ok(out[0]?.result?.serverInfo?.name === 'workday-wws' && WANT.every((n) => tools.some((t) => t.name === n)) && tools.every((t) => t.annotations?.readOnlyHint === true), `MCP: initialize, and the ${WANT.length} tools of the Python server (and ess), all read-only`, JSON.stringify(out).slice(0, 800))
  const top = text(2) ? JSON.parse(text(2)).results.slice(0, 3).map((r) => r.operation) : []
  ok(top.includes('Approve_Business_Process') && top.some((o) => o.endsWith('Flexible_Work_Arrangement')), 'MCP: the search', top.join(', '))
  ok(text(3).includes('Worker_Reference') && out[4]?.result?.isError === true && /not found/.test(text(4)), 'MCP: an operation with a path; one that is not there is an error, not a crash')
  ok(text(5) && JSON.parse(text(5)).parameters.service === 'Integrations' && /workdayEntityConfigurationTemplate/.test(text(6)), 'MCP: the Copilot Studio spec and the ESS template')
  const code = readFileSync(join(skill, 'scripts/mcp.mjs'), 'utf8')
  ok(!/from ["']node:(http|https|net|tls|dgram|child_process)["']/.test(code) && !/\bfetch\(/.test(code.replace(/\/\/.*$/gm, '')), 'the MCP bundle: no network module and no fetch')
  const mcpJson = JSON.parse(readFileSync(join(plugin, '.mcp.json'), 'utf8'))
  ok(mcpJson.mcpServers['workday-wws'].args[0] === '${CLAUDE_PLUGIN_ROOT}/skills/workday-integration/scripts/mcp.mjs', 'the plugin declares the server (.mcp.json, ${CLAUDE_PLUGIN_ROOT})')
}

// ---------- the skill ----------
{
  const files = readdirSync(ex, { recursive: true }).filter((f) => /\.(wsdl|xsd|txt)$/.test(f))
  ok(files.length === 4 && files.every((f) => /SYNTHETIC/.test(readFileSync(join(ex, f), 'utf8').slice(0, 400))), `the ${files.length} example files say they are synthetic`)
  const md = readFileSync(join(skill, 'SKILL.md'), 'utf8')
  const version = JSON.parse(readFileSync(join(plugin, '.claude-plugin/plugin.json'), 'utf8')).version
  ok(md.includes(`version: "${version}"`), `SKILL.md carries the plugin's version (${version})`)
  ok(md.split('\n').length < 500 && /as the user/i.test(md) && /never invent/i.test(md) && /calls no tenant/i.test(md) && /not affiliated with Workday/i.test(md), 'SKILL.md: under 500 lines, the identity rule, no invented field, no tenant, not affiliated')
}

rmSync(work, { recursive: true, force: true })
if (failed) {
  console.error(`✗ ${failed} check${failed === 1 ? '' : 's'} failed`)
  process.exit(1)
}
console.log('✓ workday-integration checks ok')
