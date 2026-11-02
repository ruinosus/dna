// The extractor against the answer key of the six example agents (dev/cast-list/fixtures/EXPECTED.md), and against
// files it cannot read: those go to «unknown» with their path, and the rest of the agent is still read.
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { extractAgent, type AgentFacts } from '../src/extract'
import { agentsIn } from '../src/folder'
import { knownKinds } from '../src/kinds'
import { done, ok } from './ok'

const skill = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list')
const kinds = knownKinds(JSON.parse(readFileSync(join(skill, 'vendor/microsoft/reference/bot.schema.yaml-authoring.json'), 'utf8')))
const found = agentsIn(join(skill, 'examples/agents'))
const agents = Object.fromEntries(found.map((a) => [a.id, extractAgent(a.id, a.files, kinds)])) as Record<string, AgentFacts>
const SPECIALISTS = ['bodega-pedidos', 'bodega-devolucoes', 'bodega-frete', 'bodega-cupons', 'bodega-loja-fisica']
const has = (id: string, key: string) => key in agents[id].facts
const keys = (id: string, prefix: string) => Object.keys(agents[id].facts).filter((k) => k.startsWith(prefix)).sort()
/** Every one of `ids` has every key of `list`. */
const all = (ids: string[], list: string[], what: string) => {
  const missing = ids.flatMap((id) => list.filter((k) => !has(id, k)).map((k) => `${id}: ${k}`))
  ok(!missing.length, what, missing.join(', '))
}

ok(found.map((a) => a.id).sort().join() === ['bodega-orquestrador', ...SPECIALISTS].sort().join(), 'six agents found (the child agent inside the orchestrator is not a seventh)', found.map((a) => a.id))
ok(Object.values(agents).every((a) => !a.unknown.length), 'nothing in the examples is left not understood', Object.values(agents).flatMap((a) => a.unknown))
ok(agents['bodega-pedidos'].schemaName === 'cr7b2_bodegaPedidos' && agents['bodega-pedidos'].displayName === 'Bodega Azul - Pedidos', 'names from settings.mcs.yml, known by its file name (it has no kind)')

// the orchestrator
const o = 'bodega-orquestrador'
ok(keys(o, 'calls:cr7b2').join() === ['cr7b2_bodegaCupons', 'cr7b2_bodegaDevolucoes', 'cr7b2_bodegaFrete', 'cr7b2_bodegaLojaFisica', 'cr7b2_bodegaPedidos'].map((s) => `calls:${s}`).join(), 'the orchestrator calls the five connected agents', keys(o, 'calls:'))
ok(has(o, 'child:SobreBodegaAzul') && has(o, 'var:CategoriaSolicitacao') && has(o, 'ms:orchestrator-variables'), 'the orchestrator: its child agent, its global variable, the orchestrator-variables pattern')
ok(!has(o, 'trigger:OnToolSelected') && agents[o].children[0]?.name === 'SobreBodegaAzul' && 'trigger:OnToolSelected' in agents[o].children[0].facts, "the child's OnToolSelected is the child's, not the orchestrator's")
ok(!keys(o, 'connector:').length && !keys(o, 'knowledge:').length && !keys(o, 'connref:').length, 'the orchestrator has no connector, knowledge or connection reference')
ok(has(o, 'model:GPT5Chat'), 'the model hint of agent.mcs.yml')

// the specialists: what they all have
all(SPECIALISTS, ['trigger:OnConversationStart', 'trigger:OnUnknownIntent', 'trigger:OnError', 'trigger:OnRecognizedIntent', 'trigger:OnRedirect'], 'every specialist: greeting, fallback, error, its own topic, and being called (OnRedirect)')
all(SPECIALISTS, ['connector:shared_office365', 'operation:shared_office365/SendEmailV2', 'connref:shared_office365'], 'every specialist sends e-mail through Outlook')
all(SPECIALISTS, ['knowledge:SharePointSearchSource', 'knowledge:count=1', 'node:SearchAndSummarizeContent'], 'every specialist: one SharePoint knowledge source and generative answers')
all(SPECIALISTS, ['var:CategoriaSolicitacao', 'var-in:CategoriaSolicitacao', 'setting:connectable'], 'every specialist receives the category and can be connected')
all([o, ...SPECIALISTS], ['setting:generative=on', 'auth:None', 'instructions:present'], 'every agent: generative actions on, no sign-in, instructions')
all(SPECIALISTS.filter((s) => s !== 'bodega-frete'), ['reaches:OnEscalate'], 'the fallback reaches escalation: the called topic is known by its trigger')
ok(!Object.values(agents).some((a) => Object.keys(a.facts).some((k) => k.startsWith('calls:topic:'))), 'no topic call left unresolved in the examples')
ok(agents['bodega-cupons'].names.shared_office365 === 'Office 365 Outlook' && agents['bodega-cupons'].names.shared_bodegapromocoesmcp === 'Bodega Azul Promocoes MCP', 'the readable names of the connectors, from connectionreferences')

// what each one does differently, on purpose
ok(!has('bodega-frete', 'trigger:OnEscalate') && SPECIALISTS.filter((s) => s !== 'bodega-frete').every((s) => has(s, 'trigger:OnEscalate')), 'only bodega-frete does not escalate')
ok(!has('bodega-frete', 'reaches:OnEscalate'), "bodega-frete's fallback does not reach escalation")
ok(!has('bodega-loja-fisica', 'node:LogCustomTelemetryEvent') && [o, ...SPECIALISTS].filter((s) => s !== 'bodega-loja-fisica').every((s) => has(s, 'node:LogCustomTelemetryEvent')), 'only bodega-loja-fisica logs no telemetry')
ok(has('bodega-loja-fisica', 'yaml-only:triggerCondition') && SPECIALISTS.filter((s) => s !== 'bodega-loja-fisica').every((s) => !has(s, 'yaml-only:triggerCondition')), 'only bodega-loja-fisica has a YAML-only triggerCondition')
const c = 'bodega-cupons'
ok(has(c, 'connector:shared_sharepointonline') && has(c, 'operation:shared_sharepointonline/GetItems') && has(c, 'mcp:shared_bodegapromocoesmcp'), 'bodega-cupons: SharePoint items and the MCP server')
ok(keys(c, 'connref:').length === 3, 'bodega-cupons: three connection references', keys(c, 'connref:'))
ok(!has(c, 'ms:channel-aware-behavior'), 'a tool input that reads the channel is not the channel-aware pattern')

// wave 1: the text each agent carries, and the settings that go with it
const texts = (id: string) => agents[id].texts
ok(texts('bodega-loja-fisica').some((t) => t.source === 'instructions' && t.file === 'agent.mcs.yml' && t.line === 6 && t.text.startsWith('Você é o especialista em loja física')), 'the instructions, with the line their text starts on', texts('bodega-loja-fisica').map((t) => [t.source, t.file, t.line]))
ok(texts('bodega-pedidos').some((t) => t.source === 'descriptions' && t.file === 'topics/ConsultarPoliticasPedidos.topic.mcs.yml'), "a topic's description for the model is a text too")
ok(texts('bodega-pedidos').some((t) => t.source === 'descriptions' && t.file === 'actions/AbrirChamadoERP.mcs.yml'), "an action's description too")
ok(!texts('bodega-pedidos').some((t) => t.file.includes(' Copy')), 'a copied topic leaves its text out', texts('bodega-pedidos').map((t) => t.file))
ok(!texts('bodega-orquestrador').some((t) => t.file.startsWith('agents/')), "the child agent's instructions are the child's, not compared")
ok(has('bodega-devolucoes', 'setting:model-knowledge=on') && !Object.keys(agents['bodega-pedidos'].facts).some((k) => k.startsWith('setting:model-knowledge')), "the model's general knowledge, only where the file says it")
ok(agents['bodega-pedidos'].names['7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f'] === 'Abrir chamado no ERP' && has('bodega-cupons', 'flow:7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f'), 'a flow, named by the action that calls it')
const set = extractAgent('s', [{ path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\ninstructions: Curto.\nresponseInstructions: |\n  Sempre em tópicos.\ngptCapabilities:\n  webBrowsing: false\naISettings:\n  contentModeration: High\n  isSemanticSearchEnabled: true\n' }, { path: 'topics/Ajuda.es-ES.topic.mcs.yml', text: 'kind: AdaptiveDialog\nmodelDescription: Ayuda\nbeginDialog:\n  kind: OnRecognizedIntent\n  id: main\n' }], kinds)
ok(['setting:web-browsing=off', 'setting:moderation=high', 'setting:semantic-search=on'].every((k) => k in set.facts), 'web browsing, moderation and semantic search, when the file has them', Object.keys(set.facts))
ok(set.texts.some((t) => t.text === 'Sempre em tópicos.' && t.line === 4) && !set.texts.some((t) => t.file.includes('es-ES')), 'responseInstructions are instructions; a translated copy is left out', set.texts)

// every fact says where it was seen
const src = agents['bodega-frete'].facts['trigger:OnUnknownIntent']?.[0]
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
done()
