// Workday's REST APIs, from their OpenAPI 2.0 (Swagger) files: an endpoint per method and path, with what Workday's own
// description says about it — the security domains («Secured By Domain:») and the scope («Scope:») —, its parameters
// (and what an ID accepts: a WID, a Reference ID, `me`), its body and its response as trees. Facts of the specification,
// for the agent; the request the Copilot Studio connector's «Execute REST request (Preview)» sends is in workflows.
import { LookupError } from './render.mjs'

export const METHODS = ['get', 'post', 'put', 'patch', 'delete']

const plain = (t) => (t ?? '').replace(/<[^>]+>/g, '').replace(/\\?~/g, '').replace(/\s+/g, ' ').trim()

/** «Secured By Domain: A, B» and «Scope: X, Y» from Workday's description of an endpoint. */
export function securityOf(description) {
  const text = (description ?? '').replace(/<[^>]+>/g, '')
  const list = (label) => {
    const m = new RegExp(`${label}:\\s*([^\\n]+)`, 'i').exec(text)
    return m ? m[1].split(/,\s*/).map((x) => x.trim()).filter(Boolean) : []
  }
  return { domains: list('Secured By Domain'), scope: list('Scope') }
}

/** What an ID parameter accepts, from its description: a WID, Reference ID types, named entries such as `me`. */
export function acceptsOf(param) {
  const d = param.description ?? ''
  if (!/Accepts:/i.test(d)) return null
  const refs = /Valid types:\s*([^\n]+)/i.exec(d)?.[1].split(/,\s*/).map((x) => x.trim()).filter(Boolean) ?? []
  const named = [...(/Named entry\*\*:\s*Valid values:\s*([^\n]+)/i.exec(d)?.[1] ?? '').matchAll(/`([^`]+)`/g)].map((m) => m[1])
  return { wid: /Workday ID/i.test(d), reference_id_types: refs, named }
}

/** The service and version of a spec, from its file name (staffing_v6_20261102_oas2.json) or its info. */
export function nameOf(spec, fileName = '') {
  const m = /^([A-Za-z]+)_(v\d+)/.exec(fileName)
  return { service: m?.[1] ?? spec.info?.title ?? 'rest', version: m?.[2] ?? spec.info?.version ?? 'v1' }
}

/** A REST spec (OpenAPI 2.0) as { service, version, prefix, endpoints, definitions }. prefix is what goes before the
 * path in the connector's relativePath, without the tenant (staffing/v6). */
export function parseOpenApi(spec, fileName = '') {
  if (spec.swagger !== '2.0' || !spec.paths) throw new Error(`${fileName || 'the file'}: not an OpenAPI 2.0 (Swagger) specification`)
  const { service, version } = nameOf(spec, fileName)
  const prefix = (spec.basePath ?? `/${service}/${version}`).replace(/^\/+/, '').replace(/^api\//, '').replace(/\/+$/, '')
  const endpoints = []
  for (const [path, ops] of Object.entries(spec.paths)) {
    const shared = ops.parameters ?? []
    for (const method of METHODS) {
      const o = ops[method]
      if (!o) continue
      const params = [...shared, ...(o.parameters ?? [])].map((p) => (p.$ref ? spec.parameters?.[p.$ref.split('/').pop()] ?? p : p))
      const body = params.find((p) => p.in === 'body')
      const ok = Object.entries(o.responses ?? {}).find(([code]) => /^2/.test(code))
      endpoints.push({
        method: method.toUpperCase(),
        path,
        summary: plain(o.summary),
        description: plain(o.description),
        tags: o.tags ?? [],
        ...securityOf(o.description),
        params: params.filter((p) => p.in !== 'body').map((p) => ({
          name: p.name, in: p.in, required: Boolean(p.required), type: p.type ?? null,
          ...(p.enum ? { enum: p.enum } : {}), ...(p.pattern ? { pattern: p.pattern } : {}),
          ...(acceptsOf(p) ? { accepts: acceptsOf(p) } : {}),
          description: plain(p.description).replace(/\s*Accepts:.*$/i, ''),
        })),
        body: body ? { name: body.name, required: Boolean(body.required), schema: body.schema ?? null } : null,
        response: ok ? { status: ok[0], schema: ok[1].schema ?? null } : null,
      })
    }
  }
  return { service, version, prefix, title: spec.info?.title ?? service, endpoints, definitions: spec.definitions ?? {} }
}

/** A JSON schema as a tree: { name, path, type, required, enum, readOnly, description, children, ref, recursive }.
 * $ref and allOf resolved against the spec's definitions; an array shows its items. */
export function jsonTree(definitions, schema, name = 'body', { maxDepth = 6 } = {}) {
  const resolve = (s, seen) => {
    let cur = s ?? {}
    let ref = null
    while (cur.$ref) {
      ref = cur.$ref.split('/').pop()
      if (seen.has(ref)) return { schema: {}, ref, recursive: true }
      cur = definitions[ref] ?? {}
    }
    if (cur.allOf) {
      const merged = { type: 'object', properties: {}, required: [] }
      for (const part of cur.allOf) {
        const r = resolve(part, seen).schema
        Object.assign(merged.properties, r.properties ?? {})
        merged.required.push(...(r.required ?? []))
        if (r.description && !merged.description) merged.description = r.description
      }
      if (cur.description) merged.description = cur.description
      cur = merged
    }
    return { schema: cur, ref, recursive: false }
  }
  const walk = (s, nm, path, required, depth, seen) => {
    const { schema: sc, ref, recursive } = resolve(s, seen)
    const node = { name: nm, path, type: sc.type ?? (sc.properties ? 'object' : null), required }
    if (sc.format) node.format = sc.format
    if (sc.enum) node.enum = sc.enum
    if (sc.readOnly) node.readOnly = true
    if (sc.description) node.description = plain(sc.description)
    if (ref) node.ref = ref
    if (recursive) {
      node.recursive = true
      return node
    }
    const next = new Set(seen)
    if (ref) next.add(ref)
    if (depth >= maxDepth) {
      if (sc.properties || sc.items) node.truncated = true
      return node
    }
    if (sc.type === 'array' || sc.items) {
      node.type = 'array'
      node.items = walk(sc.items ?? {}, '[]', `${path}[]`, false, depth + 1, next)
    }
    if (sc.properties) {
      const req = new Set(sc.required ?? [])
      node.children = Object.entries(sc.properties).map(([k, v]) => walk(v, k, path ? `${path}.${k}` : k, req.has(k), depth + 1, next))
    }
    return node
  }
  return walk(schema, name, '', true, 0, new Set())
}

/** A JSON tree as text, like the SOAP trees: required with no mark, ? optional, [] an array, ro read-only. */
export function renderJsonTree(node, { maxDepth = 4, docChars = 100 } = {}) {
  const lines = []
  const walk = (n, depth) => {
    const kind = n.type === 'array' ? `array of ${n.items?.type ?? 'object'}` : n.type ?? 'object'
    const bits = ['  '.repeat(depth) + (n.name || '(body)') + (n.required ? '' : '?'), `: ${kind}${n.format ? ` (${n.format})` : ''}`]
    if (n.enum) bits.push('{' + n.enum.slice(0, 8).join('|') + (n.enum.length > 8 ? '|…' : '') + '}')
    if (n.readOnly) bits.push('ro')
    if (n.recursive) bits.push('↻')
    if (n.description && docChars) bits.push('— ' + ([...n.description].length > docChars ? [...n.description].slice(0, docChars - 1).join('') + '…' : n.description))
    lines.push(bits.join(' '))
    const kids = n.type === 'array' ? n.items?.children : n.children
    if (kids?.length) {
      if (depth >= maxDepth) return void lines.push('  '.repeat(depth + 1) + `… ${kids.length} fields (increase depth)`)
      for (const c of kids) walk(c, depth + 1)
    } else if (n.truncated) lines.push('  '.repeat(depth + 1) + '… (more: increase depth)')
  }
  walk(node, 0)
  return 'card: (none)=required  ?=optional  array of …  ro=read-only  ↻=recursive\n' + lines.join('\n')
}

/** A field of a JSON tree by its dotted path, as the tree shows it (data[].id) or without the brackets (data.id). */
export function findJsonPath(root, path) {
  let cur = root
  for (const part of path.replace(/\[\]/g, '').split('.').filter(Boolean)) {
    const kids = cur.type === 'array' ? cur.items?.children ?? [] : cur.children ?? []
    const next = kids.find((c) => c.name === part)
    if (!next) throw new LookupError(`'${part}' is not a field of ${cur.path || '(the body)'}; its fields: ${kids.map((c) => c.name).join(', ') || '(none)'} (write a path as data[].id or data.id)`)
    cur = next
  }
  return cur
}

/** The words of a REST path, for the search: /workers/{ID}/timeOffPlans → workers time off plans. */
export const pathWords = (path) => path.replace(/\{[^}]+\}/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/[/_-]+/g, ' ').replace(/\s+/g, ' ').trim()
