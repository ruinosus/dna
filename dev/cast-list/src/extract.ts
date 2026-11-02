// What an agent cloned from Copilot Studio has, as facts: a key («trigger:OnEscalate», «connector:shared_office365») and
// every file and line it was seen in. Files are told apart by their kind (a connected-agent TaskDialog may live in
// topics/ or actions/), except settings.mcs.yml, which has none. A child agent (agents/<Name>/) has its own facts. What
// cannot be read — broken YAML, an empty file, a kind the schema does not have, a file that is not YAML — goes to
// `unknown` with its path, and the rest is read all the same.
import { isMap, isScalar, isSeq, LineCounter, parseDocument, type Node } from 'yaml'

export interface Source { file: string; line?: number }
export type Facts = Record<string, Source[]>
export interface Unknown { file: string; why: 'yaml' | 'empty' | 'kind' | 'file'; kind?: string }
export interface AgentFacts {
  /** The folder's name. */
  id: string
  schemaName?: string
  displayName?: string
  facts: Facts
  /** Child agents (AgentDialog): their facts are theirs, not the parent's. */
  children: { name: string; facts: Facts }[]
  unknown: Unknown[]
  /** Readable names the files give: a connector's API name → «Office 365 Outlook». */
  names: Record<string, string>
}

type Obj = Record<string, unknown>
const obj = (x: unknown): Obj | undefined => (x && typeof x === 'object' && !Array.isArray(x) ? (x as Obj) : undefined)
const str = (x: unknown): string | undefined => (typeof x === 'string' && x.trim() ? x : undefined)
const list = (x: unknown): unknown[] => (Array.isArray(x) ? x : [])

/** The YAML as plain values, and the line each map starts at. */
function read(text: string): { data: unknown; lineOf: (o: unknown) => number | undefined } | 'yaml' | 'empty' {
  if (!text.trim()) return 'empty'
  const lines = new LineCounter()
  const doc = parseDocument(text, { lineCounter: lines, uniqueKeys: false })
  if (doc.errors.length) return 'yaml'
  const at = new WeakMap<object, number>()
  const plain = (n: unknown): unknown => {
    if (isMap(n)) {
      const o: Obj = {}
      if (n.range) at.set(o, n.range[0])
      for (const p of n.items) o[String(isScalar(p.key) ? p.key.value : p.key)] = plain(p.value)
      return o
    }
    if (isSeq(n)) return n.items.map(plain)
    return isScalar(n) ? n.value : n
  }
  const data = plain(doc.contents as Node | null)
  if (data === null || data === undefined) return 'empty'
  return { data, lineOf: (o) => (o && typeof o === 'object' && at.has(o) ? lines.linePos(at.get(o)!).line : undefined) }
}

/** Every object with a string `kind`, at any depth. */
function* nodes(x: unknown): Generator<Obj> {
  if (Array.isArray(x)) for (const y of x) yield* nodes(y)
  const o = obj(x)
  if (!o) return
  if (typeof o.kind === 'string') yield o
  for (const v of Object.values(o)) yield* nodes(v)
}

/** «cr7b2_bot.shared_office365.shared-office365-…» → «shared_office365». */
const apiOf = (ref: string) => ref.split('.')[1] ?? ref
const last = (s: string, sep: string) => s.slice(s.lastIndexOf(sep) + (s.includes(sep) ? sep.length : 0))
const NODES = new Set(['LogCustomTelemetryEvent', 'CSATQuestion', 'SearchAndSummarizeContent', 'SearchKnowledgeSources'])

export function extractAgent(id: string, files: { path: string; text: string }[], kinds?: Set<string>): AgentFacts {
  const agent: AgentFacts = { id, facts: {}, children: [], unknown: [], names: {} }
  let knowledge: Source[] = []
  // a topic that calls another (BeginDialog) reaches what that topic is for — its trigger, known once every file is read
  const triggers = new Map<string, string>()
  const calls: { topic: string; into: Facts; at: Source }[] = []
  const topicName = (path: string) => last(path, '/').replace(/(\.topic)?\.mcs\.ya?ml$|\.ya?ml$/, '')
  for (const f of [...files].sort((a, b) => a.path.localeCompare(b.path))) {
    if (!/\.ya?ml$/.test(f.path)) {
      agent.unknown.push({ file: f.path, why: 'file' })
      continue
    }
    const r = read(f.text)
    if (r === 'yaml' || r === 'empty') {
      agent.unknown.push({ file: f.path, why: r })
      continue
    }
    const root = obj(r.data)
    const child = /^agents\/([^/]+)\//.exec(f.path)?.[1]
    let facts = agent.facts
    if (child) {
      let c = agent.children.find((x) => x.name === child)
      if (!c) agent.children.push((c = { name: child, facts: {} }))
      facts = c.facts
    }
    const add = (key: string, at?: unknown, into: Facts = facts) => (into[key] ??= []).push({ file: f.path, line: r.lineOf(at ?? root) })
    if (child) add(`child:${child}`, root, agent.facts)

    if (!child && /^settings\.mcs\.ya?ml$/.test(f.path) && root) {
      agent.schemaName = str(root.schemaName) ?? agent.schemaName
      agent.displayName = str(root.displayName) ?? agent.displayName
      if (str(root.authenticationMode)) add(`auth:${root.authenticationMode}`)
      const conf = obj(root.configuration)
      const generative = obj(conf?.settings)?.GenerativeActionsEnabled
      if (typeof generative === 'boolean') add(`setting:generative=${generative ? 'on' : 'off'}`, conf)
      if (conf?.isAgentConnectable === true) add('setting:connectable', conf)
      continue
    }

    // every kind in the file has to be one Copilot Studio knows; a made-up one is kept by name, and the rest is read
    const made = kinds ? [...nodes(root)].map((n) => n.kind as string).find((k) => !kinds.has(k)) : undefined
    if (made) agent.unknown.push({ file: f.path, why: 'kind', kind: made })
    if (typeof root?.kind !== 'string') {
      if (!made) agent.unknown.push({ file: f.path, why: 'kind' })
      continue
    }
    const text = f.text
    const instructions = (s: unknown, at: unknown) => {
      if (!str(s)) return
      add('instructions:present', at)
      if (/\b(Today|Now)\(\)/.test(s as string)) add('ms:date-context', at)
    }

    switch (root.kind) {
      case 'GptComponentMetadata': {
        agent.displayName ??= str(root.displayName)
        instructions(root.instructions, root)
        const model = obj(obj(root.aISettings)?.model)
        if (str(model?.modelNameHint)) add(`model:${model!.modelNameHint}`, model)
        break
      }
      case 'AgentDialog': {
        const begin = obj(root.beginDialog)
        if (str(begin?.kind)) add(`trigger:${begin!.kind}`, begin)
        instructions(obj(root.settings)?.instructions, root.settings)
        break
      }
      case 'AdaptiveDialog': {
        const begin = obj(root.beginDialog)
        const trigger = str(begin?.kind)
        if (trigger) add(`trigger:${trigger}`, begin)
        if (trigger) triggers.set(`${child ?? ''}/${topicName(f.path)}`, trigger)
        if (str(root.modelDescription)) add('topics:with-model-description')
        const silent = list(root.inputs).some((i) => obj(i)?.kind === 'AutomaticTaskInput' && obj(i)?.shouldPromptUser === false)
        if (trigger === 'OnRecognizedIntent' && silent) add('ms:orchestrator-variables', begin)
        if (trigger === 'OnError' && text.includes('System.Error.SubCode')) add('ms:rai-error-handling', begin)
        if (trigger === 'OnKnowledgeRequested' && [...nodes(begin)].some((n) => n.kind === 'SendActivity')) add('ms:knowledge-hold-message', begin)
        if (trigger === 'OnGeneratedResponse' && text.includes('System.ContinueResponse')) add('ms:prevent-tool-call-leaks', begin)
        break
      }
      case 'TaskDialog': {
        const a = obj(root.action)
        const ref = str(a?.connectionReference)
        if (a?.kind === 'InvokeConnectorTaskAction' && ref) {
          add(`connector:${apiOf(ref)}`, a)
          if (str(a.operationId)) add(`operation:${apiOf(ref)}/${a.operationId}`, a)
        }
        if (a?.kind === 'InvokeExternalAgentTaskAction' && obj(a.operationDetails)?.kind === 'ModelContextProtocolMetadata' && ref) add(`mcp:${apiOf(ref)}`, a)
        if (a?.kind === 'InvokeConnectedAgentTaskAction' && str(a.botSchemaName)) add(`calls:${a.botSchemaName}`, a)
        if (a?.kind === 'InvokeFlowTaskAction' && str(a.flowId)) add(`flow:${a.flowId}`, a)
        break
      }
      case 'KnowledgeSourceConfiguration': {
        const s = obj(root.source)
        if (str(s?.kind)) add(`knowledge:${s!.kind}`, s)
        if (s && 'triggerCondition' in s) add('yaml-only:triggerCondition', s)
        knowledge.push({ file: f.path, line: r.lineOf(root) })
        break
      }
      case 'GlobalVariableComponent': {
        // the flat shape of the templates, or the nested one of the schema
        const v = obj(root.variable) ?? root
        const name = str(v.name) ?? (str(root.schemaName) ? last(root.schemaName as string, '.') : undefined)
        if (!name) break
        add(`var:${name}`)
        if (v.isExternalInitializationAllowed === true) add(`var-in:${name}`)
        break
      }
      case 'ConnectionReferencesSourceFile':
        for (const c of list(root.connectionReferences).map(obj)) {
          const api = str(c?.connectorId) ? last(c!.connectorId as string, '/') : str(c?.connectionReferenceLogicalName) ? apiOf(c!.connectionReferenceLogicalName as string) : undefined
          if (api) add(`connref:${api}`, c)
          if (api && str(c?.displayName)) agent.names[api] = c!.displayName as string
        }
        break
    }

    // the nodes that say something, wherever they are
    for (const n of nodes(root)) {
      if (NODES.has(n.kind as string)) add(`node:${n.kind}`, n)
      if (n.kind === 'InvokeConnectorAction' && str(n.connectionReference)) {
        const api = apiOf(n.connectionReference as string)
        add(`connector:${api}`, n)
        if (str(n.operationId)) add(`operation:${api}/${n.operationId}`, n)
      }
      if (n.kind === 'InvokeFlowAction' && str(n.flowId)) add(`flow:${n.flowId}`, n)
      if ((n.kind === 'BeginDialog' || n.kind === 'ReplaceDialog') && str(n.dialog)) {
        const d = n.dialog as string
        if (d.startsWith('=')) {
          if (d.includes('Switch(')) add('ms:dynamic-topic-redirect', n)
        } else calls.push({ topic: `${child ?? ''}/${last(d, '.topic.')}`, into: facts, at: { file: f.path, line: r.lineOf(n) } }) // a topic's own schema prefix is dropped
      }
      const reads = (x: unknown) => typeof x === 'string' && x.includes('System.Activity.ChannelId')
      if ((n.kind === 'ConditionGroup' && list(n.conditions).some((c) => reads(obj(c)?.condition))) || (n.kind === 'SetVariable' && reads(n.value))) add('ms:channel-aware-behavior', n)
      if ((n.kind === 'SendActivity' || n.kind === 'Question') && JSON.stringify(n).includes('<br')) add('ms:line-breaks-in-messages', n)
    }
  }
  if (knowledge.length) agent.facts[`knowledge:count=${knowledge.length}`] = knowledge
  // «the fallback leads to escalation» is part of escalating (reaches:OnEscalate); a topic not found keeps its name
  for (const c of calls) {
    const trigger = triggers.get(c.topic)
    ;(c.into[trigger ? `reaches:${trigger}` : `calls:topic:${last(c.topic, '/')}`] ??= []).push(c.at)
  }
  // a key seen twice in the same place is one fact
  for (const facts of [agent.facts, ...agent.children.map((c) => c.facts)])
    for (const [k, v] of Object.entries(facts)) facts[k] = v.filter((s, i) => v.findIndex((x) => x.file === s.file && x.line === s.line) === i)
  return agent
}
