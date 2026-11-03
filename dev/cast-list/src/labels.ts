// The name of every key, in English and Portuguese, with no model: the keys cast-list knows by heart, and for the rest
// the kind of key and its value («Conector shared_office365»). Each key belongs to one of the five dimensions, the
// Microsoft patterns or what people declared. The screen words never say «agent»: the role or the name says who.
import { MS_PATTERNS, PATTERNS_URL } from './microsoft'

export type Lang = 'en' | 'pt'
export type Dimension = 'conversation' | 'integrations' | 'knowledge' | 'orchestration' | 'governance' | 'text' | 'microsoft' | 'declared'
export const DIMENSIONS: Record<Dimension, { en: string; pt: string }> = {
  conversation: { en: 'A. Conversation', pt: 'A. Conversa' },
  integrations: { en: 'B. Integrations', pt: 'B. Integrações' },
  knowledge: { en: 'C. Knowledge', pt: 'C. Conhecimento' },
  orchestration: { en: 'D. Orchestrator', pt: 'D. Orquestrador' },
  governance: { en: 'E. Governance', pt: 'E. Governança' },
  text: { en: 'F. Text', pt: 'F. Texto' },
  microsoft: { en: 'Microsoft patterns', pt: 'Padrões Microsoft' },
  declared: { en: 'Declared', pt: 'Declarado' },
}

interface Name { en: string; pt: string; dim: Dimension; lacks?: { en: [string, string]; pt: [string, string] }; /** The name is already a sentence («Receives the conversation history»), not a thing. */ phrase?: true }
/** The keys known by heart. `lacks`: what an agent without it does not do (one, many). */
const KNOWN: Record<string, Name> = {
  'trigger:OnConversationStart': { dim: 'conversation', en: 'Greeting', pt: 'Boas-vindas' },
  'trigger:OnUnknownIntent': { dim: 'conversation', en: 'Fallback (when it does not understand)', pt: 'Fallback (quando não entende)' },
  'trigger:OnEscalate': { dim: 'conversation', en: 'Escalation to a person', pt: 'Escalonamento para humano', lacks: { en: ['does not escalate to a person', 'do not escalate to a person'], pt: ['não escala para humano', 'não escalam para humano'] } },
  'trigger:OnError': { dim: 'conversation', en: 'Error handling', pt: 'Tratamento de erro', lacks: { en: ['does not handle errors', 'do not handle errors'], pt: ['não trata erro', 'não tratam erro'] } },
  'trigger:OnRecognizedIntent': { dim: 'conversation', en: 'A topic of its own, by intent', pt: 'Tópico próprio, por intenção' },
  'trigger:OnRedirect': { dim: 'orchestration', phrase: true, en: 'Takes a call from the orchestrator', pt: 'Recebe chamada do orquestrador', lacks: { en: ['takes no call from the orchestrator', 'take no call from the orchestrator'], pt: ['não recebe chamada do orquestrador', 'não recebem chamada do orquestrador'] } },
  'trigger:OnSelectIntent': { dim: 'conversation', en: 'Disambiguation («did you mean…»)', pt: 'Desambiguação («você quis dizer…»)' },
  'trigger:OnSignIn': { dim: 'conversation', en: 'Sign-in', pt: 'Login' },
  'trigger:OnGeneratedResponse': { dim: 'conversation', phrase: true, en: 'Reviews the generated answer', pt: 'Revisa a resposta gerada' },
  'trigger:OnKnowledgeRequested': { dim: 'knowledge', en: 'Before searching knowledge', pt: 'Antes de buscar no conhecimento' },
  'trigger:OnToolSelected': { dim: 'orchestration', en: 'Child chosen as a tool', pt: 'Filho escolhido como ferramenta' },
  'trigger:OnActivity': { dim: 'conversation', en: 'On every message', pt: 'Em toda mensagem' },
  'setting:generative=on': { dim: 'conversation', en: 'Generative orchestration on', pt: 'Orquestração generativa ligada' },
  'setting:generative=off': { dim: 'conversation', en: 'Generative orchestration off', pt: 'Orquestração generativa desligada' },
  'setting:model-knowledge=on': { dim: 'governance', en: "The model's general knowledge on", pt: 'Conhecimento geral do modelo ligado' },
  'setting:model-knowledge=off': { dim: 'governance', en: "The model's general knowledge off", pt: 'Conhecimento geral do modelo desligado' },
  'setting:semantic-search=on': { dim: 'knowledge', en: 'Semantic search on', pt: 'Busca semântica ligada' },
  'setting:semantic-search=off': { dim: 'knowledge', en: 'Semantic search off', pt: 'Busca semântica desligada' },
  'setting:web-browsing=on': { dim: 'knowledge', en: 'Web browsing on', pt: 'Navegação na web ligada' },
  'setting:web-browsing=off': { dim: 'knowledge', en: 'Web browsing off', pt: 'Navegação na web desligada' },
  'setting:connectable': { dim: 'orchestration', phrase: true, en: 'Can be called by an orchestrator', pt: 'Pode ser chamado por um orquestrador' },
  'called-with:history': { dim: 'orchestration', phrase: true, en: 'Receives the conversation history', pt: 'Recebe o histórico da conversa', lacks: { en: ['does not receive the conversation history from the orchestrator', 'do not receive the conversation history from the orchestrator'], pt: ['não recebe o histórico da conversa do orquestrador', 'não recebem o histórico da conversa do orquestrador'] } },
  'routing:described': { dim: 'orchestration', phrase: true, en: 'Has a routing description', pt: 'Tem descrição de roteamento', lacks: { en: ['has no routing description', 'have no routing description'], pt: ['não tem descrição de roteamento', 'não têm descrição de roteamento'] } },
  'flow-returns': { dim: 'integrations', phrase: true, en: 'The flow returns an answer', pt: 'O fluxo devolve uma resposta', lacks: { en: ['has a flow that returns nothing', 'have a flow that returns nothing'], pt: ['tem fluxo que não devolve nada', 'têm fluxo que não devolve nada'] } },
  'flow-uses:child-flow': { dim: 'integrations', phrase: true, en: 'The flow calls another flow', pt: 'O fluxo chama outro fluxo' },
  'topics:with-model-description': { dim: 'conversation', en: 'Topics described for the model', pt: 'Tópicos descritos para o modelo' },
  'instructions:present': { dim: 'governance', phrase: true, en: 'Has instructions', pt: 'Tem instruções', lacks: { en: ['has no instructions', 'have no instructions'], pt: ['não tem instruções', 'não têm instruções'] } },
  'node:LogCustomTelemetryEvent': { dim: 'governance', phrase: true, en: 'Logs telemetry', pt: 'Registra telemetria', lacks: { en: ['logs no telemetry', 'log no telemetry'], pt: ['não registra telemetria', 'não registram telemetria'] } },
  'node:CSATQuestion': { dim: 'governance', phrase: true, en: 'Asks for satisfaction (CSAT)', pt: 'Pergunta a satisfação (CSAT)', lacks: { en: ['does not ask for satisfaction', 'do not ask for satisfaction'], pt: ['não pergunta a satisfação', 'não perguntam a satisfação'] } },
  'node:SearchAndSummarizeContent': { dim: 'knowledge', en: 'Generative answers from knowledge', pt: 'Respostas generativas sobre o conhecimento' },
  'node:SearchKnowledgeSources': { dim: 'knowledge', phrase: true, en: 'Searches the knowledge sources', pt: 'Busca nas fontes de conhecimento' },
  'yaml-only:triggerCondition': { dim: 'knowledge', en: 'Search condition only in YAML (the editor may erase it)', pt: 'Condição de busca só no YAML (a tela pode apagar)' },
  'knowledge:SharePointSearchSource': { dim: 'knowledge', en: 'Knowledge in SharePoint', pt: 'Conhecimento no SharePoint' },
  'declared:kpi': { dim: 'declared', en: 'KPI declared', pt: 'KPI declarado', lacks: { en: ['has no KPI declared', 'have no KPI declared'], pt: ['não tem KPI declarado', 'não têm KPI declarado'] } },
  'eval:run': { dim: 'governance', phrase: true, en: 'Passed through an evaluation', pt: 'Passou por uma avaliação', lacks: { en: ['has no evaluation', 'have no evaluation'], pt: ['não tem avaliação', 'não têm avaliação'] } },
  'declared:team': { dim: 'declared', en: 'Team declared', pt: 'Equipe declarada', lacks: { en: ['has no team declared', 'have no team declared'], pt: ['não tem equipe declarada', 'não têm equipe declarada'] } },
  'declared:owner': { dim: 'declared', en: 'Owner declared', pt: 'Responsável declarado', lacks: { en: ['has no owner declared', 'have no owner declared'], pt: ['não tem responsável declarado', 'não têm responsável declarado'] } },
}

const MS_NAME = Object.fromEntries(MS_PATTERNS.map((p) => [p.id, p.name]))
/** The keys known by their kind: [prefix, dimension, name in English, name in Portuguese] — the value follows. */
const KINDS: [string, Dimension, string, string][] = [
  ['called-with:input:', 'orchestration', 'Receives <value> from the orchestrator', 'Recebe <valor> do orquestrador'],
  ['flow-uses:http:', 'integrations', 'Flow calls', 'Fluxo chama'],
  ['flow-uses:connector:', 'integrations', 'Flow uses the connector', 'Fluxo usa o conector'],
  ['flow-uses:operation:', 'integrations', 'Flow uses the operation', 'Fluxo usa a operação'],
  ['orphan:topic:', 'governance', 'Topic nobody calls', 'Tópico que ninguém chama'],
  ['orphan:action:', 'governance', 'Tool nobody can choose', 'Ferramenta que ninguém escolhe'],
  ['orphan:variable:', 'governance', 'Variable nobody uses', 'Variável que ninguém usa'],
  ['orphan:flow:', 'governance', 'Flow nobody calls', 'Fluxo que ninguém chama'],
  ['disabled:node:', 'governance', 'Switched-off node', 'Nó desligado'],
  ['telemetry:event:', 'governance', 'Logs the event', 'Registra o evento'],
  ['telemetry:field:', 'governance', 'The event carries the field (<event>/<field>)', 'O evento leva o campo (<evento>/<campo>)'],
  ['disabled:', 'governance', 'Switched off', 'Desligado'],
  ['reaches:', 'conversation', 'A topic leads to it (part of trigger:<value>)', 'Um tópico leva a ele (parte de trigger:<valor>)'],
  ['calls:topic:', 'conversation', 'Calls the topic (one not found)', 'Chama o tópico (não encontrado)'],
  ['trigger:', 'conversation', 'Trigger', 'Gatilho'],
  ['setting:', 'conversation', 'Setting', 'Configuração'],
  ['connector:', 'integrations', 'Connector', 'Conector'],
  ['operation:', 'integrations', 'Operation', 'Operação'],
  ['connref:', 'integrations', 'Connection reference', 'Referência de conexão'],
  ['mcp:', 'integrations', 'MCP server', 'Servidor MCP'],
  ['flow:', 'integrations', 'Flow', 'Fluxo'],
  ['knowledge:', 'knowledge', 'Knowledge', 'Conhecimento'],
  ['node:', 'governance', 'Node', 'Nó'],
  ['calls:', 'orchestration', 'Calls', 'Chama'],
  ['child:', 'orchestration', 'Child', 'Filho'],
  ['var-in:', 'orchestration', 'Receives from the orchestrator', 'Recebe do orquestrador'],
  ['var:', 'orchestration', 'Global variable', 'Variável global'],
  ['model:', 'governance', 'Model', 'Modelo'],
  ['auth:', 'governance', 'Sign-in', 'Login'],
  ['ms:', 'microsoft', 'Microsoft pattern:', 'Padrão Microsoft:'],
  ['text:', 'text', 'Text:', 'Texto:'],
  ['declared:', 'declared', 'Declared:', 'Declarado:'],
]
const kindOf = (key: string) => KINDS.find(([p]) => key.startsWith(p))

/** A behaviour an agent can lack (escalating, handling errors…), not a setting: what a drawing names first. */
export const isBehaviour = (key: string) => !!KNOWN[key]?.lacks

export function dimensionOf(key: string): Dimension {
  if (key.startsWith('reaches:')) return dimensionOf(`trigger:${key.slice(8)}`)
  return KNOWN[key]?.dim ?? kindOf(key)?.[1] ?? 'governance'
}

/** `key` matches `pattern`: the same, or with a trailing `*` any key that starts the same. */
export const matches = (key: string, pattern: string) => (pattern.endsWith('*') ? key.startsWith(pattern.slice(0, -1)) : key === pattern)

/** Shorter than this, a routing description does not say when to call the agent (here, so the map needs no more). */
export const SHORT_ROUTING = 80

/** The fact a key is a part of: reaching a topic is part of having it; an event is part of logging telemetry, and a
 * field is part of its event. */
export function partOf(key: string): string | undefined {
  if (key.startsWith('reaches:')) return `trigger:${key.slice(8)}`
  if (key.startsWith('telemetry:event:')) return 'node:LogCustomTelemetryEvent'
  if (key.startsWith('telemetry:field:')) return `telemetry:event:${key.slice(16, key.lastIndexOf('/'))}`
  return undefined
}

/** An event's form on screen: the agent's place in its name is «‹name›» («‹nome›»). */
export const formText = (form: string, lang: Lang) => form.split('{agent}').join(lang === 'pt' ? '‹nome›' : '‹name›')
/** telemetry:field:<form>/<field> → its event's form and its field. */
const fieldOf = (key: string) => ({ form: key.slice(16, key.lastIndexOf('/')), field: key.slice(key.lastIndexOf('/') + 1) })

/** Readable names the files give (a connector's API name, an agent's schema name → the name people know). */
export type Names = Record<string, string>
// the names Microsoft gives its common connectors, for when the files give none (a flow's connection names only the API)
const MS_CONNECTORS: Record<string, string> = {
  shared_commondataserviceforapps: 'Microsoft Dataverse', shared_sharepointonline: 'SharePoint', shared_office365: 'Office 365 Outlook',
  shared_office365users: 'Office 365 Users', shared_teams: 'Microsoft Teams', shared_approvals: 'Approvals', shared_onedriveforbusiness: 'OneDrive for Business',
  shared_excelonlinebusiness: 'Excel Online (Business)', shared_sql: 'SQL Server', shared_azureblob: 'Azure Blob Storage', shared_planner: 'Planner',
  shared_outlook: 'Outlook.com', shared_webcontents: 'HTTP with Microsoft Entra ID', shared_servicenow: 'ServiceNow', shared_salesforce: 'Salesforce',
}
/** A connector, an MCP server or an agent by the name the files give it; a common Microsoft connector, by Microsoft's. */
export const named = (value: string, names?: Names) => names?.[value] ?? MS_CONNECTORS[value] ?? value
// the kinds whose name is a sentence: «Receives «X» from the orchestrator», «Logs the event «X»»
const PHRASE_KINDS = ['called-with:input:', 'telemetry:event:', 'telemetry:field:', 'flow-uses:', 'var-in:', 'reaches:']
/** The name of `key` reads as a sentence, so a job post says it as it is rather than «Has «…»». */
export const isPhrase = (key: string) => !!KNOWN[key]?.phrase || PHRASE_KINDS.some((p) => key.startsWith(p))

export function labelOf(key: string, lang: Lang, names?: Names): string {
  const known = KNOWN[key]
  if (known) return known[lang]
  // the text: a block by its official name or its first words, a marker by the profile's name (and its value)
  if (key.startsWith('text:block:')) {
    const variant = key.endsWith('~variant')
    const base = variant ? key.slice(0, -8) : key
    const name = names?.[base] ?? base.slice(11)
    return variant ? `${name} (${lang === 'pt' ? 'variação' : 'variation'})` : name
  }
  if (key.startsWith('text:link-domain:')) return `${lang === 'pt' ? 'Link para' : 'Link to'} ${key.slice(17)}`
  if (key === 'text:email') return lang === 'pt' ? 'Cita um e-mail' : 'Mentions an e-mail'
  if (key.startsWith('text:')) {
    const [id, value] = [key.slice(5).split('=')[0], key.includes('=') ? key.slice(key.indexOf('=') + 1) : undefined]
    const name = names?.[`text:${id}`] ?? id
    return value === undefined ? name : `${name} = ${value}`
  }
  // a topic that leads to what another topic is for: part of that fact
  if (key.startsWith('reaches:')) {
    const fact = labelOf(`trigger:${key.slice(8)}`, lang)
    return lang === 'pt' ? `Um tópico leva a «${fact}»` : `A topic leads to «${fact}»`
  }
  if (key.startsWith('called-with:input:')) return lang === 'pt' ? `Recebe «${key.slice(18)}» do orquestrador` : `Receives «${key.slice(18)}» from the orchestrator`
  if (key.startsWith('telemetry:event:')) return lang === 'pt' ? `Registra o evento «${formText(key.slice(16), lang)}»` : `Logs the event «${formText(key.slice(16), lang)}»`
  if (key.startsWith('telemetry:field:')) {
    const { form, field } = fieldOf(key)
    const event = formText(form, lang)
    return lang === 'pt' ? `«${event}» leva «${field}»` : `«${event}» carries «${field}»`
  }
  const count = /^knowledge:count=(\d+)$/.exec(key)
  if (count) {
    const n = Number(count[1])
    return lang === 'pt' ? `${n} ${n === 1 ? 'fonte' : 'fontes'} de conhecimento` : `${n} knowledge ${n === 1 ? 'source' : 'sources'}`
  }
  const k = kindOf(key)
  if (!k) return key
  let value = key.slice(k[0].length)
  if (k[0] === 'ms:') value = MS_NAME[value] ?? value
  if (k[0] === 'auth:' && value === 'None') return lang === 'pt' ? 'Sem login' : 'No sign-in'
  if (key.startsWith('setting:moderation=')) return lang === 'pt' ? `Moderação de conteúdo: ${key.slice(19)}` : `Content moderation: ${key.slice(19)}`
  // a connector, its operation, a connection, an MCP server or an agent called: by the name the files give
  if (['connector:', 'connref:', 'mcp:', 'calls:', 'flow:', 'flow-uses:connector:', 'orphan:flow:'].includes(k[0])) value = named(value, names)
  if (k[0] === 'disabled:') value = value.replace(':', ' ')
  if (k[0] === 'operation:' || k[0] === 'flow-uses:operation:') {
    const [api, op] = [value.slice(0, value.indexOf('/')), value.slice(value.indexOf('/') + 1)]
    value = `${named(api, names)} · ${op}`
  }
  return `${k[lang === 'pt' ? 3 : 2]} ${value}`
}

/** What `n` agents without `key` do not do: «não escala para humano», or «não tem «Conector x»». */
export function lacks(key: string, lang: Lang, n: number, names?: Names): string {
  const known = KNOWN[key]?.lacks?.[lang]
  if (known) return known[n === 1 ? 0 : 1]
  if (key.startsWith('reaches:')) {
    const fact = labelOf(`trigger:${key.slice(8)}`, lang)
    return lang === 'pt' ? `${n === 1 ? 'tem' : 'têm'} «${fact}», mas nenhum tópico leva a ele` : `${n === 1 ? 'has' : 'have'} «${fact}», but no topic leads to it`
  }
  if (key.startsWith('called-with:input:')) return lang === 'pt' ? `${n === 1 ? 'não recebe' : 'não recebem'} «${key.slice(18)}» do orquestrador` : `${n === 1 ? 'does' : 'do'} not receive «${key.slice(18)}» from the orchestrator`
  if (key.startsWith('telemetry:event:')) {
    const event = formText(key.slice(16), lang)
    return lang === 'pt' ? `${n === 1 ? 'não registra' : 'não registram'} o evento «${event}»` : `${n === 1 ? 'does' : 'do'} not log the event «${event}»`
  }
  if (key.startsWith('telemetry:field:')) {
    const { form, field } = fieldOf(key)
    const event = formText(form, lang)
    return lang === 'pt' ? `${n === 1 ? 'registra' : 'registram'} «${event}» sem «${field}»` : `${n === 1 ? 'logs' : 'log'} «${event}» without «${field}»`
  }
  if (key.startsWith('calls:topic:')) return lang === 'pt' ? `${n === 1 ? 'não chama' : 'não chamam'} o tópico ${key.slice(12)}` : `${n === 1 ? 'does' : 'do'} not call the topic ${key.slice(12)}`
  const name = labelOf(key, lang, names)
  return lang === 'pt' ? `${n === 1 ? 'não tem' : 'não têm'} «${name}»` : `${n === 1 ? 'does' : 'do'} not have «${name}»`
}

/** references/keys.md: every key by dimension, its name, and the Microsoft patterns with how each is known. */
export function keysMarkdown(): string {
  const out = ['# Keys', '', 'GENERATED from dev/cast-list/src/labels.ts and microsoft.ts by tools/assets.mjs — do not edit.', '',
    'Every fact cast-list finds is a key. The keys below have a name; any other key keeps its kind and value', '(«Connector shared_office365»), and a kind cast-list does not know stays as it is.', '']
  for (const [dim, d] of Object.entries(DIMENSIONS) as [Dimension, (typeof DIMENSIONS)[Dimension]][]) {
    out.push(`## ${d.en} — ${d.pt.replace(/^[A-E]\. /, '')}`, '', '| Key | Name | Nome |', '|---|---|---|')
    for (const [key, n] of Object.entries(KNOWN).filter(([, n]) => n.dim === dim)) out.push(`| \`${key}\` | ${n.en} | ${n.pt} |`)
    for (const [p, , en, pt] of KINDS.filter(([, x]) => x === dim)) out.push(`| \`${p}<value>\` | ${en} <value> | ${pt} <valor> |`)
    out.push('')
  }
  out.push(`## The Microsoft patterns`, '', `From [microsoft/skills-for-copilot-studio](${PATTERNS_URL}). With a mark in the YAML, cast-list finds them (\`ms:<id>\`);`,
    'the others only a person can say (in the cast file, `declared` with the key `ms:<id>`).', '', '| Pattern | How cast-list knows |', '|---|---|')
  for (const p of MS_PATTERNS) out.push(`| \`${p.id}\` — ${p.name} | ${p.sign ?? 'declared only'} |`)
  return `${out.join('\n')}\n`
}

/** The names without the part every one of them shares, when that part ends in a separator («Bodega Azul - Pedidos»,
 * «Bodega Azul - Frete» → «Pedidos», «Frete»): where they stand side by side, the shared part says nothing. */
export function shortNames(all: string[]): (name: string) => string {
  const common = all.length > 1 ? all.reduce((p, s) => { let i = 0; while (i < p.length && p[i] === s[i]) i++; return p.slice(0, i) }) : ''
  const prefix = /[-–·:]\s*$/.test(common) ? common : ''
  return (name) => (prefix && name.startsWith(prefix) && name.length > prefix.length ? name.slice(prefix.length) : name)
}
