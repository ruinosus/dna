// The name of every key, in English and Portuguese, with no model: the keys cast-list knows by heart, and for the rest
// the kind of key and its value («Conector shared_office365»). Each key belongs to one of the five dimensions, the
// Microsoft patterns or what people declared. The screen words never say «agent»: the role or the name says who.
import { MS_PATTERNS, PATTERNS_URL } from './microsoft'

export type Lang = 'en' | 'pt'
export type Dimension = 'conversation' | 'integrations' | 'knowledge' | 'orchestration' | 'governance' | 'microsoft' | 'declared'
export const DIMENSIONS: Record<Dimension, { en: string; pt: string }> = {
  conversation: { en: 'A. Conversation', pt: 'A. Conversa' },
  integrations: { en: 'B. Integrations', pt: 'B. Integrações' },
  knowledge: { en: 'C. Knowledge', pt: 'C. Conhecimento' },
  orchestration: { en: 'D. Orchestrator', pt: 'D. Orquestrador' },
  governance: { en: 'E. Governance', pt: 'E. Governança' },
  microsoft: { en: 'Microsoft patterns', pt: 'Padrões Microsoft' },
  declared: { en: 'Declared', pt: 'Declarado' },
}

interface Name { en: string; pt: string; dim: Dimension; lacks?: { en: [string, string]; pt: [string, string] } }
/** The keys known by heart. `lacks`: what an agent without it does not do (one, many). */
const KNOWN: Record<string, Name> = {
  'trigger:OnConversationStart': { dim: 'conversation', en: 'Greeting', pt: 'Boas-vindas' },
  'trigger:OnUnknownIntent': { dim: 'conversation', en: 'Fallback (when it does not understand)', pt: 'Fallback (quando não entende)' },
  'trigger:OnEscalate': { dim: 'conversation', en: 'Escalation to a person', pt: 'Escalonamento para humano', lacks: { en: ['does not escalate to a person', 'do not escalate to a person'], pt: ['não escala para humano', 'não escalam para humano'] } },
  'trigger:OnError': { dim: 'conversation', en: 'Error handling', pt: 'Tratamento de erro', lacks: { en: ['does not handle errors', 'do not handle errors'], pt: ['não trata erro', 'não tratam erro'] } },
  'trigger:OnRecognizedIntent': { dim: 'conversation', en: 'A topic of its own, by intent', pt: 'Tópico próprio, por intenção' },
  'trigger:OnRedirect': { dim: 'orchestration', en: 'Takes a call from the orchestrator', pt: 'Recebe chamada do orquestrador', lacks: { en: ['takes no call from the orchestrator', 'take no call from the orchestrator'], pt: ['não recebe chamada do orquestrador', 'não recebem chamada do orquestrador'] } },
  'trigger:OnSelectIntent': { dim: 'conversation', en: 'Disambiguation («did you mean…»)', pt: 'Desambiguação («você quis dizer…»)' },
  'trigger:OnSignIn': { dim: 'conversation', en: 'Sign-in', pt: 'Login' },
  'trigger:OnGeneratedResponse': { dim: 'conversation', en: 'Reviews the generated answer', pt: 'Revisa a resposta gerada' },
  'trigger:OnKnowledgeRequested': { dim: 'knowledge', en: 'Before searching knowledge', pt: 'Antes de buscar no conhecimento' },
  'trigger:OnToolSelected': { dim: 'orchestration', en: 'Child chosen as a tool', pt: 'Filho escolhido como ferramenta' },
  'trigger:OnActivity': { dim: 'conversation', en: 'On every message', pt: 'Em toda mensagem' },
  'setting:generative=on': { dim: 'conversation', en: 'Generative orchestration on', pt: 'Orquestração generativa ligada' },
  'setting:generative=off': { dim: 'conversation', en: 'Generative orchestration off', pt: 'Orquestração generativa desligada' },
  'setting:connectable': { dim: 'orchestration', en: 'Can be called by an orchestrator', pt: 'Pode ser chamado por um orquestrador' },
  'topics:with-model-description': { dim: 'conversation', en: 'Topics described for the model', pt: 'Tópicos descritos para o modelo' },
  'instructions:present': { dim: 'governance', en: 'Has instructions', pt: 'Tem instruções', lacks: { en: ['has no instructions', 'have no instructions'], pt: ['não tem instruções', 'não têm instruções'] } },
  'node:LogCustomTelemetryEvent': { dim: 'governance', en: 'Logs telemetry', pt: 'Registra telemetria', lacks: { en: ['logs no telemetry', 'log no telemetry'], pt: ['não registra telemetria', 'não registram telemetria'] } },
  'node:CSATQuestion': { dim: 'governance', en: 'Asks for satisfaction (CSAT)', pt: 'Pergunta a satisfação (CSAT)', lacks: { en: ['does not ask for satisfaction', 'do not ask for satisfaction'], pt: ['não pergunta a satisfação', 'não perguntam a satisfação'] } },
  'node:SearchAndSummarizeContent': { dim: 'knowledge', en: 'Generative answers from knowledge', pt: 'Respostas generativas sobre o conhecimento' },
  'node:SearchKnowledgeSources': { dim: 'knowledge', en: 'Searches the knowledge sources', pt: 'Busca nas fontes de conhecimento' },
  'yaml-only:triggerCondition': { dim: 'knowledge', en: 'Search condition only in YAML (the editor may erase it)', pt: 'Condição de busca só no YAML (a tela pode apagar)' },
  'knowledge:SharePointSearchSource': { dim: 'knowledge', en: 'Knowledge in SharePoint', pt: 'Conhecimento no SharePoint' },
  'declared:kpi': { dim: 'declared', en: 'KPI declared', pt: 'KPI declarado', lacks: { en: ['has no KPI declared', 'have no KPI declared'], pt: ['não tem KPI declarado', 'não têm KPI declarado'] } },
  'declared:owner': { dim: 'declared', en: 'Owner declared', pt: 'Dono declarado', lacks: { en: ['has no owner declared', 'have no owner declared'], pt: ['não tem dono declarado', 'não têm dono declarado'] } },
}

const MS_NAME = Object.fromEntries(MS_PATTERNS.map((p) => [p.id, p.name]))
/** The keys known by their kind: [prefix, dimension, name in English, name in Portuguese] — the value follows. */
const KINDS: [string, Dimension, string, string][] = [
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
  ['declared:', 'declared', 'Declared:', 'Declarado:'],
]
const kindOf = (key: string) => KINDS.find(([p]) => key.startsWith(p))

/** A behaviour an agent can lack (escalating, handling errors…), not a setting: what a drawing names first. */
export const isBehaviour = (key: string) => !!KNOWN[key]?.lacks

export function dimensionOf(key: string): Dimension {
  if (key.startsWith('reaches:')) return dimensionOf(`trigger:${key.slice(8)}`)
  return KNOWN[key]?.dim ?? kindOf(key)?.[1] ?? 'governance'
}

/** The fact a key is a part of: reaching a topic is part of having it. */
export const partOf = (key: string) => (key.startsWith('reaches:') ? `trigger:${key.slice(8)}` : undefined)

/** Readable names the files give (a connector's API name, an agent's schema name → the name people know). */
export type Names = Record<string, string>
const named = (value: string, names?: Names) => names?.[value] ?? value

export function labelOf(key: string, lang: Lang, names?: Names): string {
  const known = KNOWN[key]
  if (known) return known[lang]
  // a topic that leads to what another topic is for: part of that fact
  if (key.startsWith('reaches:')) {
    const fact = labelOf(`trigger:${key.slice(8)}`, lang)
    return lang === 'pt' ? `Um tópico leva a «${fact}»` : `A topic leads to «${fact}»`
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
  // a connector, its operation, a connection, an MCP server or an agent called: by the name the files give
  if (['connector:', 'connref:', 'mcp:', 'calls:'].includes(k[0])) value = named(value, names)
  if (k[0] === 'operation:') {
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
