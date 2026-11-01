// The drill read with its lines, the review of its graph, a game played to the end, its debrief and the facilitator's
// script — on the example, and on small broken copies of it.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { readDrill, problemText } from '../src/drill'
import { facilitator } from '../src/facilitator'
import { call, canDo, choose, clockAt, debrief, startPlay } from '../src/play'
import { reviewDrill } from '../src/review'

const dir = new URL('../../../skills/dress-rehearsal/examples/', import.meta.url)
const text = readFileSync(new URL('checkout.drill.yaml', dir), 'utf8')
const runbook = readFileSync(new URL('runbooks/checkout.md', dir), 'utf8')
const read = readDrill(text)
assert.deepEqual(read.problems, [])
const drill = read.drill!
assert.equal(drill.scenes.length, 9)
assert.equal(text.split('\n')[read.drawLines!.painel - 1].trim(), 'title Erros no pagamento', 'the drawing’s first line')

// a sound drill has nothing to look at
assert.deepEqual(reviewDrill(drill, runbook).map((l) => l.pt), [])

// errors say their line
const lineOf = (t: string, needle: string) => t.split('\n').findIndex((l) => l.includes(needle)) + 1
const broken = text.replace('go: investigando-lider', 'go: lider-sumiu')
const p = readDrill(broken).problems[0]
assert.equal(p.key, 'unknownScene')
assert.equal(p.line, lineOf(broken, 'go: lider-sumiu'))
assert.match(problemText(p, 'pt'), /lider-sumiu/)
const stuck = readDrill(text.replace('    end: worse\n', ''))
assert.ok(stuck.problems.some((x) => x.key === 'stuck'))
assert.equal(readDrill('format: other').problems[0].key, 'format')
assert.ok(readDrill(text.replace('calls: lider', 'calls: cto')).problems.some((x) => x.key === 'unknownRole'))
const noEnd = readDrill(text.replace(/end: (resolved|worse)/g, 'end: resolved').replace(/    end: resolved\n/g, '    choices:\n      - { label: x, go: alarme }\n'))
assert.ok(noEnd.problems.some((x) => x.key === 'noEnd'))

// what the review finds
const keys = (t: string, rb = runbook) => reviewDrill(readDrill(t).drill!, rb).map((l) => l.key)
assert.ok(keys(text.replace('    can: [reverter-deploy]\n', '')).includes('nobodyCan'))
assert.ok(keys(text.replace(/        notifies: true\n/g, '')).includes('nobodyTold'))
assert.ok(keys(text.replace('        calls: lider\n', '')).includes('escalateNowhere'))
assert.ok(keys(text, runbook.replace('## §4', '## 4')).includes('notInRunbook'))
assert.ok(keys(text.replace("      - label: Abrir o painel de pagamentos\n        go: painel\n", "      - label: Abrir o painel de pagamentos\n        go: dormiu\n")).includes('unreachable'))

// a game: the room cannot revert until Release is called; nobody told the customers
let g = startPlay(drill, 'pt')
assert.deepEqual(g.room, ['plantao'])
g = choose(drill, g, 0, 'pt') // open the panel
assert.equal(g.scene, 'painel')
assert.equal(clockAt(drill, g.minute), '03:14')
const revert = drill.scenes.find((s) => s.id === 'painel')!.choices![0]
assert.equal(canDo(drill, g, revert), false)
g = choose(drill, g, 0, 'pt')
assert.equal(g.scene, 'painel', 'blocked: still in the panel')
assert.deepEqual(g.blocked, [{ needs: 'reverter-deploy', minute: 2 }])
g = call(drill, g, 'release', 'pt')
assert.equal(clockAt(drill, g.minute), '03:17')
g = choose(drill, g, 0, 'pt') // revert
assert.equal(g.scene, 'revertido')
g = choose(drill, g, 1, 'pt') // close and go back to sleep
assert.equal(g.ended, 'resolved')
const d = debrief(drill, g, reviewDrill(drill, runbook), 'pt')
assert.deepEqual(d.numbers, { resolved: 10, lost: 150, calls: 1 })
assert.deepEqual(d.timeline.map((t) => t.at), ['03:12', '03:12', '03:14', '03:17', '03:17', '03:21', '03:22'])
assert.ok(d.gaps.some((x) => x.says === 'Neste jogo, ninguém avisou os afetados.'))
assert.ok(d.gaps.some((x) => /Aos 2 min foi preciso «reverter-deploy» e ninguém na sala podia \(pode: Release\)/.test(x.says)))
assert.ok(d.markdown.includes('- Até resolver: 10 min') && d.markdown.includes('- Até avisar os afetados: não aconteceu'))
assert.equal(d.csv.split('\n')[0], '"Melhoria","De onde"')

// the facilitator's script has every scene, in the order the players meet them
const f = facilitator(drill, [], 'pt')
assert.ok(f.indexOf('### alarme') < f.indexOf('### painel') && f.includes('### dormiu — fim: piorou'))
assert.ok(f.includes('**Reverter o deploy das 02:58** → revertido _(+4 min · +150 pedidos perdidos · precisa de reverter-deploy · runbook §2)_'))
console.log('drill checks ok')
