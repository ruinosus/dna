# Writing the recipe as text (.chalk)

The same recipe as `references/recipe.md`, one step per line. `scripts/build.mjs` reads it (and says the line of any
mistake). Save it as `<id>.chalk`. What each step draws, the palette and the rules of good drawing are in
`references/recipe.md`; this page is only how to write them.

```
title Juntar moedas ↔ o cofrinho
id coin-jar
theme chalkboard
locale pt-BR
param n "moedas por mês" 1..8 = 3

# O gancho
> A Ana guarda moedas todo mês.
person ana at 150,330 "Ana" mood=idea
text "quer poupar" right-of ana gap 16 align=start

# Desmontar
> Cada mês, n moedas vão para o banco.
row at 470,150 gap 14
  repeat n: coin size 44
bank banco at 740,450 "banco"
ana -> banco "deposita"

# A ideia
pause ask "E em um ano, quanto junta?"
counter at 470,270 "12*n" "{v:0} moedas num ano"

learning goal "…"
learning question "…"
learning answer "…"
learning caveat "…"

quiz "Se n dobra, o total do ano…"
  * dobra -- 12 × n cresce em linha reta
  - quadruplica -- não há n² aqui
```

## The rules

- **Header lines** (anywhere, usually on top): `title …`, `id …`, `category …`, `theme paper|chalkboard`,
  `locale en-US`, `background dots|grid|plain`, `size 900x560`, `param name "label" min..max [step=1] = value`,
  `switch name "label" on|off`, `var name = value`, `learning goal|question|answer|caveat "…"`.
- `# Title` opens a chapter and `> sentence` is the narration: both go to the **next step**.
- **Numbers or expressions:** a number as it is; an expression in quotes (`"12*n"`, `"x0 + b*k",300`); a bare name
  (`n`) is a value too. A point is `x,y` (no space).
- **Attributes** after a step: `key=value` (`size=44`, `color=blue`, `id=box`, `stroke=3`, `opacity=0.5`,
  `nudge=4,-2`) or the flags `dashed`, `flip`. `gap`, `size`, `r`, `rx`, `ry`, `w`, `h`, `columns`, `ms` and `thickness`
  can also go with a space (`size 44`).
- **Placing** instead of `at x,y`: `right-of <id>`, `left-of`, `above`, `below`, then `gap 16` and `align=start|end`.
- **Indented lines** are the steps inside `row`, `column`, `grid` and `when`, the marks of a `timeline`, the rows of a
  `table` and the options of a `quiz`.

## Every step

| Text | Step |
|---|---|
| `person ana at 150,330 "Ana" mood=idea` | a prop (any prop name), with an optional id and label |
| `text "…" at 40,60 size=40 anchor=middle` | text |
| `card at 10,10 w=220 h=130 "Title" "line 1" "line 2"` | card |
| `arrow 100,200 -> 300,200` · `line …` · `highlight … thickness=18` | from → to |
| `polyline 0,0 10,0 10,10` · `polygon …` · `curve …` | points |
| `circle at 100,100 r=40` · `ellipse at 100,100 rx=60 ry=30` | circle, ellipse |
| `plot "x^2" domain 0..10 range 0..100 box 50,50,300,200` | a curve of a formula |
| `pause` · `pause 400` · `pause ask "E agora?"` | a breath; with `ask`, the lesson waits for «Show me» |
| `row at 470,150 gap 14` · `column …` · `grid at 300,300 columns=3` | + indented steps |
| `repeat n: coin size 44` | one step repeated (`i` counts from 0) |
| `when atraso:` | + indented steps drawn when the condition holds |
| `ana -> banco "deposita"` | an arrow between two ids |
| `ana says "posso?"` · `ana thinks "hmm"` | a balloon (`side=right`, `width=200`) |
| `move ana to 300,200 along=curve` | the element walks there |
| `counter at 470,270 "12*n" "{v:0} moedas"` | a number that counts up |
| `axis 80,470 -> 420,470 domain 0..10 ticks=5 label="anos"` | axis |
| `timeline 100,400 -> 800,400 domain 1440..1520` + `mark 1450 "1450" "the press"` | timeline |
| `brace 60,560 -> 290,560 "two years"` | curly brace |
| `note at 500,100 "look here" -> ana` | a note with a curved arrow (or `-> x,y`) |
| `table at 60,380` + `\| a \| b \|` lines (`noheader`) | table |
| `bars box 400,400,300,200 values 1,2,"3*n" labels a,b,c format="{v}%"` | bars |
| `json {"type": …}` | any step as JSON, for anything the text has no short form for |

## A Mermaid diagram

**Any Mermaid diagram** (flowchart, sequence, class, state, ER, pie, timeline, journey, gantt, xychart, quadrant,
mindmap, kanban, gitGraph, sankey, block, packet, treemap, radar, requirement, C4, architecture, ishikawa, venn,
treeView, cynefin, eventmodeling, railroad, swimlanes, wardley — every kind of Mermaid 11.17 but zenuml) is also a recipe: save it as `<id>.mmd` (or put it in a
```mermaid block of a `.md`) and build it. Add `%% title …`, `%% # Chapter` and `%% > narration` lines — comments for
Mermaid, so the diagram still shows as usual on GitHub. A chapter starts at the arrow (message, relation) after it. The
drawing follows the order of the arrows, each box before the first arrow that reaches it; a sequence goes top to bottom.
Node shapes are kept (`([…])`, `[(…)]`, `{{…}}`, `[/…/]`, `>…]`, `[[…]]`, `(((…)))`, `@{ shape: … }`). In the other
kinds a `%% #` goes before a section, period, task, slice, series, point, branch, column or git command; with none,
each section, column, branch or git branch is a chapter of its own. A kind it does not draw yet makes the build say
which ones it draws.

```
flowchart LR
  %% title Um café, do pedido à xícara
  %% # O pedido
  %% > Você pede um café no balcão.
  A([Você]) -->|pede| B[Caixa]
  %% # A cozinha
  %% > O caixa passa a comanda para o barista.
  B -->|comanda| C[Barista]
  C -->|café pronto| A
```

```
sequenceDiagram
  %% title Um café no balcão
  %% # O pedido
  %% > Você pede um café.
  Você->>Caixa: um café, por favor
  %% # A conta
  Caixa-->>Você: são cinco reais
```
