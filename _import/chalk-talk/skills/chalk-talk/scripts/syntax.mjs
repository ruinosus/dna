// One right way to write each kind of line of a .chalk recipe: build.mjs shows it under a mistake, so the fix is in the
// message, and SKILL.md's cheat sheet shows the same lines (tools/check.mjs builds every one of them, and checks the
// cheat sheet has them all).

/** Kind → an example that builds. Lines that need an earlier id say so in `needs`. */
export const SYNTAX = {
  title: { line: 'title Juros compostos ↔ a fatura do cartão' },
  locale: { line: 'locale pt-BR' },
  size: { line: 'size 900x560' },
  param: { line: 'param taxa "juros ao mês (%)" 1..15 step=1 = 8' },
  switch: { line: 'switch atraso "pagar com atraso" off' },
  var: { line: 'var f = "1 + taxa/100"' },
  learning: { line: 'learning goal "Ver o juro sobre o juro crescer mês a mês."', needs: 'learning question "Por que a fatura cresce cada vez mais rápido?"\nlearning answer "Porque cada mês o juro incide sobre o juro dos meses anteriores."\nlearning caveat "A taxa é ilustrativa; cartões reais têm IOF e multas."' },
  prop: { line: 'person ana at 150,330 "Ana" mood=worried' },
  text: { line: 'text "R$ 1.000 viram quanto?" at 40,64 size=36' },
  place: { line: 'text "paga só o mínimo" right-of ana gap 16 align=start', needs: 'person ana at 150,330 "Ana"' },
  row: { line: 'row at 470,150 gap 14\n  repeat 3: coin size 44' },
  repeat: { line: 'repeat 3: coin at "100 + i*60",400 size 40' },
  link: { line: 'ana -> banco "paga" -> loja "repassa"', needs: 'person ana at 150,330 "Ana"\nbank banco at 450,330 "banco"\nshop loja at 750,330 "loja"' },
  chain: { line: 'chain at 40,190 forward="o café desce" back="pedidos sobem"\n  field fazenda "fazenda"\n  truck caminhao "transporte"\n  cup cafe "cafeteria"\n  person voce "você"' },
  define: { line: 'define xicara\n  polygon 24,48 76,48 70,90 30,90 fill=#FFFFFF\n  curve 74,56 90,62 72,80\nxicara minha at 450,300 "minha xícara"' },
  arrow: { line: 'arrow 60,350 -> 840,350 color=#2E8F62 stroke=3' },
  balloon: { line: 'ana thinks "e se eu atrasar?" side=above width=200', needs: 'person ana at 150,330 "Ana"' },
  counter: { line: 'counter at 470,270 "1000*f^6" "R$ {v:0} em seis meses" size=34' , needs: 'param taxa "juros ao mês (%)" 1..15 = 8\nvar f = "1 + taxa/100"' },
  bars: { line: 'bars box 90,320,440,180 values 1000,"1000*f^3","1000*f^6" labels hoje,"3 meses","6 meses" format="R$ {v:0}"', needs: 'param taxa "juros ao mês (%)" 1..15 = 8\nvar f = "1 + taxa/100"' },
  plot: { line: 'plot "1000*(1+taxa/100)^x" domain 0..12 range 0..4000 box 480,120,360,240', needs: 'param taxa "juros ao mês (%)" 1..15 = 8' },
  when: { line: 'when atraso:\n  text "multa de 2%" at 600,100 color=#C8442C', needs: 'switch atraso "pagar com atraso" off' },
  pause: { line: 'pause ask "Quanto vai virar a fatura em seis meses?"' },
  highlight: { line: 'highlight 90,500 -> 810,500 thickness=24' },
  quiz: { line: 'quiz "Se a taxa dobra, a fatura em seis meses…"\n  * mais que dobra o juro -- é juro sobre juro\n  - só dobra -- isso seria juro simples' },
  // Not in the cheat sheet (references/text.md has them all), but a mistake in one still shows how it is written.
  line: { line: 'line 60,350 -> 840,350 dashed', sheet: false },
  polyline: { line: 'polyline 100,100 200,80 300,120', sheet: false },
  polygon: { line: 'polygon 100,100 200,100 150,40', sheet: false },
  curve: { line: 'curve 100,300 300,200 500,300', sheet: false },
  circle: { line: 'circle at 450,300 r=40', sheet: false },
  ellipse: { line: 'ellipse at 450,300 rx=80 ry=40', sheet: false },
  card: { line: 'card at 40,380 w=240 h=130 "Fatura" "mínimo: R$ 150" "juros: 8%"', sheet: false },
  move: { line: 'move ana to 400,330', needs: 'person ana at 150,330 "Ana"', sheet: false },
  axis: { line: 'axis 80,470 -> 420,470 domain 0..12 ticks=6 label="meses"', sheet: false },
  timeline: { line: 'timeline 100,400 -> 800,400 domain 1440..1520\n  mark 1450 "1450" "a prensa"', sheet: false },
  brace: { line: 'brace 60,520 -> 290,520 "seis meses"', sheet: false },
  note: { line: 'note at 600,100 "o juro entra aqui" -> ana', needs: 'person ana at 150,330 "Ana"', sheet: false },
  table: { line: 'table at 60,380\n  | mês | fatura |\n  | 1 | R$ 1.080 |', sheet: false },
  json: { line: 'json {"type":"circle","center":[450,300],"r":40}', sheet: false },
}

// The word a text line starts with, mapped to its kind (a prop name is a prop; `x says`, `x -> y` follow an id).
const ALIAS = { column: 'row', grid: 'row', says: 'balloon', thinks: 'balloon' }

/** The example for a line of text (by its first words), or undefined. `props` is every prop name and alias. */
export function syntaxForLine(source, props) {
  const words = source.trim().split(/\s+/)
  const [first, second] = words
  if (!first) return undefined
  if (SYNTAX[first]) return SYNTAX[first].line
  if (ALIAS[first]) return SYNTAX[ALIAS[first]].line
  if (props.includes(first)) return SYNTAX.prop.line
  if (second === 'says' || second === 'thinks') return SYNTAX.balloon.line
  if (second === '->') return SYNTAX.link.line
  return undefined
}

/** The example for a step of the recipe by its type (a contract error names the step). */
export function syntaxForStep(type) {
  if (!type) return undefined
  if (SYNTAX[type]) return SYNTAX[type].line
  return ALIAS[type] ? SYNTAX[ALIAS[type]].line : undefined
}
