// Reading a skill's YAML file so every mistake can say its line: the document, where a path is in the file, and the
// two problems that stop reading at once (YAML that does not parse, a file that is not of this format). Part of the
// skills kit (visual-explainer/kit): a skill's esbuild puts it in its engine.mjs. Needs the `yaml` package.
//
// A file says what it is in one of two ways: DNA's header — `apiVersion: github.com/ruinosus/dna/v1`, `kind: <Kind>` and
// the name in `metadata.name` — or the format line it had before DNA (`format: stage-door/v1`…), still read. A reader
// gets the same `raw` either way: the DNA header becomes `format` and `name`, and `at(['name'])` finds the name where it
// is. upgradeHeader rewrites the old header as DNA's, keeping the rest of the text as it is.
import { isMap, LineCounter, parseDocument, type Document } from 'yaml'

export type Path = (string | number)[]

/** The owner of the kinds DNA invents (its thesis: an apiVersion names who owns the schema). */
export const DNA_API = 'github.com/ruinosus/dna/v1'

/** A problem the reader found before the skill's own checks: `syntax` (with YAML's code) or `format`. */
export type FormatProblem = { line: number; key: 'syntax'; detail: string } | { line: number; key: 'format' }

export interface Format {
  raw: Record<string, unknown>
  doc: Document
  /** The line where `path` (or the nearest part of it that is in the file) starts; 1 when none is. */
  at: (path: Path) => number
  /** The line of a position in the text (a node's `range[0]`). */
  lineOf: (offset: number) => number
  /** How the file said what it is: DNA's header, or the format line of before. */
  header: 'dna' | 'format'
}

export type Read = { ok: true; format: Format } | { ok: false; problem: FormatProblem }

/** Parses `text`, which must be a YAML map that is `kind` under DNA's header, or whose `format:` is `format`. */
export function readFormat(text: string, format: string, kind?: string): Read {
  const lines = new LineCounter()
  const doc = parseDocument(text, { lineCounter: lines, prettyErrors: false })
  let dna = false
  const at = (given: Path) => {
    const path = dna && given[0] === 'name' ? ['metadata', ...given] : dna && given[0] === 'format' ? ['apiVersion'] : given
    for (let p = path; p.length; p = p.slice(0, -1)) {
      const node = doc.getIn(p, true) as { range?: [number, number, number] } | undefined
      if (node?.range) return lines.linePos(node.range[0]).line
    }
    return 1
  }
  if (doc.errors.length) return { ok: false, problem: { line: lines.linePos(doc.errors[0].pos[0]).line, key: 'syntax', detail: doc.errors[0].code } }
  const raw = doc.toJS() as unknown
  const map = !!raw && typeof raw === 'object' && !Array.isArray(raw) && isMap(doc.contents) ? (raw as Record<string, unknown>) : undefined
  if (map && 'apiVersion' in map) {
    dna = true
    if (!kind || map.apiVersion !== DNA_API || map.kind !== kind) return { ok: false, problem: { line: at(['apiVersion']), key: 'format' } }
    const { apiVersion: _a, kind: _k, metadata, ...rest } = map // eslint-disable-line @typescript-eslint/no-unused-vars -- the header, read
    const name = metadata && typeof metadata === 'object' && !Array.isArray(metadata) ? (metadata as Record<string, unknown>).name : undefined
    return { ok: true, format: { raw: { format, ...(name === undefined ? {} : { name }), ...rest }, doc, at, lineOf: (offset) => lines.linePos(offset).line, header: 'dna' } }
  }
  if (!map || map.format !== format) return { ok: false, problem: { line: at(['format']), key: 'format' } }
  return { ok: true, format: { raw: map, doc, at, lineOf: (offset) => lines.linePos(offset).line, header: 'format' } }
}

/** The old header as DNA's: `format: <format>` becomes `apiVersion` and `kind`, and a top-level `name:` line moves to
 * `metadata.name` where it was — comments, order and the rest of the text as they are. Undefined when the text is not of
 * that format, or already DNA's. */
export function upgradeHeader(text: string, format: string, kind: string): string | undefined {
  const lines = text.split('\n')
  const at = lines.findIndex((l) => new RegExp(`^format:\\s*["']?${format.replace(/[/.]/g, (c) => `\\${c}`)}["']?\\s*(#.*)?$`).test(l))
  if (at < 0 || lines.some((l) => /^apiVersion:/.test(l))) return undefined
  lines.splice(at, 1, `apiVersion: ${DNA_API}`, `kind: ${kind}`)
  const n = lines.findIndex((l) => /^name:\s*\S/.test(l))
  if (n >= 0) lines.splice(n, 1, 'metadata:', `  name:${lines[n]!.slice('name:'.length)}`)
  return lines.join('\n')
}
