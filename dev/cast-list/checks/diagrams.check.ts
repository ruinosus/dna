// The diagrams, with no model: what was read, in plain Mermaid, from the stage of the full example — the topology, a
// sequence per call, a lens per pattern, the anatomy of each type — and a label that cannot break Mermaid.
import { diagramsDoc, diagramsOf, esc, slug } from '../src/diagrams'
import { stageOf } from '../src/stage'
import { fired, found, run } from './example'
import { done, ok } from './ok'

const { result, looks } = run()
const st = stageOf(result, looks, found, fired)
const pt = diagramsOf(st, result, 'pt')
const en = diagramsOf(st, result, 'en')
const get = (name: string) => pt.find((d) => d.name === name)?.mermaid ?? ''
const AGENT = /\bagentes?\b|\bagents?\b/i

// the topology: every node of the stage, its arrows
const topo = get('topologia')
ok(topo.startsWith('flowchart LR\n  %% title Topologia') && topo.includes('%% cast-list '), 'the topology: a flowchart with its chalk-talk title and the version', topo.slice(0, 120))
ok(st.nodes.every((_, i) => topo.includes(`n${i + 1}`)) && (topo.match(/^\s+n\d+ (==>|-->|-\.->)/gm) ?? []).length === st.edges.length, 'every node and every arrow of the stage', [st.nodes.length, st.edges.length])
ok(/n\d+\["Fidelidade<br\/><small>chamado, fora da pasta<\/small>"\]/.test(topo) && /-\.->\|"chama, mas não está na pasta"\|/.test(topo), 'fidelidade: not in the folder, dashed', topo)
ok(topo.includes('==>|"SEM histórico · SEM «CategoriaSolicitacao» · 355"|'), "frete's arrow says what is missing, with its volume", topo)
ok(['Especialistas · transação', 'Especialistas · orientação', 'Especialistas · triagem', 'Fluxos', 'Sistemas'].every((s) => topo.includes(`["${s}"]`)), 'the columns as subgraphs, the specialists by type')

// a sequence per scene, in order: the customer first, the answer back last
const scenes = pt.filter((d) => d.name.startsWith('cena-'))
ok(scenes.length === st.scenes.length && scenes.map((d) => d.name).join() === st.scenes.map((s) => `cena-${slug(s.title.pt)}`).join(), 'one sequence per call of the orchestrator, in its order', scenes.map((d) => d.name))
const frete = get('cena-frete')
ok(frete.includes('sequenceDiagram') && /p1->>p2: O cliente escreve\./.test(frete) && /p2-->>p1: a resposta\s*$/.test(frete), 'the customer writes; the answer goes back', frete)
ok(frete.includes('⚠ Frete é chamado SEM o histórico') && (frete.match(/%% # /g) ?? []).length === st.scenes.find((s) => s.to === 'bodega-frete')!.steps.length, "frete's scene: the contract warned, a chapter per step", frete)
const cupons = get('cena-cupons')
ok(/Note over p2: ⚠ O orquestrador encaminha para Cupons.*<br\/>«Cupons\.»/.test(cupons) && /p3->>p\d+: Usa SharePoint \(GetItems\)/.test(cupons), "cupons: the routing description quoted as it is; SharePoint used by cupons, not by the flow", cupons)
ok(/p2-xp3: ⚠ Chama Fidelidade/.test(get('cena-fidelidade')), 'the call to one not in the folder ends in a cross', get('cena-fidelidade'))

// the lenses, the same as the stage's
const lenses = pt.filter((d) => d.name.startsWith('lente-'))
ok(lenses.length === st.lenses.length && lenses.every((d, i) => d.intro === st.lenses[i].caption.pt), 'a lens per lens of the stage, told by its caption')
const contract = get('lente-contrato')
ok(/n\d+\["Frete<br\/><small>fora<\/small>"\]/.test(contract) && /n\d+\["Cupons<br\/><small>para olhar<\/small>"\]/.test(contract) && /class [n\d,]+ bad/.test(contract), 'the contract lens: frete off, cupons to look at, in words and colour', contract)

// a diagram per type
const types = pt.filter((d) => d.name.startsWith('tipo-'))
ok(types.map((d) => d.name).join() === 'tipo-transacao,tipo-orientacao,tipo-triagem', 'one anatomy per type', types.map((d) => d.name))
ok(get('tipo-transacao').includes('3 especialistas: Cupons, Devoluções, Pedidos') && get('tipo-triagem').includes('poucos para comparar'), 'each type with its members; one too small to compare says so')

// nothing breaks Mermaid; nothing on screen says «agent» but what the client wrote
ok(esc('a "b" <script>; #1 %% `x`') === 'a #quot;b#quot; #lt;script#gt;#59; #35;1 #37;#37; #96;x#96;', 'a label: quotes, brackets, semicolons, # and %% become entity codes', esc('a "b" <script>; #1 %% `x`'))
const quotes = st.scenes.flatMap((s) => s.steps.flatMap((x) => (x.quote ? [esc(x.quote)] : [])))
const said = (ds: typeof pt) => ds.map((d) => [d.title, d.intro, quotes.reduce((m, q) => m.split(q).join(''), d.mermaid)].join('\n')).join('\n')
ok(!AGENT.test(said(pt)) && !AGENT.test(said(en)), 'never «agent» outside the quotes', said(pt).match(/.{0,40}\bagentes?\b.{0,20}/i)?.[0] ?? said(en).match(/.{0,40}\bagents?\b.{0,20}/i)?.[0])
ok(!!en.find((d) => d.name === 'topology')?.mermaid.includes('%% title Topology') && en.some((d) => d.name === 'scene-frete'), 'in English too, with English file names')

// the delivery document
const doc = diagramsDoc('agents', pt, result, looks, 'pt')
ok(doc.startsWith('# Bodega Azul — atendimento: o que o cast-list leu') && doc.includes('> Estes diagramas têm dados do cliente') && doc.includes('## Para olhar'), 'the document: its title, the notice, «to look at»', doc.slice(0, 300))
ok((doc.match(/^```mermaid$/gm) ?? []).length === pt.length && pt.every((d) => doc.includes(d.mermaid.trimEnd())), 'a ```mermaid block per diagram, as in its file')
ok(JSON.stringify(diagramsOf(stageOf(result, looks, found, fired), result, 'pt')) === JSON.stringify(pt), 'the same run, the same diagrams')
done()
