// What a telemetry event says, from the node that logs it (LogCustomTelemetryEvent): its form — the name with the
// agent's own name taken out, so «BodegaPedidos_OnError» and «BodegaFrete_OnError» are one event, «{agent}_OnError» —
// and the fields of its record (`properties: "={A: x, B: y}"`). A name or a record made by a formula cannot be read.

/** Lower case, with no accents and no `_`, `-`, `.` or space: how two spellings of one name are told to be the same. */
export const normal = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[\s._-]+/g, '')

export const AGENT = '{agent}'

/** The event's name with the first of the agent's names in it taken out: the folder, the schema name with no prefix,
 * the display name — each matched with no case, accents or separators. A name with none of them is its own form. */
export function formOf(name: string, agent: { id: string; schemaName?: string; displayName?: string }): string {
  // the plain letters of the name, each with where it is in the name
  const plain: { c: string; at: number }[] = []
  for (let at = 0; at < name.length; at++) for (const c of normal(name[at])) plain.push({ c, at })
  const text = plain.map((p) => p.c).join('')
  // a schema name without its publisher's prefix (cr7b2_bodegaPedidos → bodegaPedidos)
  const schema = agent.schemaName?.slice(agent.schemaName.indexOf('_') + 1)
  const ids = [...new Set([agent.id, schema, agent.displayName].filter((n): n is string => !!n).map(normal).filter((n) => n.length >= 3))]
    .sort((a, b) => b.length - a.length)
  for (const id of ids) {
    const i = text.indexOf(id)
    if (i < 0) continue
    const start = plain[i].at
    const end = plain[i + id.length - 1].at + 1
    return `${name.slice(0, start)}${AGENT}${name.slice(end)}`
  }
  return name
}

/** The names of a Power Fx record's fields (`={A: x, "B c": y, D: {E: 1}}` → A, B c, D), or undefined when it is not
 * a plain record. */
export function fieldsOf(properties: unknown): string[] | undefined {
  if (typeof properties !== 'string') return undefined
  const s = properties.trim().replace(/^=\s*/, '').trim()
  if (!s.startsWith('{') || !s.endsWith('}')) return undefined
  const body = s.slice(1, -1)
  const parts: string[] = []
  let depth = 0
  let quote: string | undefined
  let cur = ''
  for (let i = 0; i < body.length; i++) {
    const c = body[i]
    if (quote) {
      cur += c
      if (c === quote) {
        if (body[i + 1] === quote) cur += body[++i]
        else quote = undefined
      }
      continue
    }
    if (c === '"' || c === "'") quote = c
    else if (c === '{' || c === '(' || c === '[') depth++
    else if (c === '}' || c === ')' || c === ']') depth--
    if (c === ',' && depth === 0) {
      parts.push(cur)
      cur = ''
    } else cur += c
  }
  if (quote || depth) return undefined
  if (cur.trim()) parts.push(cur)
  const fields: string[] = []
  for (const p of parts) {
    const m = /^\s*(?:'((?:[^']|'')+)'|"((?:[^"]|"")+)"|([A-Za-z_][\w]*))\s*:/.exec(p)
    if (!m) return undefined
    fields.push((m[1] ?? m[2] ?? m[3]).replace(/''|""/g, (x) => x[0]))
  }
  return fields
}
