// The extractor against the answer key of the six example agents (dev/agent-review/fixtures/EXPECTED.md), and against
// files it cannot read: those go to «unknown» with their path, and the rest of the agent is still read.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { extractAgent, type AgentFacts } from '../src/extract'
import { agentsIn } from '../src/folder'
import { knownKinds } from '../src/kinds'
import { done, ok } from './ok'

const skill = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/agent-review')
const kinds = knownKinds(JSON.parse(readFileSync(join(skill, 'vendor/microsoft/reference/bot.schema.yaml-authoring.json'), 'utf8')))
const found = agentsIn(join(skill, 'examples/agents'))
const agents = Object.fromEntries(found.map((a) => [a.id, extractAgent(a.id, a.files, kinds)])) as Record<string, AgentFacts>
const SPECIALISTS = ['rh-ferias', 'rh-beneficios', 'rh-folha', 'rh-admissao', 'rh-facilities']
const has = (id: string, key: string) => key in agents[id].facts
const keys = (id: string, prefix: string) => Object.keys(agents[id].facts).filter((k) => k.startsWith(prefix)).sort()
/** Every one of `ids` has every key of `list`. */
const all = (ids: string[], list: string[], what: string) => {
  const missing = ids.flatMap((id) => list.filter((k) => !has(id, k)).map((k) => `${id}: ${k}`))
  ok(!missing.length, what, missing.join(', '))
}

ok(found.map((a) => a.id).sort().join() === ['rh-orquestrador', ...SPECIALISTS].sort().join(), 'six agents found (the child agent inside the orchestrator is not a seventh)', found.map((a) => a.id))
ok(Object.values(agents).every((a) => !a.unknown.length), 'nothing in the examples is left not understood', Object.values(agents).flatMap((a) => a.unknown))
ok(agents['rh-ferias'].schemaName === 'cr7b2_rhFerias' && agents['rh-ferias'].displayName === 'RH - Férias', 'names from settings.mcs.yml, known by its file name (it has no kind)')

// the orchestrator
const o = 'rh-orquestrador'
ok(keys(o, 'calls:cr7b2').join() === ['cr7b2_rhAdmissao', 'cr7b2_rhBeneficios', 'cr7b2_rhFacilities', 'cr7b2_rhFerias', 'cr7b2_rhFolha', 'cr7b2_rhMobilidade'].map((s) => `calls:${s}`).join(), 'the orchestrator calls the five connected agents, and one not in the folder', keys(o, 'calls:'))
ok(has(o, 'child:SobreRH') && has(o, 'var:CategoriaSolicitacao') && has(o, 'ms:orchestrator-variables'), 'the orchestrator: its child agent, its global variable, the orchestrator-variables pattern')
ok(!has(o, 'trigger:OnToolSelected') && agents[o].children[0]?.name === 'SobreRH' && 'trigger:OnToolSelected' in agents[o].children[0].facts, "the child's OnToolSelected is the child's, not the orchestrator's")
ok(!keys(o, 'connector:').length && !keys(o, 'knowledge:').length && !keys(o, 'connref:').length, 'the orchestrator has no connector, knowledge or connection reference')
ok(has(o, 'model:GPT5Chat'), 'the model hint of agent.mcs.yml')

// the specialists: what they all have
all(SPECIALISTS, ['trigger:OnConversationStart', 'trigger:OnUnknownIntent', 'trigger:OnError', 'trigger:OnRecognizedIntent', 'trigger:OnRedirect'], 'every specialist: greeting, fallback, error, its own topic, and being called (OnRedirect)')
all(SPECIALISTS, ['connector:shared_office365', 'operation:shared_office365/SendEmailV2', 'connref:shared_office365'], 'every specialist sends e-mail through Outlook')
all(SPECIALISTS, ['knowledge:SharePointSearchSource', 'knowledge:count=1', 'node:SearchAndSummarizeContent'], 'every specialist: one SharePoint knowledge source and generative answers')
all(SPECIALISTS, ['var:CategoriaSolicitacao', 'var-in:CategoriaSolicitacao', 'setting:connectable'], 'every specialist receives the category and can be connected')
all([o, ...SPECIALISTS], ['setting:generative=on', 'auth:None', 'instructions:present'], 'every agent: generative actions on, no sign-in, instructions')
all(SPECIALISTS.filter((s) => s !== 'rh-folha'), ['reaches:OnEscalate'], 'the fallback reaches escalation: the called topic is known by its trigger')
ok(!Object.values(agents).some((a) => Object.keys(a.facts).some((k) => k.startsWith('calls:topic:'))), 'no topic call left unresolved in the examples')
ok(agents['rh-admissao'].names.shared_office365 === 'Office 365 Outlook' && agents['rh-admissao'].names.shared_rhadmissaomcp === 'RH Admissao MCP', 'the readable names of the connectors, from connectionreferences')

// what each one does differently, on purpose
ok(!has('rh-folha', 'trigger:OnEscalate') && SPECIALISTS.filter((s) => s !== 'rh-folha').every((s) => has(s, 'trigger:OnEscalate')), 'only rh-folha does not escalate')
ok(!has('rh-folha', 'reaches:OnEscalate'), "rh-folha's fallback does not reach escalation")
ok(!has('rh-facilities', 'node:LogCustomTelemetryEvent') && [o, ...SPECIALISTS].filter((s) => s !== 'rh-facilities').every((s) => has(s, 'node:LogCustomTelemetryEvent')), 'only rh-facilities logs no telemetry')
ok(has('rh-facilities', 'yaml-only:triggerCondition') && SPECIALISTS.filter((s) => s !== 'rh-facilities').every((s) => !has(s, 'yaml-only:triggerCondition')), 'only rh-facilities has a YAML-only triggerCondition')
const c = 'rh-admissao'
ok(has(c, 'connector:shared_sharepointonline') && has(c, 'operation:shared_sharepointonline/GetItems') && has(c, 'mcp:shared_rhadmissaomcp'), 'rh-admissao: SharePoint items and the MCP server')
ok(keys(c, 'connref:').length === 3, 'rh-admissao: three connection references', keys(c, 'connref:'))
ok(!has(c, 'ms:channel-aware-behavior'), 'a tool input that reads the channel is not the channel-aware pattern')

// wave 1: the text each agent carries, and the settings that go with it
const texts = (id: string) => agents[id].texts
ok(texts('rh-facilities').some((t) => t.source === 'instructions' && t.file === 'agent.mcs.yml' && t.line === 6 && t.text.startsWith('Você é o especialista em facilities')), 'the instructions, with the line their text starts on', texts('rh-facilities').map((t) => [t.source, t.file, t.line]))
ok(texts('rh-ferias').some((t) => t.source === 'descriptions' && t.file === 'topics/ConsultarPoliticaFerias.topic.mcs.yml'), "a topic's description for the model is a text too")
ok(texts('rh-ferias').some((t) => t.source === 'descriptions' && t.file === 'actions/AbrirCasoWorkday.mcs.yml'), "an action's description too")
ok(!texts('rh-ferias').some((t) => t.file.includes(' Copy')), 'a copied topic leaves its text out', texts('rh-ferias').map((t) => t.file))
ok(!texts('rh-orquestrador').some((t) => t.file.startsWith('agents/')), "the child agent's instructions are the child's, not compared")
ok(has('rh-beneficios', 'setting:model-knowledge=on') && !Object.keys(agents['rh-ferias'].facts).some((k) => k.startsWith('setting:model-knowledge')), "the model's general knowledge, only where the file says it")
ok(agents['rh-ferias'].names['7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f'] === 'Abrir caso no Workday' && has('rh-admissao', 'flow:7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f'), 'a flow, named by the action that calls it')
const set = extractAgent('s', [{ path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\ninstructions: Curto.\nresponseInstructions: |\n  Sempre em tópicos.\ngptCapabilities:\n  webBrowsing: false\naISettings:\n  contentModeration: High\n  isSemanticSearchEnabled: true\n' }, { path: 'topics/Ajuda.es-ES.topic.mcs.yml', text: 'kind: AdaptiveDialog\nmodelDescription: Ayuda\nbeginDialog:\n  kind: OnRecognizedIntent\n  id: main\n' }], kinds)
ok(['setting:web-browsing=off', 'setting:moderation=high', 'setting:semantic-search=on'].every((k) => k in set.facts), 'web browsing, moderation and semantic search, when the file has them', Object.keys(set.facts))
ok(set.texts.some((t) => t.text === 'Sempre em tópicos.' && t.line === 4) && !set.texts.some((t) => t.file.includes('es-ES')), 'responseInstructions are instructions; a translated copy is left out', set.texts)

// every fact says where it was seen
const src = agents['rh-folha'].facts['trigger:OnUnknownIntent']?.[0]
ok(src?.file === 'topics/Fallback.topic.mcs.yml' && (src.line ?? 0) > 1, 'a fact says its file and line', src)

// what it cannot read never stops it
const file = (path: string, text: string) => ({ path, text })
const odd = extractAgent('odd', [
  file('settings.mcs.yaml', 'schemaName: x_odd\ndisplayName: Odd\nauthenticationMode: Integrated\n'),
  file('agent.mcs.yaml', 'kind: GptComponentMetadata\ninstructions: Seja breve.\n'),
  file('topics/Ok.topic.mcs.yaml', 'kind: AdaptiveDialog\nbeginDialog:\n  kind: OnEscalate\n  id: main\n  actions: []\n'),
  file('topics/Broken.topic.mcs.yml', 'kind: AdaptiveDialog\nbeginDialog: [unclosed\n'),
  file('topics/Empty.topic.mcs.yml', ''),
  file('topics/Made.topic.mcs.yml', 'kind: AdaptiveDialog\nbeginDialog:\n  kind: OnInventado\n  id: main\n'),
  file('actions/Nokind.mcs.yml', 'name: no kind here\n'),
  file('notes.txt', 'loose file'),
], kinds)
const why = Object.fromEntries(odd.unknown.map((u) => [u.file, u.why]))
ok(why['topics/Broken.topic.mcs.yml'] === 'yaml' && why['topics/Empty.topic.mcs.yml'] === 'empty' && why['topics/Made.topic.mcs.yml'] === 'kind'
  && why['actions/Nokind.mcs.yml'] === 'kind' && why['notes.txt'] === 'file', 'broken YAML, an empty file, a made-up kind, no kind, a loose file: each one in unknown', odd.unknown)
ok(odd.unknown.find((u) => u.why === 'kind' && u.file === 'topics/Made.topic.mcs.yml')?.kind === 'OnInventado', 'the made-up kind is kept by name')
ok('trigger:OnEscalate' in odd.facts && 'auth:Integrated' in odd.facts && 'instructions:present' in odd.facts && odd.schemaName === 'x_odd', '.yaml read like .yml; the rest of the agent read', Object.keys(odd.facts))
ok(!Object.keys(odd.facts).some((k) => k.startsWith('knowledge:')), 'no knowledge folder: no knowledge, and no error')

// wave 2: the orchestrator's contract
const contract = Object.fromEntries(agents[o].contract.map((c) => [c.calls, c]))
ok(agents[o].contract.length === 6 && contract.cr7b2_rhFerias.history && contract.cr7b2_rhFerias.inputs.join() === 'CategoriaSolicitacao' && contract.cr7b2_rhFerias.file === 'actions/AgenteFerias.mcs.yml' && !!contract.cr7b2_rhFerias.line,
  'the contract: who it calls, the history, the inputs, the file and the line', agents[o].contract)
ok(!contract.cr7b2_rhFolha.history && !contract.cr7b2_rhFolha.inputs.length, 'folha: no history and no input', contract.cr7b2_rhFolha)
ok(contract.cr7b2_rhAdmissao.description === 'Admissão.', 'admissao: a routing description of 7 characters', contract.cr7b2_rhAdmissao)
ok(SPECIALISTS.every((id) => !agents[id].contract.length), 'a specialist calls no one')

// wave 2: the flows
const erp = 'flow-uses:http:workday.empresa.example'
all(['rh-ferias', 'rh-beneficios', 'rh-admissao'], [erp], 'the three transaction specialists: the flow calls the ERP by HTTP (inside a scope)')
ok(has('rh-ferias', 'flow-returns') && has('rh-beneficios', 'flow-returns') && !has('rh-admissao', 'flow-returns'), 'the flow answers the agent, except in admissao')
ok(agents['rh-ferias'].facts[erp][0].file === 'workflows/AbrirCasoWorkday-7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f/workflow.json' && agents['rh-ferias'].facts[erp][0].line! > 1, 'a flow fact says its file and the line of its action', agents['rh-ferias'].facts[erp])
ok(agents['rh-ferias'].flows[0]?.name === 'Abrir caso no Workday' && agents['rh-ferias'].flows[0].called, 'the flow is known by its display name, and the agent calls it', agents['rh-ferias'].flows)
const lf = 'rh-facilities'
ok(has(lf, 'orphan:flow:ListarUnidades') && !keys(lf, 'flow-uses:').length && agents[lf].flows[0]?.called === false, 'a flow no node calls is unused, and what it uses is not a fact', keys(lf, ''))

// wave 2: what nobody uses, what is switched off
ok(has(lf, 'orphan:topic:AvisoAntigo') && agents[lf].facts['orphan:topic:AvisoAntigo'][0].file === 'topics/AvisoAntigo.topic.mcs.yml', 'a topic nobody can reach, with its file')
ok(has('rh-folha', 'orphan:variable:PreferenciaAntiga') && !has('rh-folha', 'var:PreferenciaAntiga'), 'a variable no file names is unused, not a variable it has')
const off = agents['rh-ferias'].facts['disabled:node:SendActivity']
ok(off?.length === 1 && off[0].file === 'topics/Escalate.topic.mcs.yml' && !!off[0].line, 'a node switched off, with the file and the line', off)
const orphans = Object.values(agents).flatMap((a) => Object.keys(a.facts).filter((k) => /^(orphan|disabled):/.test(k)).map((k) => `${a.id} ${k}`))
ok(orphans.length === 4, 'four unused or switched off in the examples, and no other', orphans)

// wave 2, by hand: the shapes of a flow, and what is not unused
const y = (s: string) => s.replace(/^\n/, '')
const flowJson = (d: unknown, wrap: boolean) => JSON.stringify(wrap ? { properties: { definition: d } } : { definition: d }, null, 2)
const nested = {
  triggers: { manual: { type: 'Request', kind: 'Skills' } },
  actions: {
    Se: { type: 'If', actions: { A: { type: 'Http', inputs: { uri: 'https://a.example/x' } } }, else: { actions: { B: { type: 'Workflow', inputs: {} } } } },
    Caso: { type: 'Switch', cases: { um: { actions: { C: { type: 'OpenApiConnection', inputs: { host: { apiId: '/providers/Microsoft.PowerApps/apis/shared_teams', operationId: 'PostMessage' } } } } } } },
    Cada: { type: 'Foreach', actions: { D: { type: 'Http', inputs: { uri: 'https://d.example' } } } },
  },
}
const flowAgent = (wrap: boolean, json = flowJson(nested, wrap)) => extractAgent('f', [
  { path: 'actions/Chamar.mcs.yml', text: y(`
kind: TaskDialog
modelDescription: Chama o fluxo.
action:
  kind: InvokeFlowTaskAction
  flowId: 11111111-2222-3333-4444-555555555555
`) },
  { path: 'workflows/Fluxo-11111111/metadata.yml', text: 'workflowId: 11111111-2222-3333-4444-555555555555\njsonFileName: workflow.json\n' },
  { path: 'workflows/Fluxo-11111111/workflow.json', text: json },
], kinds)
for (const wrap of [true, false]) {
  const f = flowAgent(wrap)
  const uses = Object.keys(f.facts).filter((k) => k.startsWith('flow-uses:')).sort()
  ok(uses.join() === ['flow-uses:child-flow', 'flow-uses:connector:shared_teams', 'flow-uses:http:a.example', 'flow-uses:http:d.example', 'flow-uses:operation:shared_teams/PostMessage'].join() && !f.unknown.length,
    `inside a condition (and its else), a switch and a loop — the definition in ${wrap ? 'properties.definition' : 'definition'}`, [uses, f.unknown])
}
const broken = flowAgent(true, '{ "properties": ')
ok(broken.unknown.some((u) => u.file === 'workflows/Fluxo-11111111/workflow.json' && u.why === 'json') && 'flow:11111111-2222-3333-4444-555555555555' in broken.facts, 'a JSON that does not read goes to «not understood», and the rest is read', broken.unknown)
// as the extension clones on Windows: the flow's JSON with a byte-order mark (the examples have it), its metadata.yml
// naming it in `name`, its folder ending in the whole GUID
const bom = readFileSync(join(skill, 'examples/agents/rh-ferias/workflows/AbrirCasoWorkday-7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f/workflow.json'), 'utf8')
ok(bom.startsWith('\uFEFF') && agents['rh-ferias'].flows.some((f) => f.name === 'Abrir caso no Workday'), 'a workflow.json with a byte-order mark is read, and the flow has its name', agents['rh-ferias'].flows)
const cloned = extractAgent('c', [
  { path: 'icon.png', text: '' },
  { path: 'connectionreferences.mcs.yml', text: 'connectionReferences:\n  - connectionReferenceLogicalName: c_x.shared_office365.shared-office365-1\n    connectorId: /providers/Microsoft.PowerApps/apis/shared_office365\n' },
  { path: 'knowledge/files/Tabela.pdf', text: '' },
  { path: 'knowledge/files/Tabela.pdf.mcs.yml', text: 'mcs.metadata:\n  componentName: Tabela.pdf\n  description: Uma tabela.\n' },
  { path: 'workflows/Avisar-11111111-2222-3333-4444-555555555555/metadata.yml', text: 'jsonFileName: workflows/Avisar-11111111-2222-3333-4444-555555555555/workflow.json\nworkflowId: 11111111-2222-3333-4444-555555555555\ntype: 1\n' },
  { path: 'workflows/Avisar-11111111-2222-3333-4444-555555555555/workflow.json', text: flowJson(nested, true) },
], kinds)
ok(!cloned.unknown.length && 'connref:shared_office365' in cloned.facts && 'knowledge:file' in cloned.facts && 'knowledge:count=1' in cloned.facts && 'orphan:flow:Avisar' in cloned.facts,
  'the icon and an uploaded document are not read; connection references without a kind, the uploaded file as knowledge, a flow folder ending in a GUID, its jsonFileName a path', [cloned.unknown, Object.keys(cloned.facts)])
// a topic can begin an action: one among the agent's actions is fine; one of another agent's prefix is not found, by its full name
const begins = extractAgent('b', [
  { path: 'agents/Outro_Agente.mcs.yml', text: 'kind: TaskDialog\nmodelDescription: Chama o outro.\naction:\n  kind: InvokeConnectedAgentTaskAction\n  botSchemaName: z_outro\n' },
  { path: 'actions/Buscar.mcs.yml', text: 'kind: TaskDialog\nmodelDescription: Busca.\naction:\n  kind: InvokeConnectorTaskAction\n  connectionReference: b_x.shared_office365.y\n  operationId: Get\n' },
  { path: 'topics/Usa.mcs.yml', text: y(`
kind: AdaptiveDialog
beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent:
    triggerQueries: [usar]
  actions:
    - kind: BeginDialog
      id: a
      dialog: b_agente.action.Buscar
    - kind: BeginDialog
      id: c
      dialog: z_outro.action.Copiada
    - kind: BeginDialog
      id: d
      dialog: SemPrefixo
    - kind: BeginDialog
      id: e
      dialog: b_agente.InvokeConnectedAgentTaskAction.Buscar
    - kind: BeginDialog
      id: f
      dialog: b_agente.InvokeConnectedAgentTaskAction.Outro_Agente
`) },
], kinds)
const callKeys = Object.keys(begins.facts).filter((k) => k.startsWith('calls:action:') || k.startsWith('calls:topic:')).sort()
ok(callKeys.join() === 'calls:action:z_outro.action.Copiada,calls:topic:SemPrefixo', 'a topic that begins an action (by .action. or .InvokeConnectedAgentTaskAction.): its own is found (in actions/ or as a file of agents/), another agent\'s is not (by its full name); a dialog without a prefix keeps its whole name', callKeys)
const shapeless = flowAgent(true, '{ "something": 1 }')
ok(shapeless.unknown.some((u) => u.why === 'flow'), 'a flow in a shape it does not know goes to «not understood»', shapeless.unknown)

const topic = (name: string, body: string) => ({ path: `topics/${name}.topic.mcs.yml`, text: y(`
kind: AdaptiveDialog
${body}`) })
const notOrphans = extractAgent('t', [
  topic('ComDescricao', `modelDescription: Responde sobre prazos.
beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent: {}
  actions: []
`),
  topic('ComFrases', `beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent:
    triggerQueries:
      - qual o prazo
  actions: []
`),
  topic('Chamado', `beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent: {}
  actions: []
`),
  topic('Quem', `beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent:
    triggerQueries:
      - oi
  actions:
    - kind: BeginDialog
      id: b
      dialog: cr7b2_x.topic.Chamado
`),
  ...['OnConversationStart', 'OnUnknownIntent', 'OnError', 'OnEscalate', 'OnRedirect', 'OnSelectIntent', 'OnActivity'].map((t) => topic(t, `beginDialog:
  kind: ${t}
  id: main
  actions: []
`)),
  topic('Sozinho', `beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent: {}
  actions: []
`),
], kinds)
ok(Object.keys(notOrphans.facts).filter((k) => k.startsWith('orphan:')).join() === 'orphan:topic:Sozinho', 'not unused: a description, phrases, a BeginDialog that calls it, the system triggers', Object.keys(notOrphans.facts))

const switched = extractAgent('d', [
  topic('OnError', `beginDialog:
  kind: OnError
  id: main
  actions:
    - kind: LogCustomTelemetryEvent
      id: t
      disabled: true
      eventName: Erro
`),
  topic('Velho', `state: Inactive
beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent:
    triggerQueries:
      - velho
  actions:
    - kind: LogCustomTelemetryEvent
      id: t
      eventName: Velho
`),
], kinds)
ok(!('node:LogCustomTelemetryEvent' in switched.facts) && 'disabled:node:LogCustomTelemetryEvent' in switched.facts, 'a telemetry node switched off is not telemetry', Object.keys(switched.facts))
ok('disabled:topic:Velho' in switched.facts && !Object.keys(switched.facts).some((k) => k === 'trigger:OnRecognizedIntent'), 'state: Inactive — the topic is switched off, and nothing in it counts', Object.keys(switched.facts))

// Copilot Studio writes the keys of a Workday record (@Descriptor, @type, @Primary) with no quotes, which plain YAML
// refuses: Microsoft's own Employee Self-Service sample has them. They are read, and the lines stay where they were.
const workday = extractAgent('w', [
  { path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\ninstructions: Workday.\n' },
  { path: 'topics/Contato.topic.mcs.yml', text: 'kind: AdaptiveDialog\nbeginDialog:\n  kind: OnRecognizedIntent\n  id: main\n  actions:\n    - kind: SetVariable\n      id: v\n      variable: Topic.Contact\n      type:\n        kind: Record\n        properties:\n          @Descriptor: String\n          @type: String\n    - kind: LogCustomTelemetryEvent\n      id: log\n      eventName: "@ não é chave"\n' },
], kinds)
ok(!workday.unknown.length && 'trigger:OnRecognizedIntent' in workday.facts && workday.facts['node:LogCustomTelemetryEvent']?.[0]?.line === 14, 'a Workday record with @-keys and no quotes is read, at its own lines', [workday.unknown, Object.keys(workday.facts)])
done()
