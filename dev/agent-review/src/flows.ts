// What a Power Automate flow uses, from its workflow.json alone: the connectors and operations it calls, the hosts it
// calls by HTTP, whether it calls another flow, and whether it answers the agent that called it. The actions are walked
// inside scopes, conditions (actions and else), switches (cases and default) and loops. What it does with them is not
// read, and neither are its secrets: that is for security tools.

type Obj = Record<string, unknown>
const obj = (x: unknown): Obj | undefined => (x && typeof x === 'object' && !Array.isArray(x) ? (x as Obj) : undefined)
const str = (x: unknown): string | undefined => (typeof x === 'string' && x.trim() ? x : undefined)

export interface FlowUse { key: string; action: string }
export interface FlowRead { uses: FlowUse[]; returns?: string }

/** The definition, in `properties.definition` (a solution export) or in `definition`; undefined when it is neither. */
export function definitionOf(json: unknown): Obj | undefined {
  const d = obj(obj(obj(json)?.properties)?.definition) ?? obj(obj(json)?.definition)
  return d && (obj(d.actions) || obj(d.triggers)) ? d : undefined
}

function* actions(map: unknown): Generator<[string, Obj]> {
  for (const [name, a] of Object.entries(obj(map) ?? {})) {
    const o = obj(a)
    if (!o) continue
    yield [name, o]
    yield* actions(o.actions)
    yield* actions(obj(o.else)?.actions)
    for (const c of Object.values(obj(o.cases) ?? {})) yield* actions(obj(c)?.actions)
    yield* actions(obj(o.default)?.actions)
  }
}

const hostOf = (uri: string) => /^https?:\/\/([^/?#:@]+)/i.exec(uri)?.[1]?.toLowerCase()
const last = (s: string) => s.slice(s.lastIndexOf('/') + 1)

export function readFlow(json: unknown): FlowRead | undefined {
  const d = definitionOf(json)
  if (!d) return undefined
  const out: FlowRead = { uses: [] }
  const use = (key: string, action: string) => out.uses.some((u) => u.key === key) || out.uses.push({ key, action })
  for (const [name, a] of actions(d.actions)) {
    const inputs = obj(a.inputs)
    const host = obj(inputs?.host)
    switch (a.type) {
      case 'OpenApiConnection':
      case 'OpenApiConnectionWebhook': {
        const api = str(host?.apiId) ? last(host!.apiId as string) : str(host?.connectionName)
        if (!api) break
        use(`connector:${api}`, name)
        if (str(host?.operationId)) use(`operation:${api}/${host!.operationId}`, name)
        break
      }
      case 'Http': {
        // a URI built by an expression has no host to say
        const h = str(inputs?.uri) && hostOf(inputs!.uri as string)
        if (h) use(`http:${h}`, name)
        break
      }
      case 'Workflow':
        use('child-flow', name)
        break
      case 'Response':
        out.returns ??= name
        break
    }
  }
  return out
}

/** The line an action is named on in the JSON text (its key), or 1. */
export function lineOfAction(text: string, name: string): number {
  const at = text.indexOf(`${JSON.stringify(name)}:`)
  return at < 0 ? 1 : text.slice(0, at).split('\n').length
}
