// Reading a skill's YAML file so every mistake can say its line: the document, where a path is in the file, and the
// two problems that stop reading at once (YAML that does not parse, a file that is not of this format). Part of the
// skills kit (chalk-talk/kit): a skill's esbuild puts it in its engine.mjs. Needs the `yaml` package.
import { isMap, LineCounter, parseDocument, type Document } from 'yaml'

export type Path = (string | number)[]

/** A problem the reader found before the skill's own checks: `syntax` (with YAML's code) or `format`. */
export type FormatProblem = { line: number; key: 'syntax'; detail: string } | { line: number; key: 'format' }

export interface Format {
  raw: Record<string, unknown>
  doc: Document
  /** The line where `path` (or the nearest part of it that is in the file) starts; 1 when none is. */
  at: (path: Path) => number
  /** The line of a position in the text (a node's `range[0]`). */
  lineOf: (offset: number) => number
}

export type Read = { ok: true; format: Format } | { ok: false; problem: FormatProblem }

/** Parses `text`, which must be a YAML map whose `format:` is `format`. */
export function readFormat(text: string, format: string): Read {
  const lines = new LineCounter()
  const doc = parseDocument(text, { lineCounter: lines, prettyErrors: false })
  const at = (path: Path) => {
    for (let p = path; p.length; p = p.slice(0, -1)) {
      const node = doc.getIn(p, true) as { range?: [number, number, number] } | undefined
      if (node?.range) return lines.linePos(node.range[0]).line
    }
    return 1
  }
  if (doc.errors.length) return { ok: false, problem: { line: lines.linePos(doc.errors[0].pos[0]).line, key: 'syntax', detail: doc.errors[0].code } }
  const raw = doc.toJS() as unknown
  if (!raw || typeof raw !== 'object' || Array.isArray(raw) || (raw as Record<string, unknown>).format !== format || !isMap(doc.contents)) {
    return { ok: false, problem: { line: at(['format']), key: 'format' } }
  }
  return { ok: true, format: { raw: raw as Record<string, unknown>, doc, at, lineOf: (offset) => lines.linePos(offset).line } }
}
