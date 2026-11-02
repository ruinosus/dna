// The profile's markers over the agents' texts: a fact for each, with the value it captured and the line it was
// found on; the built-in ones (the domains of links, an e-mail); and the two findings — agents of a role that set a
// marker in different ways, and an agent that sets it twice.
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { markerFindings, markersOf } from '../src/markers'
import type { Marker } from '../src/profile'
import { done, ok } from './ok'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/cast-list/examples')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const MARKERS: Marker[] = [
  { id: 'size', name: 'Tamanho da resposta', in: 'instructions', pattern: '(no máximo|at most|up to)\\s*(\\d+)\\s*(bullets?|frases?|sentences?)', value: '$2 $3' },
  { id: 'no-emoji', name: 'Sem emojis', in: 'instructions', pattern: '(sem|não use|no)\\s+emojis?' },
  { id: 'knowledge-only', name: 'Só o conhecimento', in: 'instructions', pattern: '(somente|apenas|only)[^.]{0,40}(conhecimento|knowledge)' },
]
const { facts, values } = markersOf(agents, MARKERS)
const has = (id: string, key: string) => key in facts[id]
const SPECIALISTS = ['bodega-pedidos', 'bodega-devolucoes', 'bodega-frete', 'bodega-cupons', 'bodega-loja-fisica']

ok(['bodega-pedidos', 'bodega-devolucoes', 'bodega-loja-fisica'].every((a) => has(a, 'text:size=3 bullets')) && ['bodega-cupons', 'bodega-loja-fisica'].every((a) => has(a, 'text:size=5 frases')), 'the answer size, with its value: 3 bullets in three, 5 frases in two', Object.fromEntries(SPECIALISTS.map((a) => [a, Object.keys(facts[a])])))
ok(!Object.keys(facts['bodega-frete']).some((k) => k.startsWith('text:size')), 'frete sets no size')
ok(values['bodega-loja-fisica'].size.join() === '3 bullets,5 frases', 'loja-fisica sets it twice', values['bodega-loja-fisica'])
ok([...SPECIALISTS.filter((a) => a !== 'bodega-loja-fisica'), 'bodega-orquestrador'].every((a) => has(a, 'text:no-emoji')) && !has('bodega-loja-fisica', 'text:no-emoji'), '«no emojis» everywhere but loja-fisica')
ok(has('bodega-devolucoes', 'text:knowledge-only') && SPECIALISTS.filter((a) => a !== 'bodega-devolucoes').every((a) => !has(a, 'text:knowledge-only')), '«only the knowledge» only in devolucoes')
const at = facts['bodega-loja-fisica']['text:size=5 frases'][0]
ok(at.file === 'agent.mcs.yml' && (at.line ?? 0) > 20, 'a marker says the line it was found on', at)

// built in: the domains of links, an e-mail
ok(has('bodega-cupons', 'text:link-domain:ajuda.bodega-azul.example') && has('bodega-loja-fisica', 'text:link-domain:ajuda.bodega-azul.example') && !has('bodega-pedidos', 'text:link-domain:ajuda.bodega-azul.example'), 'the domain of a link in the instructions, with no marker in the profile')
const mail = markersOf([extractAgent('m', [{ path: 'agent.mcs.yml', text: 'kind: GptComponentMetadata\ninstructions: Escreva para atendimento@loja.example se precisar.\n' }])], []).facts.m
ok('text:email' in mail && !Object.keys(mail).some((k) => k.startsWith('text:link-domain')), 'an e-mail is told, and is not a link')

// «in»: the descriptions are not the instructions
const desc = markersOf(agents, [{ id: 'erp', name: 'ERP', in: 'descriptions', pattern: 'erp' }, { id: 'erp-i', name: 'ERP', in: 'instructions', pattern: 'erp' }]).facts
ok('text:erp' in desc['bodega-pedidos'] && !('text:erp-i' in desc['bodega-pedidos']), '«in: descriptions» looks only at the descriptions')

// the findings
const roles = Object.fromEntries(agents.map((a) => [a.id, a.id === 'bodega-orquestrador' ? 'orchestrator' : 'specialist'])) as Record<string, 'orchestrator' | 'specialist'>
const found = markerFindings(values, MARKERS, roles)
const differ = found.find((x) => x.kind === 'values' && x.marker.id === 'size')
ok(differ?.kind === 'values' && differ.role === 'specialist' && differ.byValue['3 bullets'].length === 3 && differ.byValue['5 frases'].length === 2, '4 specialists set the size in 2 ways', found)
const twice = found.filter((x) => x.kind === 'twice')
ok(twice.length === 1 && twice[0].kind === 'twice' && twice[0].agent === 'bodega-loja-fisica' && twice[0].values.join() === '3 bullets,5 frases', 'loja-fisica sets it twice: which one holds?', twice)
ok(!found.some((x) => x.marker.id === 'no-emoji'), 'a marker with no value has no «different ways»')

// a long text is cut, not run forever
const long = 'a'.repeat(60_000) + ' no máximo 3 bullets'
const cut = markersOf([extractAgent('l', [{ path: 'agent.mcs.yml', text: `kind: GptComponentMetadata\ninstructions: ${long}\n` }])], MARKERS).facts.l
ok(!Object.keys(cut).some((k) => k.startsWith('text:size')), 'past 50,000 characters a text is not read further')
done()
