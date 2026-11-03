// The stage (the light plot), with no model: the cast as nodes and arrows in columns, the traffic of each one from the
// export, the patterns as lenses and one scene per call of the orchestrator — on the full example.
import { stageOf } from '../src/stage'
import { fired, found, run } from './example'
import { done, ok } from './ok'

const { result, looks } = run()
const st = stageOf(result, looks, found, fired)
const node = (id: string) => st.nodes.find((n) => n.id === id)
const edge = (from: string, to: string) => st.edges.find((e) => e.from === from && e.to === to)
// a condition with optional parts: undefined is not met
const yes = (cond: unknown, what: string, detail?: unknown) => ok(!!cond, what, detail)
const AGENT = /\bagentes?\b|\bagents?\b/i

// the nodes
ok(['client', 'bodega-orquestrador', 'bodega-pedidos', 'bodega-devolucoes', 'bodega-cupons', 'bodega-loja-fisica', 'bodega-frete'].every((id) => node(id)), 'the customer, the orchestrator and the five specialists', st.nodes.map((n) => n.id))
ok(node('cr7b2_bodegaFidelidade')?.kind === 'ghost' && node('cr7b2_bodegaFidelidade')?.label === 'Bodega Azul - Fidelidade', 'fidelidade: called, not in the folder, dashed', node('cr7b2_bodegaFidelidade'))
const flows = st.nodes.filter((n) => n.kind === 'flow')
ok(flows.filter((f) => f.label === 'Abrir chamado no ERP').length === 1 && flows.some((f) => f.label === 'Listar lojas' && f.unused), 'the ERP flow is one node for three; «Listar lojas», which nobody calls, dashed', flows)
const dataverse = st.nodes.find((n) => n.id === 'sys:connector:shared_commondataserviceforapps')
ok(!!dataverse?.unused && st.nodes.some((n) => n.kind === 'system' && n.label === 'erp.bodega-azul.example' && !n.unused), 'the Dataverse connector (its API name: the files give no other) dashed, as only the unused flow reaches it; the ERP host not', [dataverse, st.nodes.filter((n) => n.kind === 'system').map((n) => n.label)])
yes(node('bodega-cupons')?.sub.pt.includes('transação') && node('bodega-cupons')?.sub.pt.includes('orientação') && st.nodes.filter((n) => n.id === 'bodega-cupons').length === 1, 'cupons once, with its two types', node('bodega-cupons'))
ok(st.groups.map((g) => g.label).join() === 'transação,orientação,triagem', 'the specialists in bands by type', st.groups)

// the arrows
const frete = edge('bodega-orquestrador', 'bodega-frete')!
ok(frete.tone === 'bad' && frete.label?.pt === 'SEM histórico · SEM «CategoriaSolicitacao»', "frete's arrow is red: no history, no category", frete)
ok(edge('bodega-orquestrador', 'bodega-cupons')?.tone === 'amber' && edge('bodega-orquestrador', 'bodega-cupons')?.label?.pt === 'roteado por «Cupons.»', "cupons' arrow: routed by a 7-character description", edge('bodega-orquestrador', 'bodega-cupons'))
ok(edge('bodega-orquestrador', 'cr7b2_bodegaFidelidade')?.tone === 'ghost' && edge('bodega-orquestrador', 'cr7b2_bodegaFidelidade')?.label?.pt === 'chama, mas não está na pasta', 'the call to fidelidade: dashed')
const cupFlow = st.edges.find((e) => e.from === 'bodega-cupons' && st.nodes.find((n) => n.id === e.to)?.kind === 'flow')
ok(cupFlow?.tone === 'amber' && cupFlow.label?.pt === 'não devolve nada', "cupons' flow returns nothing", cupFlow)
ok(st.edges.some((e) => e.from === 'bodega-cupons' && e.label?.en === 'GetItems'), "cupons → SharePoint, with the operation", st.edges.filter((e) => e.from === 'bodega-cupons'))

// the traffic
ok(node('bodega-orquestrador')?.volume === 1840 && node('bodega-pedidos')?.volume === 610 && node('bodega-devolucoes')?.volume === 402 && node('bodega-cupons')?.volume === 290 && node('bodega-frete')?.volume === 355, 'the topic starts of each, from the export', st.nodes.map((n) => [n.id, n.volume]))
ok(node('bodega-loja-fisica')?.silent === true && node('bodega-loja-fisica')?.volume === undefined && edge('bodega-orquestrador', 'bodega-loja-fisica')?.dashed === true, 'loja-fisica: no line in the telemetry, no volume, a dashed arrow', [node('bodega-loja-fisica'), edge('bodega-orquestrador', 'bodega-loja-fisica')])
ok(edge('client', 'bodega-orquestrador')?.volume === 1840 && edge('bodega-orquestrador', 'bodega-pedidos')?.volume === 610 && st.edges.filter((e) => e.kind === 'structure').every((e) => e.volume === undefined), 'the arrows into each carry its volume; the structure carries none', st.edges.map((e) => [e.from, e.to, e.kind, e.volume]))
const bare = run([], false)
const st0 = stageOf(bare.result, bare.looks, found)
ok(!st0.hasTelemetry && st0.nodes.every((n) => n.volume === undefined && !n.silent), 'with no export, no volume and nobody silent')

// the lenses
const lens = (k: string) => st.lenses.find((l) => l.id === k)
const escalate = st.lenses.find((l) => l.id === 'pattern:trigger:OnEscalate')
ok(!!escalate && escalate.bad.join() === 'bodega-frete' && escalate.ok.length === 5, 'the escalation lens: five follow it, frete is off', escalate)
yes(lens('contract')?.bad.join() === 'bodega-frete' && lens('contract')?.amber.includes('bodega-cupons'), 'the contract lens: frete off, cupons to decide', lens('contract'))
yes(lens('telemetry')?.bad.includes('bodega-loja-fisica') && lens('telemetry')?.amber.includes('bodega-cupons') && lens('telemetry')?.amber.includes('bodega-frete'), 'the telemetry lens: loja-fisica off; cupons and frete to look at', lens('telemetry'))
ok(lens('unused')?.amber.sort().join() === 'bodega-frete,bodega-loja-fisica,bodega-pedidos', 'the unused lens: frete, loja-fisica, pedidos', lens('unused'))
ok(st.lenses.every((l) => l.name.en && l.name.pt && l.caption.en && l.caption.pt), 'every lens named and told, in both languages')

// the scenes
ok(st.scenes.length === 6, 'six scenes: one per call of the orchestrator', st.scenes.map((s) => s.title.pt))
const sFrete = st.scenes.find((s) => s.to === 'bodega-frete')!
ok(sFrete.steps.some((x) => x.node === 'bodega-frete' && x.warn && x.text.pt.includes('SEM o histórico')), "frete's scene stops on the contract", sFrete.steps)
const sFid = st.scenes.find((s) => s.to === 'cr7b2_bodegaFidelidade')!
yes(sFid.steps[sFid.steps.length - 1].node === 'cr7b2_bodegaFidelidade' && sFid.steps[sFid.steps.length - 1].warn, "fidelidade's scene ends on the dashed one", sFid.steps)
const sCup = st.scenes.find((s) => s.to === 'bodega-cupons')!
ok(sCup.steps.some((x) => x.node === 'bodega-orquestrador' && x.warn) && sCup.steps.some((x) => st.nodes.find((n) => n.id === x.node)?.kind === 'flow' && x.warn), "cupons' scene: the short routing description, the flow that returns nothing", sCup.steps)

// the actor card
const aFrete = st.actors.find((a) => a.id === 'bodega-frete')!
ok(aFrete.fingerprint.some((f) => f.kind === 'variant') && aFrete.fingerprint.some((f) => f.kind === 'own') && aFrete.checks.some((c) => c.state === 'off' && c.key === 'trigger:OnEscalate'), "frete's card: a variation in its fingerprint; off the escalation", aFrete)

// knowledge on stage, and in the scene
ok(st.nodes.some((n) => n.id === 'sys:knowledge:SharePointSearchSource' && n.labels?.pt === 'Conhecimento no SharePoint') && st.scenes.find((s) => s.to === 'bodega-frete')!.steps.some((x) => x.node === 'sys:knowledge:SharePointSearchSource' && x.text.pt === 'Consulta «Conhecimento no SharePoint».'), 'the knowledge source is on stage, and frete looks it up in its scene')
ok(st.nodes.some((n) => n.id === 'sys:connector:shared_commondataserviceforapps' && n.label === 'Microsoft Dataverse'), "a connector the files do not name, by Microsoft's name")

// the review of access on the card
ok(st.actors.find((a) => a.id === 'bodega-cupons')!.access.some((x) => x.pt.includes('SharePoint')), "cupons' card asks about the access only it has in its type")

// the words
const words = JSON.stringify([st.lenses.map((l) => [l.name, l.caption]), st.edges.map((e) => e.label), st.scenes.map((s) => [s.title, s.steps.map((x) => x.text)]), st.nodes.map((n) => n.sub)])
ok(!AGENT.test(words), 'never «agent» in its own words', words.match(/.{0,40}\bagentes?\b.{0,20}/i)?.[0])
ok(JSON.stringify(stageOf(result, looks, found, fired)) === JSON.stringify(st), 'the same run, the same stage')
done()
