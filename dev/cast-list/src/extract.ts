// What an agent cloned from Copilot Studio has, as facts: a key («trigger:OnEscalate», «connector:shared_office365») and
// every file and line it was seen in. Files are told apart by their kind (a connected-agent TaskDialog may live in
// topics/ or actions/), except those known by their name: settings.mcs.yml and connectionreferences.mcs.yml, which may
// have none, and the files of uploaded knowledge (knowledge/files/: a .mcs.yml with only its metadata, beside the
// document itself, which is not read). The agent's icon is not read either. A child agent (agents/<Name>/) has its own facts. What
// cannot be read — broken YAML, an empty file, a kind the schema does not have, a file that is not YAML — goes to
// `unknown` with its path, and the rest is read all the same.
//
// Also: what the orchestrator passes each agent it calls (its contract), what each flow in workflows/ uses, and what
// nothing uses — a topic nobody can reach, a tool the model cannot choose, a variable no file names, a flow no node
// calls — and what was switched off. A switched-off node is not a fact: a disabled telemetry node is no telemetry.
import { lineOfAction, readFlow } from './flows'
import { fieldsOf, formOf } from './telemetry'
import { isMap, isScalar, isSeq, LineCounter, parseDocument, type Node } from 'yaml'

export interface Source { file: string; line?: number }
export type Facts = Record<string, Source[]>
export interface Unknown { file: string; why: 'yaml' | 'empty' | 'kind' | 'file' | 'json' | 'flow' | 'telemetry'; kind?: string }
/** One connected-agent action of an orchestrator: who it calls, with what. */
export interface Call { calls: string; /** The name the action gives it. */ name?: string; history: boolean; inputs: string[]; description: string; file: string; line?: number }
/** A flow in workflows/: what it uses (the keys of flow-uses:), whether it answers, and whether a node calls it. */
export interface Flow { id?: string; name: string; folder: string; uses: string[]; returns: boolean; called: boolean; file: string }
/** A telemetry event the agent logs: its name as written, its form (the agent's own name taken out: «{agent}_OnError»)
 * and the fields of its record (none when the record is a formula that cannot be read). */
export interface TelemetryEvent { name: string; form: string; fields?: string[]; file: string; line?: number }
/** A text the model reads: the instructions, or a topic's or an action's description for the model. */
export interface Text { source: 'instructions' | 'descriptions'; file: string; line: number; text: string }
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
  /** The texts of the agent itself (not its children), for the blocks and markers. */
  texts: Text[]
  /** The connected agents it calls, each with what it passes. */
  contract: Call[]
  flows: Flow[]
  telemetry: TelemetryEvent[]
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
function* nodes(x: unknown, off = false): Generator<Obj> {
  if (Array.isArray(x)) for (const y of x) yield* nodes(y, off)
  const o = obj(x)
  if (!o) return
  // a switched-off node, and what is inside it, says nothing; `off` asks for those nodes instead
  if (o.disabled === true) {
    if (off && typeof o.kind === 'string') yield o
    return
  }
  if (typeof o.kind === 'string' && !off) yield o
  for (const v of Object.values(o)) yield* nodes(v, off)
}

/** «cr7b2_bot.shared_office365.shared-office365-…» → «shared_office365». */
const apiOf = (ref: string) => ref.split('.')[1] ?? ref
// what follows the last `sep`; the whole string when there is none
const last = (s: string, sep: string) => (s.includes(sep) ? s.slice(s.lastIndexOf(sep) + sep.length) : s)
// a copy or a test left in the editor, or a copy per language: its text says nothing new
const NOISE = /(^|[\s._-])(copy|c[oó]pia|new|test|teste)([\s._-]|$)|\.[a-z]{2}-[A-Z]{2}(\.topic)?\.mcs\.ya?ml$/i
const MAX_TEXT = 50_000
/** The line a key's text starts on: the next line for a block scalar (`|`, `>`), the key's own line otherwise. */
function textLine(source: string, key: string): number {
  const lines = source.split('\n')
  const at = lines.findIndex((l) => new RegExp(`^\\s*${key}:`).test(l))
  if (at < 0) return 1
  return /:\s*[|>][-+]?\s*$/.test(lines[at]) ? at + 2 : at + 1
}
const NODES = new Set(['LogCustomTelemetryEvent', 'CSATQuestion', 'SearchAndSummarizeContent', 'SearchKnowledgeSources'])
const KIND_OF_FOLDER: Record<string, string> = { topics: 'topic', actions: 'action', knowledge: 'knowledge', variables: 'variable' }
const FLOW_FILE = /^workflows\/([^/]+)\/(.+)$/
// a component's schema name: <agent schema>.<type>.<Name> (the type is topic, action, InvokeConnectedAgentTaskAction…)
const COMPONENT = /^[^.=]+\.([A-Za-z]+)\.(.+)$/
// the icon at the top of an agent, and the documents of its uploaded knowledge, beside their .mcs.yml
const ICON = /^(agents\/[^/]+\/)?icon\.png$/
const UPLOADED = /^(agents\/[^/]+\/)?knowledge\/files\//
// the id the extension appends to a flow's folder: a whole GUID, or a short one
const FOLDER_ID = /-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{6,})$/i

export function extractAgent(id: string, files: { path: string; text: string }[], kinds?: Set<string>): AgentFacts {
  const agent: AgentFacts = { id, facts: {}, children: [], unknown: [], names: {}, texts: [], contract: [], flows: [], telemetry: [] }
  let knowledge: Source[] = []
  // a topic that calls another (BeginDialog) reaches what that topic is for — its trigger, known once every file is read
  const triggers = new Map<string, string>()
  const calls: { topic: string; into: Facts; at: Source }[] = []
  // a topic can begin an action too (<schema>.action.<Name>, <schema>.InvokeConnectedAgentTaskAction.<Name>…): it has
  // to be among the agent's actions
  const actionCalls: { dialog: string; name: string; child: string; into: Facts; at: Source }[] = []
  const topicName = (path: string) => last(path, '/').replace(/(\.topic)?\.mcs\.ya?ml$|\.ya?ml$/, '')
  // what may turn out unused, known once every file is read
  const dialogs: string[] = []
  const lonely: { kind: 'topic' | 'action'; name: string; at: Source }[] = []
  const variables: { name: string; at: Source }[] = []
  // the events it logs, named once every file is read (the agent's names are in settings.mcs.yml)
  const events: { name: string; properties: unknown; at: Source }[] = []
  const flowFolders = new Map<string, { meta?: Obj; metaFile?: string; json: Record<string, { file: string; text: string; data: unknown }> }>()
  for (const f of [...files].sort((a, b) => a.path.localeCompare(b.path))) {
    const flow = FLOW_FILE.exec(f.path)
    if (flow && (/\.json$/.test(f.path) || /^metadata\.ya?ml$/.test(flow[2]))) {
      const folder = flowFolders.get(flow[1]) ?? { json: {} }
      flowFolders.set(flow[1], folder)
      if (/\.json$/.test(f.path)) {
        try {
          folder.json[flow[2]] = { file: f.path, text: f.text, data: JSON.parse(f.text) }
        } catch {
          agent.unknown.push({ file: f.path, why: 'json' })
        }
        continue
      }
      const m = read(f.text)
      if (m === 'yaml' || m === 'empty') agent.unknown.push({ file: f.path, why: m })
      else [folder.meta, folder.metaFile] = [obj(m.data), f.path]
      continue
    }
    if (!/\.ya?ml$/.test(f.path)) {
      if (!ICON.test(f.path) && !UPLOADED.test(f.path)) agent.unknown.push({ file: f.path, why: 'file' })
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

    if (/^connectionreferences\.mcs\.ya?ml$/.test(f.path.split('/').pop()!) && root) {
      for (const c of list(root.connectionReferences).map(obj)) {
        const api = str(c?.connectorId) ? last(c!.connectorId as string, '/') : str(c?.connectionReferenceLogicalName) ? apiOf(c!.connectionReferenceLogicalName as string) : undefined
        if (api) add(`connref:${api}`, c)
        if (api && str(c?.displayName)) agent.names[api] = c!.displayName as string
      }
      continue
    }
    if (UPLOADED.test(f.path) && root && typeof root.kind !== 'string') {
      add('knowledge:file')
      knowledge.push({ file: f.path, line: r.lineOf(root) })
      continue
    }

    // every kind in the file has to be one Copilot Studio knows; a made-up one is kept by name, and the rest is read
    const made = kinds ? [...nodes(root)].map((n) => n.kind as string).find((k) => !kinds.has(k)) : undefined
    if (made) agent.unknown.push({ file: f.path, why: 'kind', kind: made })
    if (typeof root?.kind !== 'string') {
      if (!made) agent.unknown.push({ file: f.path, why: 'kind' })
      continue
    }
    // a component switched off: that it is there, and nothing else
    if (root.state === 'Inactive' || root.status === 'Inactive') {
      add(`disabled:${KIND_OF_FOLDER[f.path.split('/')[child ? 2 : 0]] ?? 'component'}:${topicName(f.path)}`)
      continue
    }
    const text = f.text
    // the agent's own texts: never a child's, never a copy's
    const keepText = (source: Text['source'], key: string, value: unknown) => {
      if (child || !str(value) || NOISE.test(last(f.path, '/'))) return
      agent.texts.push({ source, file: f.path, line: textLine(text, key), text: (value as string).trimEnd().slice(0, MAX_TEXT) })
    }
    const instructions = (s: unknown, at: unknown) => {
      if (!str(s)) return
      add('instructions:present', at)
      if (/\b(Today|Now)\(\)/.test(s as string)) add('ms:date-context', at)
    }

    switch (root.kind) {
      case 'GptComponentMetadata': {
        agent.displayName ??= str(root.displayName)
        instructions(root.instructions, root)
        keepText('instructions', 'instructions', root.instructions)
        keepText('instructions', 'responseInstructions', root.responseInstructions)
        // the settings that change how it answers, only when the file says them
        const ai = obj(root.aISettings)
        const onOff = (v: unknown) => (v === true ? 'on' : 'off')
        if (typeof ai?.useModelKnowledge === 'boolean') add(`setting:model-knowledge=${onOff(ai.useModelKnowledge)}`, ai)
        if (str(ai?.contentModeration)) add(`setting:moderation=${(ai!.contentModeration as string).toLowerCase()}`, ai)
        if (typeof ai?.isSemanticSearchEnabled === 'boolean') add(`setting:semantic-search=${onOff(ai.isSemanticSearchEnabled)}`, ai)
        const caps = obj(root.gptCapabilities)
        if (typeof caps?.webBrowsing === 'boolean') add(`setting:web-browsing=${onOff(caps.webBrowsing)}`, caps)
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
        // a topic the model cannot pick (no description, no phrases) is reached only if another topic calls it
        const phrases = list(obj(begin?.intent)?.triggerQueries).length
        if (!child && trigger === 'OnRecognizedIntent' && !str(root.modelDescription) && !phrases) lonely.push({ kind: 'topic', name: topicName(f.path), at: { file: f.path, line: r.lineOf(root) } })
        keepText('descriptions', 'modelDescription', root.modelDescription)
        const silent = list(root.inputs).some((i) => obj(i)?.kind === 'AutomaticTaskInput' && obj(i)?.shouldPromptUser === false)
        if (trigger === 'OnRecognizedIntent' && silent) add('ms:orchestrator-variables', begin)
        if (trigger === 'OnError' && text.includes('System.Error.SubCode')) add('ms:rai-error-handling', begin)
        if (trigger === 'OnKnowledgeRequested' && [...nodes(begin)].some((n) => n.kind === 'SendActivity')) add('ms:knowledge-hold-message', begin)
        if (trigger === 'OnGeneratedResponse' && text.includes('System.ContinueResponse')) add('ms:prevent-tool-call-leaks', begin)
        break
      }
      case 'TaskDialog': {
        const a = obj(root.action)
        keepText('descriptions', 'modelDescription', root.modelDescription)
        if (!child && !str(root.modelDescription)) lonely.push({ kind: 'action', name: topicName(f.path), at: { file: f.path, line: r.lineOf(root) } })
        const ref = str(a?.connectionReference)
        if (a?.kind === 'InvokeConnectorTaskAction' && ref) {
          add(`connector:${apiOf(ref)}`, a)
          if (str(a.operationId)) add(`operation:${apiOf(ref)}/${a.operationId}`, a)
        }
        if (a?.kind === 'InvokeExternalAgentTaskAction' && obj(a.operationDetails)?.kind === 'ModelContextProtocolMetadata' && ref) add(`mcp:${apiOf(ref)}`, a)
        if (a?.kind === 'InvokeConnectedAgentTaskAction' && str(a.botSchemaName)) {
          add(`calls:${a.botSchemaName}`, a)
          if (!child)
            agent.contract.push({
              calls: a.botSchemaName as string,
              ...(str(root.modelDisplayName) ? { name: root.modelDisplayName as string } : {}),
              history: obj(a.historyType)?.kind === 'ConversationHistory',
              inputs: list(root.inputs).map((i) => str(obj(i)?.propertyName)).filter((x): x is string => !!x),
              description: str(root.modelDescription)?.trim() ?? '',
              file: f.path,
              line: r.lineOf(a),
            })
        }
        if (a?.kind === 'InvokeFlowTaskAction' && str(a.flowId)) {
          add(`flow:${a.flowId}`, a)
          // a flow is known by the action that calls it
          const name = str(root.modelDisplayName) ?? str(obj(root['mcs.metadata'])?.componentName)
          if (name) agent.names[a.flowId as string] ??= name
        }
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
        if (!child) variables.push({ name, at: { file: f.path, line: r.lineOf(root) } })
        break
      }
    }

    for (const n of nodes(root, true)) add(`disabled:node:${n.kind}`, n)
    // the nodes that say something, wherever they are
    for (const n of nodes(root)) {
      if (NODES.has(n.kind as string)) add(`node:${n.kind}`, n)
      if (n.kind === 'LogCustomTelemetryEvent' && !child) {
        // a name made by a formula says nothing to compare
        if (str(n.eventName) && !(n.eventName as string).trim().startsWith('=')) events.push({ name: (n.eventName as string).trim(), properties: n.properties, at: { file: f.path, line: r.lineOf(n) } })
        else agent.unknown.push({ file: f.path, why: 'telemetry' })
      }
      if (n.kind === 'InvokeConnectorAction' && str(n.connectionReference)) {
        const api = apiOf(n.connectionReference as string)
        add(`connector:${api}`, n)
        if (str(n.operationId)) add(`operation:${api}/${n.operationId}`, n)
      }
      if (n.kind === 'InvokeFlowAction' && str(n.flowId)) add(`flow:${n.flowId}`, n)
      if ((n.kind === 'BeginDialog' || n.kind === 'ReplaceDialog') && str(n.dialog)) {
        const d = n.dialog as string
        dialogs.push(d)
        if (d.startsWith('=')) {
          if (d.includes('Switch(')) add('ms:dynamic-topic-redirect', n)
        } else {
          const c = COMPONENT.exec(d)
          if (c && c[1] !== 'topic') actionCalls.push({ dialog: d, name: c[2], child: child ?? '', into: facts, at: { file: f.path, line: r.lineOf(n) } })
          else calls.push({ topic: `${child ?? ''}/${last(d, '.topic.')}`, into: facts, at: { file: f.path, line: r.lineOf(n) } }) // a topic's own schema prefix is dropped
        }
      }
      const reads = (x: unknown) => typeof x === 'string' && x.includes('System.Activity.ChannelId')
      if ((n.kind === 'ConditionGroup' && list(n.conditions).some((c) => reads(obj(c)?.condition))) || (n.kind === 'SetVariable' && reads(n.value))) add('ms:channel-aware-behavior', n)
      if ((n.kind === 'SendActivity' || n.kind === 'Question') && JSON.stringify(n).includes('<br')) add('ms:line-breaks-in-messages', n)
    }
  }
  if (knowledge.length) agent.facts[`knowledge:count=${knowledge.length}`] = knowledge
  for (const e of events) {
    const form = formOf(e.name, agent)
    const fields = fieldsOf(e.properties)
    ;(agent.facts[`telemetry:event:${form}`] ??= []).push(e.at)
    for (const field of fields ?? []) (agent.facts[`telemetry:field:${form}/${field}`] ??= []).push(e.at)
    agent.telemetry.push({ name: e.name, form, ...(fields ? { fields } : {}), ...e.at })
  }

  // the flows: what each uses counts only when a node of the agent calls it; one nobody calls is unused
  const calledFlows = new Set([agent.facts, ...agent.children.map((c) => c.facts)].flatMap((fs) => Object.keys(fs)).filter((k) => k.startsWith('flow:')).map((k) => k.slice(5)))
  for (const [folder, { meta, metaFile, json }] of [...flowFolders].sort(([a], [b]) => a.localeCompare(b))) {
    // jsonFileName is the file's name, or its path from the agent's folder (workflows/<folder>/workflow.json)
    const fileName = str(meta?.jsonFileName) ? last(meta!.jsonFileName as string, '/') : Object.keys(json)[0]
    const j = fileName ? json[fileName] : undefined
    const id = str(meta?.workflowId)
    const key = folder.replace(FOLDER_ID, '')
    if (!j) {
      if (metaFile) agent.unknown.push({ file: metaFile, why: 'flow' })
      continue
    }
    const read = readFlow(j.data)
    if (!read || !id) {
      agent.unknown.push({ file: j.file, why: 'flow' })
      continue
    }
    // the extension's metadata.yml names it in `name`
    const name = str(meta?.name) ?? str(meta?.displayName) ?? str(obj(obj(j.data)?.properties)?.displayName) ?? key
    const called = calledFlows.has(id)
    agent.flows.push({ id, name, folder, uses: read.uses.map((u) => u.key), returns: !!read.returns, called, file: j.file })
    agent.names[id] ??= name
    if (!called) {
      ;(agent.facts[`orphan:flow:${key}`] ??= []).push({ file: metaFile ?? j.file, line: 1 })
      agent.names[key] ??= name
      continue
    }
    for (const u of read.uses) (agent.facts[`flow-uses:${u.key}`] ??= []).push({ file: j.file, line: lineOfAction(j.text, u.action) })
    if (read.returns) (agent.facts['flow-returns'] ??= []).push({ file: j.file, line: lineOfAction(j.text, read.returns) })
  }
  // a topic or a tool nobody calls; a variable no other file names (and then it is not a variable the agent has)
  for (const l of lonely) if (!dialogs.some((d) => d === l.name || d.endsWith(`.${l.name}`))) (agent.facts[`orphan:${l.kind}:${l.name}`] ??= []).push(l.at)
  for (const v of variables) {
    const named = files.some((f) => f.path !== v.at.file && new RegExp(`\\bGlobal\\.${v.name}\\b`).test(f.text))
    if (named) continue
    delete agent.facts[`var:${v.name}`]
    delete agent.facts[`var-in:${v.name}`]
    ;(agent.facts[`orphan:variable:${v.name}`] ??= []).push(v.at)
  }
  // «the fallback leads to escalation» is part of escalating (reaches:OnEscalate); a topic not found keeps its name
  for (const c of calls) {
    const trigger = triggers.get(c.topic)
    ;(c.into[trigger ? `reaches:${trigger}` : `calls:topic:${last(c.topic, '/')}`] ??= []).push(c.at)
  }
  // an action not found (in actions/, or topics/ or agents/ where a TaskDialog may live) is named in full: its schema prefix may
  // be another agent's
  // (a connected agent's action may also be a file of agents/, beside the folders of the child agents)
  const actions = new Set(files.map((f) => /^(?:agents\/([^/]+)\/)?(?:actions|topics)\/[^/]+$|^agents\/[^/]+\.mcs\.ya?ml$/.exec(f.path)).filter((m) => m).map((m) => `${m![1] ?? ''}/${topicName(m![0])}`))
  for (const c of actionCalls) if (!actions.has(`${c.child}/${c.name}`)) (c.into[`calls:action:${c.dialog}`] ??= []).push(c.at)
  // a key seen twice in the same place is one fact
  for (const facts of [agent.facts, ...agent.children.map((c) => c.facts)])
    for (const [k, v] of Object.entries(facts)) facts[k] = v.filter((s, i) => v.findIndex((x) => x.file === s.file && x.line === s.line) === i)
  return agent
}
