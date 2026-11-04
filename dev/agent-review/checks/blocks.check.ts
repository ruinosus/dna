// The text blocks: split, normalised, compared by 5-word shingles; the same block, a variation, or another; families
// of blocks shared by two agents or more, with an id that survives a comma; the official block of the profile; the
// word diff of a variation; and thirty agents of three thousand characters in well under ten seconds.
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { blocksOf, jaccard, normalize, splitBlocks } from '../src/blocks'
import { wordDiff } from '../src/diff'
import { extractAgent } from '../src/extract'
import { agentsIn } from '../src/folder'
import { done, ok } from './ok'

const examples = resolve(dirname(fileURLToPath(import.meta.url)), '../../../skills/agent-review/examples')
const agents = agentsIn(join(examples, 'agents')).map((a) => extractAgent(a.id, a.files))
const LINKS = `Links:
- Formate links assim: [título](url), nunca a URL crua.
- Um link de ação vai no topo; o link da base de ajuda vai no fim.
- Nunca escreva as palavras «clique aqui».
- No máximo 3 links por resposta.`

// the pieces
const parts = splitBlocks({ source: 'instructions', file: 'agent.mcs.yml', line: 6, text: 'Curto demais.\n\nUm parágrafo com mais de oito palavras para contar aqui.\n\nLinks:\n- um\n- dois três quatro cinco seis sete' })
ok(parts.length === 2 && parts[0].line === 8 && parts[1].line === 10, 'a paragraph and a section (heading and list) are blocks, with their lines; under 8 words is not', parts.map((p) => [p.line, p.text.slice(0, 20)]))
ok(normalize('Até 3 links: https://x.example/a — São Paulo!').join(' ') === 'ate #n links #url sao paulo', 'normalised: lower case, no accents or punctuation, numbers and URLs as markers', normalize('Até 3 links: https://x.example/a — São Paulo!'))
ok(jaccard(LINKS, LINKS.replace('3 links', '5 links')) === 1, 'another number is the same block')
ok(jaccard(LINKS, 'Ao citar uma página, escreva o nome dela como texto do link e evite mostrar o endereço; ações primeiro, ajuda por último.') < 0.5, 'the same idea in other words is another block (text, not meaning)')

// the examples: the links block in four, a variation in frete
const { families, facts } = blocksOf(agents, [], [])
const links = families.find((f) => f.text.startsWith('Links:'))!
ok(!!links && links.id === 'links-formate-links-assim-titulo' && links.label.startsWith('Links: - Formate links assim'), 'the links block: an id from its first words, a label from its first eight', links && [links.id, links.label])
ok(Object.keys(links.holders).sort().join() === 'bodega-cupons,bodega-devolucoes,bodega-loja-fisica,bodega-pedidos', 'four have it the same', Object.keys(links.holders))
const v = links.variants['bodega-frete']!
ok(!!v && v.similarity >= 0.5 && v.similarity < 0.85 && v.source.file === 'agent.mcs.yml', `frete has a variation (${v?.similarity.toFixed(2)})`, v)
ok(v.diff.some((p) => p.op === 'del' && p.text.includes('link de ação vai no topo')) && v.diff.some((p) => p.op === 'del' && p.text === '3') && v.diff.some((p) => p.op === 'add' && p.text === '5'), 'its word diff: the line it lacks, 3 → 5', v.diff.filter((p) => p.op !== 'same'))
ok(`text:block:${links.id}` in facts['bodega-pedidos'] && `text:block:${links.id}~variant` in facts['bodega-frete'] && !(`text:block:${links.id}` in facts['bodega-frete']), 'the facts: the block, or its variation (which is not the block)')
ok((facts['bodega-pedidos'][`text:block:${links.id}`]?.[0]?.line ?? 0) > 6, 'a block says the line it starts on', facts['bodega-pedidos'][`text:block:${links.id}`])
ok(families.every((f) => Object.keys(f.holders).length + Object.keys(f.variants).length >= 2), 'a text only one agent has is not a family')
ok(!families.some((f) => Object.values(f.holders).some((s) => s.file.includes(' Copy'))), 'the copied topic is not counted')

// the official block, and an id that survives a comma
const official = blocksOf(agents, [], [{ id: 'links', name: 'Formatação de links', text: LINKS }]).families.find((f) => f.id === 'links')
ok(official?.official === 'Formatação de links' && Object.keys(official.holders).length === 4 && !!official.variants['bodega-frete'], 'the official block gives its id and name to the family like it')
const kept = blocksOf(agents, [{ id: 'meu-bloco', text: LINKS.replace('crua.', 'crua,') }], []).families.find((f) => f.text.startsWith('Links:'))
ok(kept?.id === 'meu-bloco', 'a block kept in the review file keeps its id when a comma changes', kept?.id)
const lone = blocksOf(agents, [], [{ id: 'aviso', name: 'Aviso legal', text: 'Este atendimento é automático e pode errar; confirme os dados importantes com uma pessoa.' }]).families.find((f) => f.id === 'aviso')
ok(!!lone && !Object.keys(lone.holders).length, 'an official block nobody has is still a family, with nobody in it')

// the word diff
const d = wordDiff('a b c d', 'a x c d e')
ok(d.map((p) => `${p.op}:${p.text}`).join('|') === 'same:a|del:b|add:x|same:c d|add:e', 'the word diff', d)

// thirty agents with three thousand characters each
const words = 'atendimento cliente pedido prazo entrega troca reembolso cupom loja retirada pagamento boleto cartão pix nota fiscal endereço horário'.split(' ')
let seed = 7
const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
const para = (n: number) => Array.from({ length: n }, () => words[Math.floor(rnd() * words.length)]).join(' ') + '.'
const shared = Array.from({ length: 6 }, () => para(40))
const many = Array.from({ length: 30 }, (_, i) => {
  const text = [...shared.map((p, k) => (k === i % 6 ? para(40) : p)), para(60), para(60)].join('\n\n')
  return extractAgent(`a${i}`, [{ path: 'agent.mcs.yml', text: `kind: GptComponentMetadata\ninstructions: |\n${text.split('\n').map((l) => `  ${l}`).join('\n')}\n` }])
})
const t0 = Date.now()
const big = blocksOf(many, [], [])
const ms = Date.now() - t0
ok(ms < 10_000 && big.families.length >= 6 && many[0].texts[0].text.length > 2500, `thirty agents of ~${many[0].texts[0].text.length} characters: ${ms} ms, ${big.families.length} families`)
done()
