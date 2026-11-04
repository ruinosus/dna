// The RH of the cast, with no model: the development plan (PDI) of each one, from what «to look at» says about them
// alone — and, later in this file, the staff board, the post and the résumé.
import { pdiOf } from '../src/pdi'
import { playbillOf } from '../src/playbill'
import { accessOf, requirement } from '../src/playbill'
import { evals, fired, found, profile, run } from './example'
import { done, ok } from './ok'

const { result, looks } = run()
const pdi = pdiOf(looks, result)
const of = (agent: string, lang: 'pt' | 'en' = 'pt') => pdi.filter((p) => p.agent === agent).map((p) => p[lang])
const AGENT = /\bagentes?\b|\bagents?\b/i

// the PDI
ok(of('rh-folha').join(' · ') === 'Aprender a encaminhar para uma pessoa · Receber do gestor o histórico da conversa e «CategoriaSolicitacao» · Alinhar o bloco oficial «Formatação de links» · Conferir se o evento «RhFolha_OnError» dispara · Remover a variável «PreferenciaAntiga»', "folha: 5 items — one per fact (the handoff's claim and the pattern are one), the orchestrator's inputs as one", of('rh-folha'))
ok(pdi.filter((p) => p.agent === 'rh-folha').map((p) => p.group).join() === 'contradictions,contract,off,telemetry,cleanup', 'in the order of the groups', pdi.filter((p) => p.agent === 'rh-folha').map((p) => p.group))
ok(!pdi.some((p) => p.keys.some((k) => k === 'trigger:OnSelectIntent' || k === 'text:size' && p.agent !== 'rh-facilities')), 'no solo, no type with one, no marker set in ways across the cast', pdi.map((p) => [p.agent, p.keys]))
ok(of('rh-ferias').join() === 'Remover o nó desligado em «topics/Escalate»' && pdi.filter((p) => p.agent === 'rh-ferias').every((p) => p.group === 'cleanup'), 'ferias: only the cleanup', of('rh-ferias'))
ok(of('rh-beneficios').join() === 'Tirar «Conhecimento geral do modelo ligado»', 'beneficios: the contradiction of its text and its setup', of('rh-beneficios'))
ok(of('rh-orquestrador').join() === 'Trazer «RH - Mobilidade» para a pasta, ou tirar a chamada', "the orchestrator: the call to one not in the folder is its item", of('rh-orquestrador'))
ok(of('rh-facilities').includes('Declarar uma meta (KPI)') && of('rh-facilities').includes('Escolher um só «Tamanho da resposta»') && of('rh-facilities').includes('Ligar a telemetria ao Application Insights'), 'facilities: the rule, the marker set twice, the telemetry', of('rh-facilities'))
ok(of('rh-admissao').includes('Escrever a descrição de roteamento: o que ele resolve') && of('rh-admissao').includes('Fazer o fluxo «Abrir caso no Workday» devolver o resultado') && of('rh-admissao').includes('Chamar o evento como os outros: «‹nome›_OnError»') && of('rh-admissao').includes('Registrar «ConversationId» no evento «‹nome›_OnError»'), 'admissao: the routing description, the flow, the spelling, the field', of('rh-admissao'))
ok(pdi.every((p) => p.en && p.pt && p.why.en && p.why.pt && !AGENT.test(p.en + p.pt)), 'every item in English and Portuguese, with why, never «agent»', pdi.filter((p) => !p.en || !p.pt || AGENT.test(p.en + p.pt)))
ok(pdi.every((p) => p.en !== p.pt || /^[^a-z]*$/i.test(p.en)), 'the English is not the Portuguese', pdi.filter((p) => p.en === p.pt))
ok(pdiOf([], result).length === 0, 'nothing to look at: no PDI')

// the staff board
const full = run()
const pb = playbillOf(full.result, full.looks, found, full.cast, profile.rules, fired)
const in_ = (key: string) => pb.staff.find((s) => s.key === key)?.people.map((p) => p.name).join(', ')
ok(in_('cast')?.split(', ').length === 6, 'the cast: the six in the folder', in_('cast'))
ok(in_('hiring') === 'RH - Mobilidade', 'being hired: mobilidade, called and not in the folder (and in Testes in the inventory)', in_('hiring'))
ok(in_('noOwner') === 'RH - Admissão', 'no owner: admissao (no Owner in the inventory, though the team spreadsheet gives it a team)', in_('noOwner'))
ok(in_('neverPublished') === 'RH - Facilities', 'never published: facilities', in_('neverPublished'))
ok(in_('ok') === 'RH - Férias' && !!in_('pdi')?.includes('RH - Folha') && !!in_('pdi')?.includes('RH - Orquestrador'), 'in good standing: ferias alone (its only item is cleanup); folha and the orchestrator in PDI', [in_('ok'), in_('pdi')])
ok(pb.missing.length === 0, 'with the inventory, the team spreadsheet and the telemetry, nothing missing', pb.missing)

// the org chart
ok(pb.org.orchestrators.map((p) => p.id).join() === 'rh-orquestrador' && pb.org.ghosts.map((g) => g.name).join() === 'RH - Mobilidade', 'the org chart: the orchestrator as the manager, mobilidade dashed', pb.org)
ok(pb.org.types.map((t) => `${t.name}:${t.people.map((p) => p.id.replace('rh-', '')).join('+')}`).join(' ') === 'transação:admissao+beneficios+ferias orientação:facilities triagem:folha' && pb.org.types[0].people[0].alsoIn?.join() === 'orientação', 'the specialists by type: admissao once, in its first, «also in orientação»', pb.org.types.map((t) => [t.name, t.people.map((p) => [p.id, p.alsoIn])]))

// the post
const post = pb.posts.find((p) => p.scope === 'specialist')!
ok(post.requirements.some((r) => r.pt === 'Sabe encaminhar para uma pessoa (escalonamento)' && !r.proposal) && post.requirements.some((r) => r.key === 'declared:kpi' && !r.proposal), "the specialist's post: the accepted escalation and the profile's KPI rule", post.requirements)
const noDecision = run()
noDecision.cast.decisions = []
const pb0 = playbillOf({ ...noDecision.result, patterns: noDecision.result.patterns.map(({ decision, ...p }) => p) }, noDecision.looks, found, noDecision.cast, [], fired)
ok(pb0.posts.find((p) => p.scope === 'specialist')!.requirements.every((r) => r.proposal) && pb0.posts.find((p) => p.scope === 'specialist')!.requirements.length > 0, 'with no decision, the post is what someone is off, as a proposal', pb0.posts[0])

ok(requirement('called-with:input:CategoriaSolicitacao', 'pt') === 'Recebe «CategoriaSolicitacao» do orquestrador' && requirement('node:SearchKnowledgeSources', 'pt') === 'Busca nas fontes de conhecimento' && requirement('connector:shared_office365', 'pt') === 'Tem «Conector Office 365 Outlook»', 'a requirement already a sentence is said as it is; a thing, as «Tem «…»»', [requirement('called-with:input:CategoriaSolicitacao', 'pt'), requirement('node:SearchKnowledgeSources', 'pt')])

// the résumé
const folha = pb.resumes.find((r) => r.id === 'rh-folha')!
ok(folha.title === 'Você é o especialista em folha de pagamento do autoatendimento de RH da empresa.' && folha.manager === 'RH - Orquestrador', 'folha: the title is the first sentence of its instructions; the manager, who calls it', [folha.title, folha.manager])
ok(folha.team?.value === 'Squad Folha' && folha.owner?.value === 'folha@empresa.example' && folha.goal?.value === 'resposta sobre o holerite em menos de 5 s' && folha.goal.source.startsWith('equipe.csv'), 'folha: team, owner and goal, each with its source', [folha.team, folha.owner, folha.goal])
ok(folha.created?.value === '2026-03-09' && folha.published?.value === '2026-09-30' && folha.schemaName === 'cr7b2_rhFolha' && folha.environment?.value === 'RH (Produção)', 'folha: hired, published, its schema name and environment, from the inventory', folha)
ok(folha.summary[0] === 'Explicar o holerite, os descontos e o calendário de pagamento' && folha.summary.length === 3, 'folha: the summary is the first list of its instructions, as written', folha.summary)
ok(folha.performance?.starts === 355 && folha.performance.errors === 0 && folha.performance.notFired.join() === 'RhFolha_OnError' && !folha.performance.silent, 'folha: 355 topic starts, 0 errors, the event that did not fire', folha.performance)
ok(folha.pdi.length === 5 && folha.seal === 'pdi' && folha.sources.join() === 'YAML,telemetria.csv,handoff da folha, seção 4,inventario.csv,equipe.csv', 'folha: 5 items, the PDI seal, and where it came from (the handoff the demo review file declares, too)', [folha.pdi.length, folha.seal, folha.sources])
ok(folha.tools.some((t) => t.pt.includes('Outlook')) && folha.conduct.length > 0, 'folha: its tools and its conduct', [folha.tools, folha.conduct])
const loja = pb.resumes.find((r) => r.id === 'rh-facilities')!
ok(!loja.goal && loja.performance?.silent === true && !loja.published, 'facilities: no goal (never invented), no line in the telemetry, never published', loja)
ok(pb.resumes.find((r) => r.id === 'rh-ferias')!.seal === 'ok', 'ferias: in good standing')
ok(!pb.resumes.find((r) => r.id === 'rh-orquestrador')!.manager, 'nobody calls the orchestrator: no manager')

// with no tables and no telemetry
const bare = run([], false)
const pbBare = playbillOf(bare.result, bare.looks, found, bare.cast, profile.rules)
ok(!pbBare.staff.some((s) => s.key === 'noOwner' || s.key === 'neverPublished') && pbBare.missing.join() === 'inventory,telemetry' && pbBare.resumes.every((r) => !r.performance && !r.team && !r.owner), 'with no tables: no «no owner» or «never published», and it says which tables would tell (the demo review file already declares KPIs)', pbBare.missing)
ok(JSON.stringify(playbillOf(full.result, full.looks, found, full.cast, profile.rules, fired)) === JSON.stringify(pb), 'the same run, the same RH')

// the evaluations: the counts in the résumé, «with no evaluation» on the board
const pbE = playbillOf(full.result, full.looks, found, full.cast, profile.rules, fired, evals)
const cert = (id: string) => pbE.resumes.find((r) => r.id === id)!.certifications
ok(cert('rh-ferias')?.[0]?.passed === 4 && cert('rh-folha')?.[0]?.passed === 2 && cert('rh-folha')?.[0]?.total === 4 && cert('rh-admissao')?.length === 0, 'the certifications: ferias 4 of 4, folha 2 of 4, admissao none', [cert('rh-ferias'), cert('rh-folha')])
ok(pbE.staff.find((s) => s.key === 'noEval')?.people.map((p) => p.id).sort().join() === 'rh-admissao,rh-beneficios,rh-facilities,rh-orquestrador' && !pb.staff.some((s) => s.key === 'noEval') && pb.resumes.every((r) => !r.certifications), 'with no evaluation: the four with none, only when --evals was given', pbE.staff)
ok(!/Onde está meu pedido|Manaus|saiu para entrega/.test(JSON.stringify(pbE)), 'no question or answer of an evaluation in the RH')

// the review of access
const acc = accessOf(full.result)
ok(acc.some((x) => x.agent === 'rh-admissao' && x.types.includes('transaction') && x.key === 'connector:shared_sharepointonline') && acc.some((x) => x.agent === 'rh-admissao' && x.key.startsWith('mcp:')) && acc.every((x) => x.pt.includes('o cargo precisa?')), 'only admissao, in the type transaction, has SharePoint and the MCP server: does the post need them?', acc)
ok(!acc.some((x) => x.types.includes('triage')) && !acc.some((x) => x.key.startsWith('operation:shared_sharepointonline/')) && new Set(acc.map((x) => `${x.agent} ${x.key}`)).size === acc.length, 'one line per access (its types together; an operation of a connector already asked about left out); a type of one has none', acc)
ok(!pb.resumes.find((r) => r.id === 'rh-admissao')!.pdi.some((p) => p.pt.startsWith('Tirar o acesso')), 'a question, not a plan item, until the team decides')
const decided = run()
decided.cast.decisions.push({ key: 'connector:shared_sharepointonline', status: 'rejected', scope: 'type:transaction', why: 'o cargo não precisa' })
const pbD = playbillOf(decided.result, decided.looks, found, decided.cast, profile.rules, fired)
ok(pbD.resumes.find((r) => r.id === 'rh-admissao')!.pdi.some((p) => p.pt === 'Tirar o acesso «Conector SharePoint»' && p.group === 'cleanup'), 'with a decision «rejected» in the scope of the type, a cleanup item', pbD.resumes.find((r) => r.id === 'rh-admissao')!.pdi)
done()
