// The RH of the cast, with no model: the development plan (PDI) of each one, from what «to look at» says about them
// alone — and, later in this file, the staff board, the post and the résumé.
import { pdiOf } from '../src/pdi'
import { playbillOf } from '../src/playbill'
import { accessOf } from '../src/playbill'
import { evals, fired, found, profile, run } from './example'
import { done, ok } from './ok'

const { result, looks } = run()
const pdi = pdiOf(looks, result)
const of = (agent: string, lang: 'pt' | 'en' = 'pt') => pdi.filter((p) => p.agent === agent).map((p) => p[lang])
const AGENT = /\bagentes?\b|\bagents?\b/i

// the PDI
ok(of('bodega-frete').join(' · ') === 'Aprender a encaminhar para uma pessoa · Receber do gestor o histórico da conversa e «CategoriaSolicitacao» · Alinhar o bloco oficial «Formatação de links» · Conferir se o evento «BodegaFrete_OnError» dispara · Remover a variável «PreferenciaAntiga»', "frete: 5 items — one per fact (the handoff's claim and the pattern are one), the orchestrator's inputs as one", of('bodega-frete'))
ok(pdi.filter((p) => p.agent === 'bodega-frete').map((p) => p.group).join() === 'contradictions,contract,off,telemetry,cleanup', 'in the order of the groups', pdi.filter((p) => p.agent === 'bodega-frete').map((p) => p.group))
ok(!pdi.some((p) => p.keys.some((k) => k === 'trigger:OnSelectIntent' || k === 'text:size' && p.agent !== 'bodega-loja-fisica')), 'no solo, no type with one, no marker set in ways across the cast', pdi.map((p) => [p.agent, p.keys]))
ok(of('bodega-pedidos').join() === 'Remover o nó desligado em «topics/Escalate»' && pdi.filter((p) => p.agent === 'bodega-pedidos').every((p) => p.group === 'cleanup'), 'pedidos: only the cleanup', of('bodega-pedidos'))
ok(of('bodega-devolucoes').join() === 'Tirar «Conhecimento geral do modelo ligado»', 'devolucoes: the contradiction of its text and its setup', of('bodega-devolucoes'))
ok(of('bodega-orquestrador').join() === 'Trazer «Bodega Azul - Fidelidade» para a pasta, ou tirar a chamada', "the orchestrator: the call to one not in the folder is its item", of('bodega-orquestrador'))
ok(of('bodega-loja-fisica').includes('Declarar uma meta (KPI)') && of('bodega-loja-fisica').includes('Escolher um só «Tamanho da resposta»') && of('bodega-loja-fisica').includes('Ligar a telemetria ao Application Insights'), 'loja-fisica: the rule, the marker set twice, the telemetry', of('bodega-loja-fisica'))
ok(of('bodega-cupons').includes('Escrever a descrição de roteamento: o que ele resolve') && of('bodega-cupons').includes('Fazer o fluxo «Abrir chamado no ERP» devolver o resultado') && of('bodega-cupons').includes('Chamar o evento como os outros: «‹nome›_OnError»') && of('bodega-cupons').includes('Registrar «ConversationId» no evento «‹nome›_OnError»'), 'cupons: the routing description, the flow, the spelling, the field', of('bodega-cupons'))
ok(pdi.every((p) => p.en && p.pt && p.why.en && p.why.pt && !AGENT.test(p.en + p.pt)), 'every item in English and Portuguese, with why, never «agent»', pdi.filter((p) => !p.en || !p.pt || AGENT.test(p.en + p.pt)))
ok(pdi.every((p) => p.en !== p.pt || /^[^a-z]*$/i.test(p.en)), 'the English is not the Portuguese', pdi.filter((p) => p.en === p.pt))
ok(pdiOf([], result).length === 0, 'nothing to look at: no PDI')

// the staff board
const full = run()
const pb = playbillOf(full.result, full.looks, found, full.cast, profile.rules, fired)
const in_ = (key: string) => pb.staff.find((s) => s.key === key)?.people.map((p) => p.name).join(', ')
ok(in_('cast')?.split(', ').length === 6, 'the cast: the six in the folder', in_('cast'))
ok(in_('hiring') === 'Bodega Azul - Fidelidade', 'being hired: fidelidade, called and not in the folder (and in Testes in the inventory)', in_('hiring'))
ok(in_('noOwner') === 'Bodega Azul - Cupons', 'no owner: cupons (no Owner in the inventory, though the team spreadsheet gives it a team)', in_('noOwner'))
ok(in_('neverPublished') === 'Bodega Azul - Loja Física', 'never published: loja-fisica', in_('neverPublished'))
ok(in_('ok') === 'Bodega Azul - Pedidos' && !!in_('pdi')?.includes('Bodega Azul - Frete') && !!in_('pdi')?.includes('Bodega Azul - Orquestrador'), 'in good standing: pedidos alone (its only item is cleanup); frete and the orchestrator in PDI', [in_('ok'), in_('pdi')])
ok(pb.missing.length === 0, 'with the inventory, the team spreadsheet and the telemetry, nothing missing', pb.missing)

// the org chart
ok(pb.org.orchestrators.map((p) => p.id).join() === 'bodega-orquestrador' && pb.org.ghosts.map((g) => g.name).join() === 'Bodega Azul - Fidelidade', 'the org chart: the orchestrator as the manager, fidelidade dashed', pb.org)
ok(pb.org.types.map((t) => `${t.name}:${t.people.map((p) => p.id.replace('bodega-', '')).join('+')}`).join(' ') === 'transação:cupons+devolucoes+pedidos orientação:cupons+loja-fisica triagem:frete', 'the specialists by type (cupons in its two)', pb.org.types.map((t) => [t.name, t.people.map((p) => p.id)]))

// the post
const post = pb.posts.find((p) => p.scope === 'specialist')!
ok(post.requirements.some((r) => r.pt === 'Sabe encaminhar para uma pessoa (escalonamento)' && !r.proposal) && post.requirements.some((r) => r.key === 'declared:kpi' && !r.proposal), "the specialist's post: the accepted escalation and the profile's KPI rule", post.requirements)
const noDecision = run()
noDecision.cast.decisions = []
const pb0 = playbillOf({ ...noDecision.result, patterns: noDecision.result.patterns.map(({ decision, ...p }) => p) }, noDecision.looks, found, noDecision.cast, [], fired)
ok(pb0.posts.find((p) => p.scope === 'specialist')!.requirements.every((r) => r.proposal) && pb0.posts.find((p) => p.scope === 'specialist')!.requirements.length > 0, 'with no decision, the post is what someone is off, as a proposal', pb0.posts[0])

// the résumé
const frete = pb.resumes.find((r) => r.id === 'bodega-frete')!
ok(frete.title === 'Você é o especialista em frete e entregas da Bodega Azul, uma loja online.' && frete.manager === 'Bodega Azul - Orquestrador', 'frete: the title is the first sentence of its instructions; the manager, who calls it', [frete.title, frete.manager])
ok(frete.team?.value === 'Squad Logística' && frete.owner?.value === 'frete@bodegaazul.example' && frete.goal?.value === 'cotação em menos de 5 s' && frete.goal.source.startsWith('equipe.csv'), 'frete: team, owner and goal, each with its source', [frete.team, frete.owner, frete.goal])
ok(frete.created?.value === '2026-03-09' && frete.published?.value === '2026-09-30' && frete.schemaName === 'cr7b2_bodegaFrete' && frete.environment?.value === 'Bodega Azul (Produção)', 'frete: hired, published, its schema name and environment, from the inventory', frete)
ok(frete.summary[0] === 'Explicar modalidades de envio, prazos por região e regras de frete grátis' && frete.summary.length === 3, 'frete: the summary is the first list of its instructions, as written', frete.summary)
ok(frete.performance?.starts === 355 && frete.performance.errors === 0 && frete.performance.notFired.join() === 'BodegaFrete_OnError' && !frete.performance.silent, 'frete: 355 topic starts, 0 errors, the event that did not fire', frete.performance)
ok(frete.pdi.length === 5 && frete.seal === 'pdi' && frete.sources.join() === 'YAML,telemetria.csv,handoff do frete, seção 4,inventario.csv,equipe.csv', 'frete: 5 items, the PDI seal, and where it came from (the handoff the demo cast file declares, too)', [frete.pdi.length, frete.seal, frete.sources])
ok(frete.tools.some((t) => t.pt.includes('Outlook')) && frete.conduct.length > 0, 'frete: its tools and its conduct', [frete.tools, frete.conduct])
const loja = pb.resumes.find((r) => r.id === 'bodega-loja-fisica')!
ok(!loja.goal && loja.performance?.silent === true && !loja.published, 'loja-fisica: no goal (never invented), no line in the telemetry, never published', loja)
ok(pb.resumes.find((r) => r.id === 'bodega-pedidos')!.seal === 'ok', 'pedidos: in good standing')
ok(!pb.resumes.find((r) => r.id === 'bodega-orquestrador')!.manager, 'nobody calls the orchestrator: no manager')

// with no tables and no telemetry
const bare = run([], false)
const pbBare = playbillOf(bare.result, bare.looks, found, bare.cast, profile.rules)
ok(!pbBare.staff.some((s) => s.key === 'noOwner' || s.key === 'neverPublished') && pbBare.missing.join() === 'inventory,telemetry' && pbBare.resumes.every((r) => !r.performance && !r.team && !r.owner), 'with no tables: no «no owner» or «never published», and it says which tables would tell (the demo cast file already declares KPIs)', pbBare.missing)
ok(JSON.stringify(playbillOf(full.result, full.looks, found, full.cast, profile.rules, fired)) === JSON.stringify(pb), 'the same run, the same RH')

// the evaluations: the counts in the résumé, «with no evaluation» on the board
const pbE = playbillOf(full.result, full.looks, found, full.cast, profile.rules, fired, evals)
const cert = (id: string) => pbE.resumes.find((r) => r.id === id)!.certifications
ok(cert('bodega-pedidos')?.[0]?.passed === 4 && cert('bodega-frete')?.[0]?.passed === 2 && cert('bodega-frete')?.[0]?.total === 4 && cert('bodega-cupons')?.length === 0, 'the certifications: pedidos 4 of 4, frete 2 of 4, cupons none', [cert('bodega-pedidos'), cert('bodega-frete')])
ok(pbE.staff.find((s) => s.key === 'noEval')?.people.map((p) => p.id).sort().join() === 'bodega-cupons,bodega-devolucoes,bodega-loja-fisica,bodega-orquestrador' && !pb.staff.some((s) => s.key === 'noEval') && pb.resumes.every((r) => !r.certifications), 'with no evaluation: the four with none, only when --evals was given', pbE.staff)
ok(!/Onde está meu pedido|Manaus|saiu para entrega/.test(JSON.stringify(pbE)), 'no question or answer of an evaluation in the RH')

// the review of access
const acc = accessOf(full.result)
ok(acc.some((x) => x.agent === 'bodega-cupons' && x.types.includes('transaction') && x.key === 'connector:shared_sharepointonline') && acc.some((x) => x.agent === 'bodega-cupons' && x.key.startsWith('mcp:')) && acc.every((x) => x.pt.includes('o cargo precisa?')), 'only cupons, in the type transaction, has SharePoint and the MCP server: does the post need them?', acc)
ok(!acc.some((x) => x.types.includes('triage')) && !acc.some((x) => x.key.startsWith('operation:shared_sharepointonline/')) && new Set(acc.map((x) => `${x.agent} ${x.key}`)).size === acc.length, 'one line per access (its types together; an operation of a connector already asked about left out); a type of one has none', acc)
ok(!pb.resumes.find((r) => r.id === 'bodega-cupons')!.pdi.some((p) => p.pt.startsWith('Tirar o acesso')), 'a question, not a plan item, until the team decides')
const decided = run()
decided.cast.decisions.push({ key: 'connector:shared_sharepointonline', status: 'rejected', scope: 'type:transaction', why: 'o cargo não precisa' })
const pbD = playbillOf(decided.result, decided.looks, found, decided.cast, profile.rules, fired)
ok(pbD.resumes.find((r) => r.id === 'bodega-cupons')!.pdi.some((p) => p.pt === 'Tirar o acesso «Conector SharePoint»' && p.group === 'cleanup'), 'with a decision «rejected» in the scope of the type, a cleanup item', pbD.resumes.find((r) => r.id === 'bodega-cupons')!.pdi)
done()
