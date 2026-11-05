// Checks the curated notes against an index of Workday's real WSDLs (the repository has only synthetic ones):
// each «schema» note's evidence is a name the WSDLs have (an element, a type, an attribute, an enumeration value or an
// operation), each operation it says is absent is absent, and no field of the request is named after what it says the
// request lacks; each «description» note's quote is in Workday's description of the operation. Every note has a kind.
//
//   node dev/workday-integration/tools/check-notes.mjs [--index <folder>]   (the default index otherwise)
import { defaultIndexDir, Index } from '../src/index.mjs'
import { NOTES } from '../src/notes.mjs'
import { TreeBuilder } from '../src/render.mjs'

const at = process.argv.indexOf('--index')
const ix = new Index(at > 0 ? process.argv[at + 1] : defaultIndexDir())
if (ix.empty) {
  console.error(`✗ nothing indexed in ${ix.dir}: fetch or ingest Workday's WSDLs first`)
  process.exit(2)
}
const names = new Set(ix.data.operations.map((r) => r.op))
const services = Object.values(ix.data.schemas)
for (const s of services) {
  const reg = ix.registry(s.service, s.version)
  for (const k of ['elements', 'complex', 'simple', 'attributes', 'groups']) for (const n of Object.keys(reg[k])) names.add(n)
  for (const st of Object.values(reg.simple)) for (const v of st.enum ?? []) names.add(v)
  const walk = (items) => {
    for (const it of items ?? []) {
      if (it.kind === 'element' && it.name) names.add(it.name)
      walk(it.items)
    }
  }
  for (const ct of Object.values(reg.complex)) {
    walk(ct.content)
    for (const a of ct.attrs ?? []) if (a.name) names.add(a.name)
  }
}
const KINDS = new Set(['schema', 'description', 'inferred', 'sensitive', 'tenant'])
let bad = 0
let checked = 0
for (const [op, notes] of Object.entries(NOTES)) {
  for (const n of notes) {
    const off = []
    if (!KINDS.has(n.kind)) off.push(`kind ${n.kind}`)
    for (const e of n.evidence ?? []) if (!names.has(e)) off.push(`${e} is not in the WSDLs`)
    for (const a of n.absent ?? []) if (ix.data.operations.some((r) => r.op === a)) off.push(`${a} exists`)
    if (n.absentFields) {
      const row = ix.data.operations.find((r) => r.op === op && r.request_element)
      const reg = row && ix.registry(row.service, row.version)
      if (!reg) off.push(`${op}'s WSDL is not indexed`)
      else {
        const stack = [new TreeBuilder(reg).element(row.request_element)]
        while (stack.length) {
          const x = stack.pop()
          for (const f of n.absentFields) if (x.name.includes(f)) off.push(`${x.path} is named after ${f}`)
          stack.push(...x.children)
        }
      }
    }
    if (n.kind === 'schema' && !n.evidence && !n.absent && !n.absentFields) off.push('a schema note with nothing to check it by')
    if (n.kind === 'description') {
      const desc = ix.data.operations.filter((r) => r.op === op).map((r) => r.description).join(' ')
      if (!n.quote) off.push('a description note with no quote')
      else if (!desc.includes(n.quote)) off.push(`Workday's description does not say «${n.quote}»`)
    }
    checked++
    if (off.length) {
      bad++
      console.log(`✗ ${op}: «${n.text.slice(0, 80)}» — ${off.join('; ')}`)
    }
  }
}
console.log(`${bad ? '✗' : '✓'} ${checked - bad}/${checked} notes hold against ${ix.dir} (${services.length} WSDLs)`)
process.exit(bad ? 1 : 0)
