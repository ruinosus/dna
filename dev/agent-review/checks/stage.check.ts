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

// the nodes
ok(['client', 'rh-orquestrador', 'rh-ferias', 'rh-beneficios', 'rh-admissao', 'rh-facilities', 'rh-folha'].every((id) => node(id)), 'the customer, the orchestrator and the five specialists', st.nodes.map((n) => n.id))
ok(node('cr7b2_rhMobilidade')?.kind === 'ghost' && node('cr7b2_rhMobilidade')?.label === 'RH - Mobilidade', 'mobilidade: called, not in the folder, dashed', node('cr7b2_rhMobilidade'))
const flows = st.nodes.filter((n) => n.kind === 'flow')
ok(flows.filter((f) => f.label === 'Abrir caso no Workday').length === 1 && flows.some((f) => f.label === 'Listar unidades' && f.unused), 'the ERP flow is one node for three; «Listar unidades», which nobody calls, dashed', flows)
const dataverse = st.nodes.find((n) => n.id === 'sys:connector:shared_commondataserviceforapps')
ok(!!dataverse?.unused && st.nodes.some((n) => n.kind === 'system' && n.label === 'workday.empresa.example' && !n.unused), 'the Dataverse connector (its API name: the files give no other) dashed, as only the unused flow reaches it; the ERP host not', [dataverse, st.nodes.filter((n) => n.kind === 'system').map((n) => n.label)])
yes(node('rh-admissao')?.sub.pt.includes('transação') && node('rh-admissao')?.sub.pt.includes('orientação') && st.nodes.filter((n) => n.id === 'rh-admissao').length === 1, 'admissao once, with its two types', node('rh-admissao'))
ok(st.groups.map((g) => g.label).join() === 'transação,orientação,triagem', 'the specialists in bands by type', st.groups)

// the arrows
const folha = edge('rh-orquestrador', 'rh-folha')!
ok(folha.tone === 'bad' && folha.label?.pt === 'SEM histórico · SEM «CategoriaSolicitacao»', "folha's arrow is red: no history, no category", folha)
ok(edge('rh-orquestrador', 'rh-admissao')?.tone === 'amber' && edge('rh-orquestrador', 'rh-admissao')?.label?.pt === 'roteado por «Admissão.»', "admissao' arrow: routed by a 7-character description", edge('rh-orquestrador', 'rh-admissao'))
ok(edge('rh-orquestrador', 'cr7b2_rhMobilidade')?.tone === 'ghost' && edge('rh-orquestrador', 'cr7b2_rhMobilidade')?.label?.pt === 'chama, mas não está na pasta', 'the call to mobilidade: dashed')
const cupFlow = st.edges.find((e) => e.from === 'rh-admissao' && st.nodes.find((n) => n.id === e.to)?.kind === 'flow')
ok(cupFlow?.tone === 'amber' && cupFlow.label?.pt === 'não devolve nada', "admissao' flow returns nothing", cupFlow)
ok(st.edges.some((e) => e.from === 'rh-admissao' && e.label?.en === 'GetItems'), "admissao → SharePoint, with the operation", st.edges.filter((e) => e.from === 'rh-admissao'))

// the traffic
ok(node('rh-orquestrador')?.volume === 1840 && node('rh-ferias')?.volume === 610 && node('rh-beneficios')?.volume === 402 && node('rh-admissao')?.volume === 290 && node('rh-folha')?.volume === 355, 'the topic starts of each, from the export', st.nodes.map((n) => [n.id, n.volume]))
ok(node('rh-facilities')?.silent === true && node('rh-facilities')?.volume === undefined && edge('rh-orquestrador', 'rh-facilities')?.dashed === true, 'facilities: no line in the telemetry, no volume, a dashed arrow', [node('rh-facilities'), edge('rh-orquestrador', 'rh-facilities')])
ok(edge('client', 'rh-orquestrador')?.volume === 1840 && edge('rh-orquestrador', 'rh-ferias')?.volume === 610 && st.edges.filter((e) => e.kind === 'structure').every((e) => e.volume === undefined), 'the arrows into each carry its volume; the structure carries none', st.edges.map((e) => [e.from, e.to, e.kind, e.volume]))
const bare = run([], false)
const st0 = stageOf(bare.result, bare.looks, found)
ok(!st0.hasTelemetry && st0.nodes.every((n) => n.volume === undefined && !n.silent), 'with no export, no volume and nobody silent')

// the lenses
const lens = (k: string) => st.lenses.find((l) => l.id === k)
const escalate = st.lenses.find((l) => l.id === 'pattern:trigger:OnEscalate')
ok(!!escalate && escalate.bad.join() === 'rh-folha' && escalate.ok.length === 5, 'the escalation lens: five follow it, folha is off', escalate)
yes(lens('contract')?.bad.join() === 'rh-folha' && lens('contract')?.amber.includes('rh-admissao'), 'the contract lens: folha off, admissao to decide', lens('contract'))
yes(lens('telemetry')?.bad.includes('rh-facilities') && lens('telemetry')?.amber.includes('rh-admissao') && lens('telemetry')?.amber.includes('rh-folha'), 'the telemetry lens: facilities off; admissao and folha to look at', lens('telemetry'))
ok(lens('unused')?.amber.sort().join() === 'rh-facilities,rh-ferias,rh-folha', 'the unused lens: facilities, ferias, folha', lens('unused'))
ok(st.lenses.every((l) => l.name.en && l.name.pt && l.caption.en && l.caption.pt), 'every lens named and told, in both languages')

// the scenes, in short names: what every one shares («RH - ») left out
ok(st.scenes.map((s) => s.title.pt).sort().join() === 'Admissão,Benefícios,Facilities,Folha,Férias,Mobilidade' && sFolhaSteps().some((x) => x.text.pt === 'O orquestrador encaminha para Folha.'), 'the scenes by short names, in their buttons and steps', st.scenes.map((s) => s.title.pt))
function sFolhaSteps() { return st.scenes.find((s) => s.to === 'rh-folha')!.steps }
ok(st.scenes.length === 6, 'six scenes: one per call of the orchestrator', st.scenes.map((s) => s.title.pt))
const sFolha = st.scenes.find((s) => s.to === 'rh-folha')!
ok(sFolha.steps.some((x) => x.node === 'rh-folha' && x.warn && x.text.pt.includes('SEM o histórico')), "folha's scene stops on the contract", sFolha.steps)
const sFid = st.scenes.find((s) => s.to === 'cr7b2_rhMobilidade')!
yes(sFid.steps[sFid.steps.length - 1].node === 'cr7b2_rhMobilidade' && sFid.steps[sFid.steps.length - 1].warn, "mobilidade's scene ends on the dashed one", sFid.steps)
const sCup = st.scenes.find((s) => s.to === 'rh-admissao')!
ok(sCup.steps.some((x) => x.node === 'rh-orquestrador' && x.warn) && sCup.steps.some((x) => st.nodes.find((n) => n.id === x.node)?.kind === 'flow' && x.warn), "admissao' scene: the short routing description, the flow that returns nothing", sCup.steps)

// the actor card
const aFolha = st.actors.find((a) => a.id === 'rh-folha')!
ok(aFolha.fingerprint.some((f) => f.kind === 'variant') && aFolha.fingerprint.some((f) => f.kind === 'own') && aFolha.checks.some((c) => c.state === 'off' && c.key === 'trigger:OnEscalate'), "folha's card: a variation in its fingerprint; off the escalation", aFolha)

// knowledge on stage, and in the scene
ok(st.nodes.some((n) => n.id === 'sys:knowledge:SharePointSearchSource' && n.labels?.pt === 'Conhecimento no SharePoint') && st.scenes.find((s) => s.to === 'rh-folha')!.steps.some((x) => x.node === 'sys:knowledge:SharePointSearchSource' && x.text.pt === 'Consulta «Conhecimento no SharePoint».'), 'the knowledge source is on stage, and folha looks it up in its scene')
ok(st.nodes.some((n) => n.id === 'sys:connector:shared_commondataserviceforapps' && n.label === 'Microsoft Dataverse'), "a connector the files do not name, by Microsoft's name")

// the review of access on the card
ok(st.actors.find((a) => a.id === 'rh-admissao')!.access.some((x) => x.pt.includes('SharePoint')), "admissao' card asks about the access only it has in its type")

ok(JSON.stringify(stageOf(result, looks, found, fired)) === JSON.stringify(st), 'the same run, the same stage')
done()
