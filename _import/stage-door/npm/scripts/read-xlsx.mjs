// Reads the sheets of an .xlsx as rows of text, with nothing but Node: the zip (stored or deflated, as Excel, Numbers
// and LibreOffice save it), the workbook's sheet names in order, the shared strings, and each cell by its reference (an
// empty cell is "", a number is its text, a formula its last value). Enough to read back what workbook.ts wrote.
import { inflateRawSync } from 'node:zlib'

/** The zip's files, by name. */
function unzip(buf) {
  // the central directory: the end record is in the last 64 KB
  let end = -1
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) if (buf.readUInt32LE(i) === 0x06054b50) { end = i; break }
  if (end < 0) throw new Error('not an .xlsx (no zip directory)')
  const count = buf.readUInt16LE(end + 10)
  let at = buf.readUInt32LE(end + 16)
  const files = new Map()
  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(at) !== 0x02014b50) throw new Error('not an .xlsx (a broken zip directory)')
    const method = buf.readUInt16LE(at + 10)
    const size = buf.readUInt32LE(at + 20)
    const [nameLen, extraLen, commentLen] = [buf.readUInt16LE(at + 28), buf.readUInt16LE(at + 30), buf.readUInt16LE(at + 32)]
    const local = buf.readUInt32LE(at + 42)
    const name = buf.toString('utf8', at + 46, at + 46 + nameLen)
    const start = local + 30 + buf.readUInt16LE(local + 26) + buf.readUInt16LE(local + 28)
    const raw = buf.subarray(start, start + size)
    if (method === 0) files.set(name, raw)
    else if (method === 8) files.set(name, inflateRawSync(raw))
    else throw new Error(`${name}: a zip method this reader does not know (${method})`)
    at += 46 + nameLen + extraLen + commentLen
  }
  return files
}

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }
const unescape = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) => (e[0] === '#' ? String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : Number(e.slice(1))) : (ENTITIES[e] ?? m)))
// The text of a string item: its <t> runs joined (a rich text has several), phonetic hints (<rPh>) left out.
const textOf = (xml) => unescape([...xml.replace(/<rPh\b[\s\S]*?<\/rPh>/g, '').matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>|<t(?:\s[^>]*)?\/>/g)].map((m) => m[1] ?? '').join(''))
const attr = (tag, name) => tag.match(new RegExp(`\\s${name}="([^"]*)"`))?.[1]
// A column's letters to its index (A → 0, AA → 26).
const columnIndex = (ref) => [...ref.replace(/\d+$/, '')].reduce((n, c) => n * 26 + c.charCodeAt(0) - 64, 0) - 1

/** The sheets of the .xlsx in `buf`, in the workbook's order: { name, rows: string[][] }. */
export function readXlsx(buf) {
  const files = unzip(buf)
  const text = (p) => files.get(p)?.toString('utf8')
  const workbook = text('xl/workbook.xml')
  if (!workbook) throw new Error('not an .xlsx (no xl/workbook.xml)')
  const rels = new Map([...(text('xl/_rels/workbook.xml.rels') ?? '').matchAll(/<Relationship\b[^>]*>/g)].map(([t]) => [attr(t, 'Id'), attr(t, 'Target')]))
  const shared = [...(text('xl/sharedStrings.xml') ?? '').matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) => textOf(m[1]))
  return [...workbook.matchAll(/<sheet\b[^>]*>/g)].map(([tag]) => {
    const target = rels.get(attr(tag, 'r:id')) ?? ''
    const path = target.startsWith('/') ? target.slice(1) : `xl/${target.replace(/^\.\//, '')}`
    const xml = text(path) ?? ''
    const rows = []
    for (const [, rowAttrs, body] of xml.matchAll(/<row\b([^>]*?)(?:\/>|>([\s\S]*?)<\/row>)/g)) {
      const r = Number(attr(rowAttrs, 'r') ?? rows.length + 1) - 1
      const cells = []
      for (const [, cellAttrs, inner = ''] of (body ?? '').matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
        const ref = attr(cellAttrs, 'r')
        const c = ref ? columnIndex(ref) : cells.length
        const type = attr(cellAttrs, 't')
        const v = inner.match(/<v>([\s\S]*?)<\/v>/)?.[1]
        cells[c] = type === 's' ? (shared[Number(v)] ?? '') : type === 'inlineStr' ? textOf(inner.match(/<is>([\s\S]*?)<\/is>/)?.[1] ?? '') : type === 'b' ? (v === '1' ? 'TRUE' : 'FALSE') : unescape(v ?? '')
      }
      rows[r] = Array.from(cells, (x) => x ?? '')
    }
    return { name: unescape(attr(tag, 'name') ?? ''), rows: Array.from(rows, (x) => x ?? []) }
  })
}
