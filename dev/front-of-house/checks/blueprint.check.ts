// The blueprint read with its lines, what the review finds (the return example on purpose has what to look at), the
// workbook's sheets and the lesson in chalk-talk's contract.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { validateScene } from '@lib/drawing/recipe'
import { readBlueprint, problemText } from '../src/blueprint'
import { lessonOf } from '../src/lesson'
import { reviewBlueprint } from '../src/review'
import { workbookFile, workbookOf } from '../src/workbook'

const dir = new URL('../../../skills/front-of-house/examples/', import.meta.url)
const text = readFileSync(new URL('devolucao.blueprint.yaml', dir), 'utf8')
const read = readBlueprint(text)
assert.deepEqual(read.problems, [])
const b = read.blueprint!
assert.equal(b.moments.length, 5)
assert.equal(b.who, 'Cliente da loja')

// the return blueprint, on purpose: the worst moment with no action, a failure where the customer hears nothing, a promise
// with no owner and no time
const looks = reviewBlueprint(b)
assert.deepEqual(looks.map((l) => `${l.key}:${l.moment ?? ''}`), ['worstNoAction:esperar', 'silentWait:esperar', 'promiseNoOwner:esperar', 'promiseNoTime:esperar'])
assert.match(looks[0].pt, /«Espera notícia — 6 dias sem nada» é o pior momento/)
// the gym one is sound
const gym = readBlueprint(readFileSync(new URL('gym-signup.blueprint.yaml', dir), 'utf8'))
assert.deepEqual(gym.problems, [])
assert.deepEqual(reviewBlueprint(gym.blueprint!).map((l) => l.en), [])
assert.deepEqual(gym.blueprint!.phases.map((p) => p.id), ['discover', 'join', 'first-week'], 'a phase given as a name')

// what each rule finds
const keys = (t: string) => reviewBlueprint(readBlueprint(t).blueprint!).map((l) => l.key)
assert.ok(keys(text.replace('    front: [Formulário guiado]\n    back: [{ actor: logistica, does: Regra de prazo confere o pedido }]\n    support: [pedidos]\n', '')).includes('nobodyBehind'))
assert.ok(keys(text.replace(', source: NPS (comentários)', '')).includes('painNoSource'))
assert.ok(keys(text.replace(', owner: logistica, due: 2026-12', '')).includes('actionNoOwner'))
assert.ok(keys(text.replace(/support: \[\w+\]/g, 'support: [pedidos]')).includes('systemEverywhere'))

// errors say their line
const lineOf = (t: string, needle: string) => t.split('\n').findIndex((l) => l.includes(needle)) + 1
const broken = text.replace('owner: financeiro, within', 'owner: tesouraria, within')
const p = readBlueprint(broken).problems[0]
assert.deepEqual([p.key, p.line], ['unknown', lineOf(broken, 'tesouraria')])
assert.match(problemText(p, 'pt'), /«reembolso» cita o ator «tesouraria», que não existe/)
assert.equal(readBlueprint(text.replace('feels: 2', 'feels: 9')).problems[0].key, 'feels')
assert.equal(readBlueprint(text.replace('support: [galpao]', 'support: [armazem]')).problems[0].key, 'unknown')
assert.equal(readBlueprint('format: x').problems[0].key, 'format')

// the workbook: the blueprint's layers in the rows, the moments in the columns
const sheets = workbookOf(b, looks, 'pt')
assert.deepEqual(sheets.map((s) => s.key), ['summary', 'blueprint', 'pains', 'promises', 'systems'])
const cell = (v: unknown) => String(typeof v === 'object' && v ? (v as { v: unknown }).v : v)
const grid = sheets[1].rows.map((r) => r.map(cell))
assert.deepEqual(grid[0].slice(1, 3), ['Pede a devolução em «Meus pedidos»', 'Recebe a etiqueta por e-mail'])
assert.equal(grid.find((r) => r[0] === 'Sente')![4], '1 😣')
assert.equal(grid.find((r) => r[0] === 'Evidência')![4], '(nada)')
const pains = sheets[2].rows.map((r) => r.map(cell))
assert.ok(pains.some((r) => r[2] === 'Fila de 40 minutos no correio' && r[4] === 'Oferecer coleta em casa' && r[5] === 'Logística'))
const bytes = workbookFile(sheets)
assert.equal(String.fromCharCode(bytes[0], bytes[1]), 'PK')

// the lesson: a recipe chalk-talk takes, a chapter per phase, a person per moment with its mood
const scene = validateScene(lessonOf(b, 'pt')) as { steps: { type: string; chapter?: string; mood?: string; name?: string }[] }
assert.deepEqual(scene.steps.filter((s) => s.chapter).map((s) => s.chapter), ['Pedir', 'Enviar', 'Receber'])
assert.deepEqual(scene.steps.filter((s) => s.name === 'person').map((s) => s.mood ?? '-'), ['-', 'happy', 'worried', 'sad', 'happy'])
console.log('blueprint checks ok')
