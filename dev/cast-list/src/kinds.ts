// The kinds the Copilot Studio schema knows, read the way Microsoft's own schema reader reads them (every `kind` given as
// a const or an enum, at any depth). With it the extractor tells a real kind it does not use, which it leaves alone,
// from one that does not exist, which goes to «what the analysis did not understand».

type Json = unknown

export function knownKinds(schema: { definitions?: Record<string, Json> }): Set<string> {
  const kinds = new Set<string>()
  const take = (k: unknown) => {
    if (!k || typeof k !== 'object') return
    const { const: one, enum: many } = k as { const?: unknown; enum?: unknown }
    if (typeof one === 'string') kinds.add(one)
    if (Array.isArray(many)) for (const x of many) if (typeof x === 'string') kinds.add(x)
  }
  const walk = (o: Json): void => {
    if (Array.isArray(o)) return o.forEach(walk)
    if (!o || typeof o !== 'object') return
    const obj = o as Record<string, Json>
    take(obj.kind)
    take((obj.properties as Record<string, Json> | undefined)?.kind)
    for (const v of Object.values(obj)) walk(v)
  }
  for (const d of Object.values(schema.definitions ?? {})) walk(d)
  return kinds
}
