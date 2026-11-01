// The blueprint as a workbook: Summary, Blueprint (the layers in the rows, the moments in the columns, as on the map),
// Pains and actions, Promises, Systems — as sheets of rows the platform's xlsx writer turns into an .xlsx.
import type { Sheet as LibSheet, Value } from '@lib/ways/workbook'
import { xlsx } from '@lib/ways/xlsx'
import type { Blueprint, Doing } from './blueprint'
import type { Look } from './review'
import { FACES, FEEL_FILLS, WORDS, type Lang } from './words'

/** A sheet of rows; the xlsx writer reads its name, columns, rows and header. */
export interface Sheet extends Omit<LibSheet, 'key'> {
  key: 'summary' | 'blueprint' | 'pains' | 'promises' | 'systems'
}
/** The .xlsx of these sheets (the platform's writer: its own `key` names only the platform's sheets). */
export const workbookFile = (sheets: Sheet[]): Uint8Array => xlsx(sheets as unknown as LibSheet[])

const HEAD = { bold: true, fill: 'E8EEF7' }
const head = (titles: string[]): Value[] => titles.map((v) => ({ v, ...HEAD }))
const list = (xs: (string | undefined)[] | undefined) => (xs ?? []).filter(Boolean).join('; ')

export function workbookOf(b: Blueprint, looks: Look[], lang: Lang = 'en'): Sheet[] {
  const w = WORDS[lang]
  const actor = (id?: string) => b.actors.find((a) => a.id === id)?.name ?? id ?? ''
  const system = (id: string) => b.systems.find((s) => s.id === id)?.name ?? id
  const phase = (id: string) => b.phases.find((p) => p.id === id)?.name ?? id
  const doings = (ds?: Doing[]) => list((ds ?? []).map((d) => (d.actor ? `${d.does} (${actor(d.actor)})` : d.does)))
  const feel = (n?: number): Value => (n === undefined ? '' : { v: `${n} ${FACES[n]}`, fill: FEEL_FILLS[n], center: true })
  const summary: Sheet = {
    key: 'summary', name: w.summary, header: false,
    columns: [{ title: '', width: 24 }, { title: '', width: 90 }],
    rows: [
      [{ v: w.name, bold: true }, { v: b.name, bold: true }],
      [w.who, b.who],
      ...(b.about ? [['', { v: b.about, wrap: true }] as Value[]] : []),
      [w.phases, b.phases.map((p) => p.name).join(' → ')],
      [w.moments, b.moments.length],
      [],
      [{ v: w.look, bold: true }, looks.length ? '' : w.nothing],
      ...looks.map((l) => ['', { v: l[lang], wrap: true }] as Value[]),
    ],
  }
  const width = (s: string) => Math.max(14, Math.min(30, s.length + 4))
  const grid: Sheet = {
    key: 'blueprint', name: w.blueprint, header: true,
    columns: [{ title: '', width: 26 }, ...b.moments.map((m) => ({ title: m.customer, width: width(m.customer) }))],
    rows: [
      head(['', ...b.moments.map((m) => m.customer)]),
      [{ v: w.phase, bold: true }, ...b.moments.map((m) => phase(m.phase))],
      [{ v: w.feels, bold: true }, ...b.moments.map((m) => feel(m.feels))],
      [{ v: w.marks, bold: true }, ...b.moments.map((m) => list((m.marks ?? []).map((k) => (k === 'fail' ? `⚠ ${w.fail}` : `⏱ ${w.wait}`))))],
      [{ v: w.evidence, bold: true }, ...b.moments.map((m) => ({ v: list(m.evidence) || `(${w.none})`, wrap: true }))],
      [{ v: w.front, bold: true, fill: 'EAF1FF' }, ...b.moments.map((m) => ({ v: doings(m.front), wrap: true, fill: 'EAF1FF' }))],
      [{ v: w.back, bold: true, fill: 'F2ECFF' }, ...b.moments.map((m) => ({ v: doings(m.back), wrap: true, fill: 'F2ECFF' }))],
      [{ v: w.support, bold: true, fill: 'EEF3EE' }, ...b.moments.map((m) => ({ v: list((m.support ?? []).map(system)), wrap: true, fill: 'EEF3EE' }))],
      [{ v: w.promise, bold: true }, ...b.moments.map((m) => ({ v: m.promise ? `${m.promise.says}${m.promise.within ? ` (${m.promise.within})` : ''}` : '', wrap: true }))],
    ],
  }
  const pains: Sheet = {
    key: 'pains', name: w.painsActions, header: true,
    columns: [{ title: w.moment, width: 28 }, { title: w.feels, width: 8 }, { title: w.pain, width: 40 }, { title: w.source, width: 22 }, { title: w.action, width: 36 }, { title: w.owner, width: 16 }, { title: w.due, width: 12 }],
    rows: [],
  }
  pains.rows = [head(pains.columns.map((c) => c.title))]
  for (const m of b.moments) {
    const acts = b.actions.filter((a) => a.moment === m.id)
    const n = Math.max((m.pains ?? []).length, acts.length)
    for (let i = 0; i < n; i++) {
      const p = (m.pains ?? [])[i]
      const a = acts[i]
      pains.rows.push([i === 0 ? { v: m.customer, bold: true } : '', i === 0 ? feel(m.feels) : '', { v: p?.says ?? '', wrap: true }, p?.source ?? '', { v: a?.does ?? '', wrap: true }, actor(a?.owner), a?.due ?? ''])
    }
  }
  const promises: Sheet = {
    key: 'promises', name: w.promises, header: true,
    columns: [{ title: w.moment, width: 28 }, { title: w.promise, width: 44 }, { title: w.within, width: 16 }, { title: w.owner, width: 18 }],
    rows: [head([w.moment, w.promise, w.within, w.owner]), ...b.moments.filter((m) => m.promise).map((m) => [{ v: m.customer, bold: true }, { v: m.promise!.says, wrap: true }, m.promise!.within ?? '—', actor(m.promise!.owner) || '—'] as Value[])],
  }
  const systems: Sheet = {
    key: 'systems', name: w.systems, header: true,
    columns: [{ title: w.system, width: 28 }, { title: w.count, width: 10 }, { title: w.moments, width: 70 }],
    rows: [head([w.system, w.count, w.moments]), ...b.systems.map((s) => {
      const ms = b.moments.filter((m) => (m.support ?? []).includes(s.id))
      return [{ v: s.name, bold: true }, ms.length, { v: ms.map((m) => m.customer).join('; '), wrap: true }] as Value[]
    })],
  }
  return [summary, grid, pains, promises, systems]
}
