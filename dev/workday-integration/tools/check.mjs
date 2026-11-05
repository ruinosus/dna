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
import { parseOpenApi } from '../src/rest.mjs'
import { connectorActions, copilotActionSpec, essTemplate, findElement, getOperation, getRestEndpoint, getType, listOperations, makeEnvelope, relatedOperations, restActionSpec } from '../src/workflows.mjs'

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
  // 0.2.0: the words as they are — the agent writes Workday's terms; each result says what matched where
  const plain = ix.search('request flexible work arrangement', { limit: 3 })
  ok(plain.some((r) => r.operation === 'Add_Flexible_Work_Arrangement') && plain.every((r) => r.matched.length && r.matched.every((m) => m.in.length)), 'search, the words as they are (Workday\'s terms): each result says what matched, and where', JSON.stringify(plain.map((r) => [r.operation, r.matched])))
  ok(!ix.search('colaborador pede trabalho flexível').some((r) => r.matched.some((m) => m.term === 'request')), 'search without --expand adds no word of its own (no synonym, no verb boost)')
  ok(ix.search('Approve_Business_Process')[0].operation === 'Approve_Business_Process', 'an exact operation name comes first')
  // --expand: the Portuguese synonyms of the Python port, still there for whoever wants them
  for (const [q, want] of [
    ['quero aprovar o home office do meu advisee', 'Flexible_Work_Arrangement'],
    ['encerrar trabalho remoto', 'End_Flexible_Work_Arrangement'],
    ['saldo de férias', 'Get_Time_Off_Plan_Balances'],
    ['histórico de eventos do colaborador', 'Get_Worker_Event_History'],
  ]) ok(top(q, { expand: true }).some((o) => o.includes(want)), `search --expand «${q}» → ${want}`, top(q, { expand: true }).join(', '))
  for (const [q, want] of [
    ['colaborador pede trabalho flexível e o gestor aprova', 'Add_Flexible_Work_Arrangement'],
    ['o colaborador encerra o trabalho remoto', 'End_Flexible_Work_Arrangement'],
    ['o gestor cancela o pedido', 'Cancel_Business_Process'],
  ]) ok(top(q, { expand: true })[0] === want, `search --expand «${q}» → ${want} first (the short verb forms)`, top(q, { expand: true }).join(', '))
  ok(!ix.search('journals').length && top('journals', { scope: 'all' })[0] === 'Get_Journals', 'the HR scope by default; --scope all for the rest')
  // 0.2.4: an operation whose name is the words (in any order), or holds them all, comes first and says so; each result has its verb
  const byName = ix.search('arrangement flexible work end')
  ok(byName[0].operation === 'End_Flexible_Work_Arrangement' && byName[0].matched[0].term === 'the name is your words' && byName.every((r) => r.verb === r.operation.split('_')[0]), 'search: the name is the words (any order) → first, and said; each result has its verb', JSON.stringify(byName.slice(0, 2).map((r) => [r.operation, r.matched[0]])))
  const holds = ix.search('worker event')
  ok(holds[0].operation === 'Get_Worker_Event_History' && /all your words are in the name \(and 2 others\)/.test(holds[0].matched[0].term), 'search: all the words in the name → ahead, and how many other words it has', JSON.stringify(holds.slice(0, 2).map((r) => [r.operation, r.matched[0]])))

  ok(!ix.search('expense sheet', { scope: 'all' }).length && ix.search('expense sheet', { scope: 'all', includeDeprecated: true }).length, 'a deprecated operation is left out')
  const none = getOperation(ix, 'Enter_Time_Off')
  ok(none.schema === null && /node scripts\/wws\.mjs ingest/.test(none.hint), 'known from the directory only: the hint says what to ingest')
  ok(throws(() => ix.resolve('Add_Flexible_Work'), /not found/), 'an operation that is not there')
  // related: facts, no verdict
  const r = relatedOperations(ix, 'Add_Flexible_Work_Arrangement')
  ok(r.same_noun.some((x) => x.operation === 'End_Flexible_Work_Arrangement' && x.description) && ['Approve_Business_Process', 'Deny_Business_Process', 'Send_Back_Business_Process', 'Cancel_Business_Process', 'Rescind_Business_Process', 'Get_Event_Detail', 'Get_Worker_Event_History'].every((o) => r.business_process_events.some((x) => x.operation === o)), 'related: the operations on the same noun, and those on business process events, with Workday\'s descriptions')
  ok(r.facts.some((f) => /No Get_Flexible_Work_Arrangement/.test(f) && /indexed/.test(f)) && !('primary' in r) && !('steps' in r) && r.notes.every((n) => n.text && n.kind) && Object.keys(r.sources).length, 'related: «no Get_» as a fact about the index, no primary, no steps; the notes with their kind, the sources once')
  ok(!/GetWorkerMe|GetWorkerInboxTasks/.test(JSON.stringify(r)), 'related: no connector action it cannot check')
  // browsing: a service, a type, where a field is
  const ops = listOperations(ix, 'Integrations')
  ok(ops.operations.length === 6 && ops.operations.every((o) => o.schema) && listOperations(ix, 'Human_Resources', { filter: 'flexible' }).operations.length === 2, 'operations: a service\'s, and filtered')
  const ty = getType(ix, 'WorkerObjectType')
  ok(ty.service === 'Human_Resources' && /ID\* : string @type\{WID\|Employee_ID\|Contingent_Worker_ID\}/.test(ty.schema), 'type: a type\'s tree, wherever it is defined')
  const wh = findElement(ix, 'Worker_Reference')
  ok(wh.operations.some((o) => o.operation === 'Add_Flexible_Work_Arrangement' && o.in === 'request' && o.paths.includes('Add_Flexible_Work_Arrangement_Request/Arrangement_Data/Worker_Reference')) && wh.operations.some((o) => o.operation === 'Get_Worker_Event_History'), 'where: which operations carry a field, and by which path', JSON.stringify(wh).slice(0, 600))
  ok(findElement(ix, 'Unique_IdentifierObjectType').found > 5 && throws(() => getType(ix, 'Nope_Type'), /No type/), 'where by a type; a type that is not there')
  // the envelope's decisions, and changing them
  const env = makeEnvelope(ix, 'Add_Flexible_Work_Arrangement')
  ok(env.decisions.some((d) => d.kind === 'id_type' && d.path.endsWith('Worker_Reference') && d.chosen === 'Employee_ID' && d.options.length === 3 && d.why === 'default') && /Employee_ID for a person/.test(env.decision_rules.default), 'envelope: the ID type it chose, among its options, said as a default (the rule once, in decision_rules)')
  const env2 = makeEnvelope(ix, 'Add_Flexible_Work_Arrangement', { idTypes: { Worker_Reference: 'WID' }, include: ['Arrangement_Data/Job_Reference'], choose: ['Job_Reference'] })
  ok(/<wd:Worker_Reference>\n\s*<wd:ID wd:type="WID">/.test(env2.xml) && /<wd:Job_Reference>/.test(env2.xml) && !/<wd:Position_Reference>/.test(env2.xml) && env2.decisions.some((d) => d.kind === 'choice' && d.kept === 'Job_Reference' && d.why === 'chosen'), 'envelope: --id-type and --choose change them')
  // 0.2.4: what to read back — the fields asked for, checked, with the connector's path and an ESS XPath
  const rd = copilotActionSpec(ix, 'Get_Worker_Event_History', { read: ['Event/Effective', 'Event/Event_Reference'] })
  const [eff, ref] = rd.response.reads
  ok(eff.kind === 'value' && eff.value_type === 'xsd:date' && eff.repeats === true && eff.xpath === "//*[local-name()='Worker_Event_History_Response']/*[local-name()='Event']/*[local-name()='Effective']/text()" && ref.kind === 'reference' && /ID\[@wd:type='WID'\]$/.test(rd.response.read_paths[1]), 'copilot --read: a value (its type, that it repeats, its XPath) and a reference (its WID)', JSON.stringify(rd.response))
  ok(throws(() => copilotActionSpec(ix, 'Get_Worker_Event_History', { read: ['Event'] }), /holds fields, not a value — read one of them: Event_Reference, Effective/) && throws(() => copilotActionSpec(ix, 'Get_Worker_Event_History', { read: ['Event/Nope'] }), /not under/), 'copilot --read: a container or a path that is not there is refused, with the fields to pick')
  const essRead = essTemplate(ix, 'Get_Worker_Event_History', { read: ['Event/Effective'] })
  ok(/<key>Effective<\/key>/.test(essRead.xml) && /local-name\(\)='Effective'\]\/text\(\)/.test(essRead.xml) && essRead.response_properties[0].repeats, 'ess --read: the field asked for as a responseProperty, said to repeat')
  ok(copilotActionSpec(ix, 'Add_Flexible_Work_Arrangement').response.read_default, 'copilot without --read: the references, said as the default')
  ok(throws(() => makeEnvelope(ix, 'Add_Flexible_Work_Arrangement', { idTypes: { Worker_Reference: 'Badge_ID' } }), /takes WID, Employee_ID, Contingent_Worker_ID — not Badge_ID/) && throws(() => makeEnvelope(ix, 'Add_Flexible_Work_Arrangement', { choose: ['Nope'] }), /not an alternative/) && throws(() => makeEnvelope(ix, 'Add_Flexible_Work_Arrangement', { idTypes: { Nope_Reference: 'WID' } }), /not a reference in this envelope/), 'envelope: an ID type, a choice or a reference that is not there is refused, with the options')
  const spec = copilotActionSpec(ix, 'Add_Flexible_Work_Arrangement', { include: ['Arrangement_Data/Note'] })
  const inputs = Object.fromEntries(spec.inputs.map((i) => [i.name, i]))
  ok(spec.operation_id === 'SOAP_Operation' && JSON.stringify(spec.parameters) === '{"service":"Human_Resources","version":"v47.0","requestBody":"<see power_fx / xml_template>"}', 'copilot: Execute SOAP operation, its service and version')
  ok(inputs.WorkerID.id_type === 'Employee_ID' && inputs.FirstDay.type === 'Date', 'copilot: typed inputs')
  ok(spec.power_fx.includes('Text(Topic.FirstDay, "yyyy-mm-dd")') && spec.power_fx.includes('Substitute(Substitute(Substitute(Topic.Note') && spec.power_fx.includes('version=""v47.0""'), 'copilot: Power Fx — dates as text, free text escaped, quotes doubled')
  ok(spec.notes.some((n) => /signed-in user/.test(n.text) && /Entra ID Integrated/.test(n.text)) && spec.notes.some((n) => /Integration Permissions/.test(n.text) && /Task not authorized/.test(n.text)) && spec.notes.some((n) => /200 calls/.test(n.text)) && spec.notes.some((n) => /Secure inputs and Secure outputs/.test(n.text)) && spec.notes.every((n) => n.kind) && spec.sources.documentation && /learn\.microsoft\.com/.test(spec.sources.documentation) && spec.decisions.length && spec.response.read_paths.length, 'copilot: the identity as the signed-in user, the domain security, the limit, Secure inputs/outputs — the sources once —, its decisions, what to read back')
  ok(Object.keys(spec)[5] === 'power_fx' && Object.keys(spec).indexOf('notes') > Object.keys(spec).indexOf('decisions') && !/<!--/.test(spec.xml_template + spec.power_fx) && spec.notes.some((n) => n.kind === 'pointer') && spec.notes.every((n) => !['schema', 'inferred', 'description'].includes(n.kind)), 'copilot (0.2.3): the formula first, the notes last; no comment in the request body; of the curated notes the ones to act on, and where the rest is')
  ok(!/<env:Envelope|wsse:/.test(spec.xml_template) && /^<wd:Add_Flexible_Work_Arrangement_Request xmlns:wd=/.test(spec.xml_template), 'copilot: requestBody is the element alone by default (no envelope, no WS-Security)')
  ok(/<env:Envelope/.test(copilotActionSpec(ix, 'Add_Flexible_Work_Arrangement', { bodyStyle: 'envelope' }).xml_template), 'copilot --envelope: the whole envelope, when asked')
  const nospec = copilotActionSpec(ix, 'Enter_Time_Off')
  ok(nospec.parameters.service === 'Absence_Management' && nospec.warning, 'copilot without a WSDL: a warning, not a guess')
  ok(throws(() => getOperation(ix, 'Add_Flexible_Work_Arrangement', { path: 'Nope' }), /not under/) && LookupError, 'show --path that is not there')
}

// ---------- the same answers as the Python port (checks/golden.json) ----------
{
  const golden = JSON.parse(readFileSync(join(here, '../checks/golden.json'), 'utf8'))
  // notes are rewritten here, hints name this CLI, and decisions and matched are new (0.2.0): left out of the comparison;
  // the trace is gone (0.2.0: related, with facts only) and its cases are not compared; the search is compared with
  // --expand, the Python's synonyms
  // and a choice's comment now names its alternatives (it said «alternatives exist»): those comment lines too
  const noChoice = (v) => (typeof v === 'string' ? v.split('\n').filter((l) => !/^\s*<!-- (choice |one of )/.test(l)).join('\n').replace(/<!-- (choice |one of )[^>]*-->\n?/g, '') : v)
  // 0.2.3 cuts for an agent's answer — the spec's XML without comments, a field's documentation at 160 characters, an
  // input's description at 100 — applied to both sides, so what is compared is still the Python's logic
  const cut = (t, n) => ([...t].length > n ? [...t].slice(0, n - 1).join('') + '…' : t)
  const noComments = (t) => t.split('\n').filter((l) => !/^\s*<!--.*-->\s*$/.test(l)).map((l) => l.replace(/\s*<!--.*?-->/g, '')).join('\n')
  const strip = (o, key = '', parent = '') => (Array.isArray(o) ? o.map((x) => strip(x, key, parent)) : o && typeof o === 'object' ? Object.fromEntries(Object.entries(o).filter(([k]) => !['notes', 'score', 'hint', 'warning', 'decisions', 'decision_rules', 'matched', 'sources', 'cut', 'verb', 'read_default', 'api'].includes(k)).sort(([a], [b]) => (a < b ? -1 : 1)).map(([k, v]) => [k, strip(v, k, key)])) : typeof o === 'string' && key === 'doc' ? cut(o, 160) : typeof o === 'string' && key === 'description' && parent === 'inputs' ? cut(o, 100) : typeof o === 'string' && (key === 'xml_template' || key === 'power_fx') ? noComments(noChoice(o)) : noChoice(o))
  const run = (c) => {
    const a = c.args
    try {
      if (c.cmd === 'search') return ix.search(a.query, { scope: a.scope, limit: 10, expand: true })
      if (c.cmd === 'show') return getOperation(ix, a.operation, { which: a.which, path: a.path, depth: a.depth, fmt: a.fmt, budget: Infinity })
      if (c.cmd === 'envelope') return makeEnvelope(ix, a.operation, { include: a.include, mode: a.mode, withHeader: a.with_header, bodyOnly: a.body_only })
      if (c.cmd === 'copilot') return copilotActionSpec(ix, a.operation, { include: a.include, bodyStyle: a.body_style ?? 'envelope' })
    } catch (e) {
      if (e instanceof LookupError) return { error: e.message }
      throw e
    }
  }
  const off = []
  const cases = golden.cases.filter((c) => c.cmd !== 'trace')
  for (const c of cases) {
    const got = JSON.parse(JSON.stringify(run(c)))
    // search: the same operations with the same bm25 scores; equal scores may come in any order (the Python's did)
    const same = c.cmd === 'search'
      ? JSON.stringify(c.out.map((r, i) => [c.scores[i], JSON.stringify(strip(r))]).sort()) === JSON.stringify(got.map((r) => [r.score, JSON.stringify(strip(r))]).sort())
      : JSON.stringify(strip(c.out)) === JSON.stringify(strip(got))
    if (!same) off.push(`${c.cmd} ${JSON.stringify(c.args)}`)
  }
  ok(!off.length && cases.length >= 30, `the same answers as the Python port on the examples (${cases.length - off.length}/${cases.length}: search --expand with its bm25 scores, show, envelope, copilot)`, off.join('\n'))
}

// ---------- the notes ----------
{
  const all = Object.values(NOTES).flat()
  const KINDS = ['schema', 'description', 'inferred', 'sensitive', 'tenant']
  ok(all.every((n) => KINDS.includes(n.kind)), `every note has a kind (${KINDS.join(', ')})`)
  ok(all.filter((n) => n.kind === 'schema').every((n) => n.evidence?.length || n.absent?.length || n.absentFields?.length), "every «schema» note names its evidence (tools/check-real.mjs finds it in an index of Workday's real WSDLs)")
  ok(all.filter((n) => n.kind === 'description').every((n) => n.quote), "every «description» note quotes Workday's words")
  ok(!/Staffing functional area security|self-approval is blocked by BP security|Approval routing follows the supervisory organization/.test(all.map((n) => n.text).join('\n')) && all.some((n) => n.kind === 'tenant'), 'what the schema cannot show is a «tenant» note')
  ok(['Get_Workers', 'Get_Worker_Event_History', 'Get_Event_Detail'].every((op) => NOTES[op].some((n) => n.kind === 'sensitive')), 'what may come back about a person is a «sensitive» note')
  const shown = getOperation(ix, 'Add_Flexible_Work_Arrangement').notes
  const shownAll = getOperation(ix, 'Add_Flexible_Work_Arrangement')
  ok(shown.every((n) => n.text && n.kind) && /deduction/.test(shownAll.sources.inferred) && shown.some((n) => n.kind === 'schema' && n.evidence), 'show: each note with its kind (the source of each kind once) and, from the schema, its evidence')
  // a tree too big for an agent's answer is cut to a lower depth, and says so
  const small = getOperation(ix, 'Add_Flexible_Work_Arrangement', { depth: 6, budget: 600 })
  ok(small.cut && /cut to depth \d of the 6 asked/.test(small.cut) && /path/.test(small.cut) && small.schema.length <= 600 * 2, 'show: a tree too big is cut to a lower depth, with how to go down', small.cut)
  ok(shown.some((n) => n.absent_operations?.includes('Get_Flexible_Work_Arrangement')) && shown.some((n) => n.absent_fields?.includes('Questionnaire')) && shown.some((n) => n.kind === 'description' && n.quote) && shown.some((n) => /^To confirm in the tenant: the /.test(n.text)), 'show: what proves each note — the absent operations and fields, the quote — and the tenant note in one sentence')
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
  const steps = [['status'], ['search', 'aprovar home office'], ['related', 'Add_Flexible_Work_Arrangement'], ['operations', 'Integrations'], ['type', 'WorkerObjectType'], ['where', 'Worker_Reference'], ['show', 'Add_Flexible_Work_Arrangement', '--path', 'Arrangement_Data'], ['envelope', 'Approve_Business_Process', '--body-only'], ['copilot', 'Approve_Business_Process']]
  const outs = steps.map((s) => cli(...s, '--json', '--index', idx))
  ok(outs.every((o) => o.status === 0 && JSON.parse(o.stdout) && !/NETWORK/.test(o.stderr)), 'status, search, related, operations, type, where, show, envelope, copilot: --json, and no network', outs.map((o) => o.stderr).join('\n'))
  ok(JSON.parse(outs[outs.length - 1].stdout).parameters.service === 'Integrations', 'copilot by the CLI: the service of the operation')
  const bad = cli('show', 'Nope_Operation', '--index', idx)
  ok(bad.status === 2 && /not found/.test(bad.stderr), 'an operation that is not there: exit 2', bad.stderr)
  const nos = cli('envelope', 'Enter_Time_Off', '--index', idx)
  ok(nos.status === 3 && /No WSDL ingested for Absence_Management/.test(nos.stdout), 'no WSDL for its service: exit 3, with what to ingest', nos.stdout)
  const code = readFileSync(wws, 'utf8')
  ok(!/from ["']node:(http|https|net|tls|dgram)["']|require\(["'](http|https|net)/.test(code) && (code.match(/\bfetch\(/g) ?? []).length === 1, 'the bundle: no http/net module, one call to fetch (the fetch command, SOAP and REST)')
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

// ---------- 0.3.0: REST — Workday's OpenAPI specifications, beside the SOAP ----------
{
  const REST = join(ex, 'rest/peopleDesk_v1_20260101_oas2.json')
  const spec = parseOpenApi(JSON.parse(readFileSync(REST, 'utf8')), 'peopleDesk_v1_20260101_oas2.json')
  const card = spec.endpoints.find((e) => e.method === 'GET' && e.path === '/workers/{ID}')
  ok(spec.service === 'peopleDesk' && spec.version === 'v1' && spec.prefix === 'peopleDesk/v1' && spec.endpoints.length === 3, 'REST: a spec — its service, version and prefix, from its name and basePath; an endpoint per method and path')
  ok(JSON.stringify(card.domains) === '["Self-Service: Card","Person Data: Card"]' && JSON.stringify(card.scope) === '["People Basics"]', "REST: the security domains and the scope, from Workday's description")
  ok(card.params[0].accepts.wid && JSON.stringify(card.params[0].accepts.reference_id_types) === '["Employee_ID","Contingent_Worker_ID"]' && JSON.stringify(card.params[0].accepts.named) === '["me"]', 'REST: what an ID accepts — a WID, Reference ID types, me (a $ref parameter resolved)')
  const rx = new Index(join(work, 'rest-index'))
  rx.ingestDirectory(readFileSync(join(ex, 'operation-directory-sample.txt'), 'utf8'))
  for (const f of [HR, INT]) rx.ingestSchema(parseWsdl(f), f)
  rx.ingestRest(spec, REST)
  const mixed = rx.search('leave balances')
  ok(mixed[0].api === 'rest' && mixed[0].operation === 'GET peopleDesk/v1 /workers/{ID}/leaveBalances' && mixed[0].domains.length && /path/.test(mixed[0].matched[0].term), 'search: a REST endpoint among the SOAP operations, marked api: rest, with its domains; the path as its name', JSON.stringify(mixed.slice(0, 2)))
  ok(rx.search('arrangement', { api: 'soap' }).every((r) => r.api === 'soap') && rx.search('arrangement', { api: 'rest' }).every((r) => r.api === 'rest') && rx.search('arrangement').some((r) => r.api === 'rest') && rx.search('arrangement').some((r) => r.api === 'soap'), 'search: SOAP and REST together by default; --api soap|rest for one')
  const ep = getRestEndpoint(rx, 'get', 'workers/{ID}/leaveBalances')
  ok(ep.relative_path === 'peopleDesk/v1/{tenant}/workers/{ID}/leaveBalances' && ep.facts.some((f) => /Secured by the domains .*Self-Service: Leave Balances/.test(f)) && ep.facts.some((f) => /Scope .*Time Away/.test(f)) && /balance\? : number/.test(ep.response.tree), "rest: the endpoint — its relativePath with {tenant}, the domains and scope as facts, the response's fields")
  const post = getRestEndpoint(rx, 'POST', '/workers/{ID}/arrangementRequests')
  ok(/startDate : string \(date\)/.test(post.body.tree) && /note\? : string/.test(post.body.tree) && /id\? : string ro/.test(post.body.tree), 'rest: the body — allOf and $ref resolved, required and optional, read-only said')
  ok(throws(() => getRestEndpoint(rx, 'DELETE', '/workers/{ID}'), /No REST endpoint DELETE \/workers\/\{ID\}.*on that path: GET peopleDesk\/v1/), 'rest: an endpoint that is not there names what is on that path')
  // the connector's Execute REST request (Preview)
  const r1 = restActionSpec(rx, 'GET', '/workers/{ID}/leaveBalances', { idForms: { ID: 'me' }, read: ['data.balance', 'data.plan.id'] })
  ok(r1.operation_id === 'REST_Operation' && r1.parameters.relativePath === 'peopleDesk/v1/{tenant}/workers/me/leaveBalances?asOf={{AsOf}}' && r1.parameters.method === 'GET' && !r1.parameters.body && r1.decisions[0].chosen === 'me', 'copilot-rest: Execute REST request — relativePath with {tenant}, the ID as me (a decision), no body for a GET')
  ok(r1.response.reads.every((x) => x.repeats) && r1.response.reads[0].type === 'number' && r1.notes.some((n) => /signed-in user's OAuth/.test(n.text)) && r1.notes.some((n) => /idempotency/.test(n.text)) && r1.notes.some((n) => n.kind === 'spec' && /Leave Balances/.test(n.text)), 'copilot-rest: what to read (a number, one per plan), the OAuth and idempotency notes, the domains from the spec')
  ok(r1.inputs.length === 1 && r1.inputs[0].in === 'query' && r1.inputs[0].required && r1.decisions.some((d) => d.kind === 'optional_query' && d.left_out.map((q) => q.name).join() === 'limit,offset' && /at most 100/.test(d.left_out[0].description)), 'copilot-rest: a required query parameter is an input; the optional ones (paging) left out are a decision, with what Workday says of them', JSON.stringify(r1.decisions))
  const paged = restActionSpec(rx, 'GET', '/workers/{ID}/leaveBalances', { idForms: { ID: 'me' }, include: ['limit', 'offset'] })
  ok(paged.parameters.relativePath.endsWith('?asOf={{AsOf}}&limit={{Limit}}&offset={{Offset}}') && paged.power_fx.relativePath.includes('EncodeUrl(Text(Topic.Limit))') && paged.inputs.find((i) => i.name === 'Limit').type === 'Number' && !paged.decisions.some((d) => d.kind === 'optional_query'), 'copilot-rest: include names a query parameter — an input in the path, a number as text in the Power Fx', paged.power_fx.relativePath)
  const ep2 = getRestEndpoint(rx, 'GET', '/workers/{ID}/leaveBalances', { fmt: 'json' })
  const shown = JSON.stringify(ep2).match(/data\[\]\.plan\.id/)?.[0]
  const r1b = restActionSpec(rx, 'GET', '/workers/{ID}/leaveBalances', { idForms: { ID: 'me' }, read: [shown, 'data.plan.id'] })
  ok(shown && r1b.response.reads.every((x) => x.json_path === 'data[].plan.id' && x.repeats), 'copilot-rest: read takes a path as rest shows it (data[].plan.id), and without the brackets', shown)
  ok(throws(() => restActionSpec(rx, 'GET', '/workers/{ID}/leaveBalances', { include: ['nope'] }), /has no body; its query parameters: asOf, limit, offset/), 'copilot-rest: include on an endpoint with no body names its query parameters')
  const r2 = restActionSpec(rx, 'POST', '/workers/{ID}/arrangementRequests', { idForms: { ID: 'Employee_ID' }, include: ['office.id'] })
  const body = JSON.parse(r2.body_template.replace(/"\{\{[A-Za-z0-9_]+\}\}"/g, '"x"'))
  ok(JSON.stringify(Object.keys(body)) === '["startDate","kind","office"]' && !('id' in body) && r2.decisions.some((d) => d.kind === 'optional_fields' && d.left_out.includes('note')), 'copilot-rest: the body — the required fields and include, no read-only field; the optional ones left out said')
  const inp = Object.fromEntries(r2.inputs.map((i) => [i.name, i]))
  ok(inp.ID.written_as === 'Employee_ID=<value>' && r2.power_fx.relativePath.includes('"Employee_ID=" & EncodeUrl(Topic.ID)') && inp.StartDate.type === 'Date' && inp.KindId.required && !inp.OfficeId.required, 'copilot-rest: the inputs — the ID written as a Reference ID, a date, a field required only when what holds it is')
  ok(r2.power_fx.body.includes('Text(Topic.StartDate, "yyyy-mm-dd")') && r2.power_fx.body.includes('Substitute(Substitute(Topic.KindId, "\\", "\\\\"), """", "\\""")'), 'copilot-rest: the Power Fx of the body — a date as text, a string escaped for JSON', r2.power_fx.body)
  ok(throws(() => restActionSpec(rx, 'GET', '/workers/{ID}', { idForms: { ID: 'Badge_ID' } }), /takes WID, Employee_ID=…, Contingent_Worker_ID=…, me — not Badge_ID/) && throws(() => restActionSpec(rx, 'POST', '/workers/{ID}/arrangementRequests', { include: ['nope'] }), /not a field of/) && throws(() => restActionSpec(rx, 'GET', '/workers/{ID}/leaveBalances', { read: ['data'] }), /holds fields, not a value/), 'copilot-rest: a wrong ID form, body field or read is refused, with the options')
  const actions = connectorActions()
  ok(['SOAP_Operation', 'REST_Operation', 'RaaS_Operation', 'GetWorkerMe', 'GetWorkerInboxTasks', 'TransferEmployee'].every((id) => actions.actions.some((a) => a.id === id)) && /learn\.microsoft\.com/.test(actions.source), "connector: the connector's actions, from Microsoft's documentation")
  // fetch --rest, with a fake network: the directory page, its script, the spec
  const served = join(work, 'served-rest.json')
  writeFileSync(served, JSON.stringify({ page: '<script src="bundle.0a1b2c.js"></script>', bundle: 'x="peopleDesk_v1_20260101_oas2.json";y="peopleDesk_v1_20260101_oas2.json";z="otherThing_v2_20260101_oas2.json"', spec: readFileSync(REST, 'utf8') }))
  const fake = join(work, 'fake-rest.mjs')
  writeFileSync(fake, `import { readFileSync, appendFileSync } from 'node:fs'
const s = JSON.parse(readFileSync(${JSON.stringify(served)}, 'utf8'))
globalThis.fetch = async (url) => {
  appendFileSync(${JSON.stringify(join(work, 'asked-rest.txt'))}, url + '\\n')
  const body = url.endsWith('/index.html') ? s.page : url.endsWith('.js') ? s.bundle : url.endsWith('peopleDesk_v1_20260101_oas2.json') ? s.spec : null
  return { ok: body !== null, status: body === null ? 404 : 200, text: async () => body, arrayBuffer: async () => new TextEncoder().encode(body ?? '').buffer }
}
`)
  const f = spawnSync(process.execPath, ['--import', fake, join(skill, 'scripts/wws.mjs'), 'fetch', '--rest', '--rest-services', 'peopleDesk', '--index', join(work, 'fetched-rest')], { encoding: 'utf8' })
  const asked = readFileSync(join(work, 'asked-rest.txt'), 'utf8').trim().split('\n')
  ok(f.status === 0 && /REST peopleDesk v1: 3 endpoints/.test(f.stdout) && asked.length === 3 && asked.every((u) => u.startsWith('https://community.workday.com/sites/default/files/file-hosting/restapi/')), 'fetch --rest: the page, its script, the spec it names (only the services asked), from Workday Community only', f.stdout + f.stderr + asked.join('\n'))
  writeFileSync(served, JSON.stringify({ page: '<html>changed</html>', bundle: '', spec: '' }))
  const changed = spawnSync(process.execPath, ['--import', fake, join(skill, 'scripts/wws.mjs'), 'fetch', '--rest', '--index', join(work, 'fetched-rest-2')], { encoding: 'utf8' })
  ok(changed.status !== 0 && /Workday may have changed its REST directory page.*ingest/.test(changed.stdout), 'fetch --rest: a page that changed is said, with how to ingest the files instead', changed.stdout)
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
    { method: 'tools/call', params: { name: 'wws_search_operations', arguments: { query: 'approve business process flexible work arrangement', api: 'soap' } } },
    { method: 'tools/call', params: { name: 'wws_get_operation', arguments: { operation: 'Add_Flexible_Work_Arrangement', path: 'Arrangement_Data' } } },
    { method: 'tools/call', params: { name: 'wws_get_operation', arguments: { operation: 'Nope_Operation' } } },
    { method: 'tools/call', params: { name: 'wws_copilot_action_spec', arguments: { operation: 'Approve_Business_Process' } } },
    { method: 'tools/call', params: { name: 'wws_ess_template', arguments: { operation: 'Approve_Business_Process' } } },
  ])
  const text = (n) => out[n]?.result?.content?.[0]?.text ?? ''
  const tools = out[1]?.result?.tools ?? []
  const WANT = ['wws_get_rest_endpoint', 'wws_rest_action_spec', 'wws_list_connector_actions', 'wws_search_operations', 'wws_related_operations', 'wws_list_operations', 'wws_get_type', 'wws_find_element', 'wws_get_operation', 'wws_build_envelope', 'wws_copilot_action_spec', 'wws_ess_template', 'wws_list_services', 'wws_index_status']
  ok(out[0]?.result?.serverInfo?.name === 'workday-wws' && WANT.every((n) => tools.some((t) => t.name === n)) && tools.every((t) => t.annotations?.readOnlyHint === true), `MCP: initialize, and its ${WANT.length} tools, all read-only`, JSON.stringify(out).slice(0, 800))
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
  const files = readdirSync(ex, { recursive: true }).filter((f) => /\.(wsdl|xsd|txt|json)$/.test(f))
  ok(files.length === 5 && files.every((f) => /SYNTHETIC/.test(readFileSync(join(ex, f), 'utf8').slice(0, 400))), `the ${files.length} example files say they are synthetic`)
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
