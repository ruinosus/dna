// The RH of the cast, with no model: the development plan (PDI) of each one, from what «to look at» says about them
// alone — and, later in this file, the staff board, the post and the résumé.
import { pdiOf } from '../src/pdi'
import { run } from './example'
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

done()
