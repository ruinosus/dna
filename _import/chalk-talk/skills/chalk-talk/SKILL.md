---
name: chalk-talk
description: Explains an idea by drawing it, the way a teacher does at the board — a hand-drawn lesson that appears stroke by stroke, chapter by chapter, with narration and values the person can move, delivered as one HTML file that opens offline. Use when someone asks to explain, teach or show something by drawing it ("explain compound interest by drawing", "draw how a web request works", "desenha pra mim como funciona…"), or wants a visual, step-by-step explanation of a concept, a process, an argument or a system for a class, a talk or themselves.
license: MIT
compatibility: Best with code execution and Node.js 18 or later (Chrome, Chromium or Edge, when installed, lets the script check the drawing first). Without code execution, an HTML artifact that loads the player from a CDN works too; the page then checks itself.
metadata:
  version: "0.14.1"
---

# chalk-talk: explain by drawing

You make a hand-drawn explanation: a **recipe** in a short text (`.chalk`) that the player in this skill draws stroke
by stroke, with chapters, a short narration and, when there is a real quantity, a value the person moves. You write
only the recipe; `scripts/build.mjs` checks it and builds one HTML file with everything inside. Never write or copy the
player yourself. Paths below are relative to this skill's folder.

## 1. Draw first

For an ordinary request ("explain X by drawing", "draw how Y works") **do not ask and do not show an outline: draw.**
Decide the three things a drawing needs yourself, and say them when you deliver:

- **the hook**: a thing of everyday life the idea is tied to, that the audience has seen or done and that can be drawn
  with few shapes (a card bill, a bus stop, a café queue);
- **who it is for**: what the request says, else a curious adult;
- **the value the person moves**: a real quantity in the idea (the monthly rate, people arriving per minute), or none.

Ask first — once, all together, and only what is missing — when it is **for a class, students, a talk or a course**
(see «For a class»), when the request could mean two different things, or when the person asks to see the plan first.

The drawing has four parts, a chapter each: **the hook as a question** ("why does R$ 1,000 become R$ 1,974?"); **take
it apart** (the real thing, simply, and what is hidden in it); **the idea** (the rule, the flow or the argument, with
the value that moves); **the close** (a highlight on the result and where the comparison stops).

## 2. Write the recipe

Write `<id>.chalk` with the lines below — this covers the usual drawing; **you do not need to read anything else
first**. The paper is 900 × 560 (`size 900x780` makes a taller board), x grows right and y down, a
prop's `at` is where it stands (its bottom centre); keep 30 px from the edges. `# Title` opens a chapter and
`> sentence` is the narration: both go to the next step. A point is `x,y` with no space; an expression goes in quotes
and can use the params and vars.

**It is one board: a chapter never clears the paper.** Everything drawn stays, like chalk on a blackboard, so plan the
whole board before writing and give each part its own place — the title once at the top, the hook and the real thing
in the upper half, the idea below or beside it, the close in what is left. Never draw two things in the same place;
12 to 25 steps are usually enough.

The top:

```
title Juros compostos ↔ a fatura do cartão
locale pt-BR
size 900x560
param taxa "juros ao mês (%)" 1..15 step=1 = 8
switch atraso "pagar com atraso" off
var f = "1 + taxa/100"
learning goal "Ver o juro sobre o juro crescer mês a mês."
```

Write all four `learning` lines — `goal`, `question` (one to think about), `answer` (grounded) and `caveat` (what was
simplified) — and set `locale` to the person's language, with every text in it.

People and things are **props**: person, person-sitting, person-pointing, house, car, bus, coin, phone, document,
server, bank, cloud, queue, desk, computer, clock, lock, money-arrow, tree, school, hospital, factory, truck, cart,
safe, bulb, gear, database, robot, ship, container, warehouse, box, pallet, shop, shelf, field, cup, function,
api-gateway, cache, cluster, board, book, pencil. A person takes `mood=` happy, sad, surprised, worried or idea.

```
person ana at 150,330 "Ana" mood=worried
text "R$ 1.000 viram quanto?" at 40,64 size=36
text "paga só o mínimo" right-of ana gap 16 align=start
ana thinks "e se eu atrasar?" side=above width=200
ana -> banco "paga" -> loja "repassa"
arrow 60,350 -> 840,350 color=#2E8F62 stroke=3
highlight 90,500 -> 810,500 thickness=24
```

Placing without working out coordinates — prefer these whenever pieces sit side by side or follow each other. A
`chain` is things that pass something along: spread over the paper, each joined to the next, with the long arrows if
asked:

```
chain at 40,190 forward="o café desce" back="pedidos sobem"
  field fazenda "fazenda"
  truck caminhao "transporte"
  cup cafe "cafeteria"
  person voce "você"
row at 470,150 gap 14
  repeat 3: coin size 44
repeat 3: coin at "100 + i*60",400 size 40
```

Numbers that follow the value:

```
counter at 470,270 "1000*f^6" "R$ {v:0} em seis meses" size=34
bars box 90,320,440,180 values 1000,"1000*f^3","1000*f^6" labels hoje,"3 meses","6 meses" format="R$ {v:0}"
plot "1000*(1+taxa/100)^x" domain 0..12 range 0..4000 box 480,120,360,240
when atraso:
  text "multa de 2%" at 600,100 color=#C8442C
```

A thing no prop draws: make it on a 0–100 grid (whole numbers, y down; it stands at 50,100), then use its name:

```
define xicara
  polygon 24,48 76,48 70,90 30,90 fill=#FFFFFF
  curve 74,56 90,62 72,80
xicara minha at 450,300 "minha xícara"
```

Waiting for the person, and a quiz (both for a class):

```
pause ask "Quanto vai virar a fatura em seis meses?"
quiz "Se a taxa dobra, a fatura em seis meses…"
  * mais que dobra o juro -- é juro sobre juro
  - só dobra -- isso seria juro simples
```

Keep: 8 to 40 steps on one board; a short narration only when the idea changes; titles 36 to 44, labels 24 to 34, nothing under 22;
colours graphite (the default), #2F5BEA, #C8442C, #2E8F62, #8C8578, marker #FFE45C, three accents at most; facts and
numbers right — never invent a quote or a figure. Other steps (circle, curve, card, table, axis, timeline, brace, note,
move…) are in `references/text.md`; what each draws, in `references/recipe.md`. Open them only when you need a step that
is not above or the build's message does not settle a mistake.

If the person gives a **Mermaid diagram**, keep it as it is, add `%% title …`, `%% # chapter` and `%% > narration`
lines and save it as `<id>.mmd` (`references/text.md` shows how). Save the recipe in the folder the person works in,
or, when an outputs folder exists for files the person downloads (on claude.ai, `/mnt/user-data/outputs`), there.

## 3. Build and check

```
node scripts/build.mjs <id>.chalk
```

It writes `<id>.html` next to the recipe and prints:

- `✗ text: line N …` or `✗ contract: …` (exit 1, nothing written): fix that line the way the message says, as the
  example under it shows.
- `! review …` (exit 3): drawn, but something leaves the paper, a text covers another or a line crosses a text. Fix it
  and build again **with `--snapshots`**: it also writes `<id>.snapshots/<id>.contact-sheet.png` — every chapter at
  every setting of the values. Open that picture and fix what the review named and anything that does not read right
  (a figure that is not recognisable, a crowded corner, a text too small).
- `✓ review`, or `• review … the page checks itself when opened` (no browser here): done.
- `• figures … defined`: the recipe makes a figure with `define`, and the review only measures it — open the contact
  sheet once and check the figure reads as the thing it should be.
- `✗ review not checked: …`: done, but tell the person the drawing was not checked.

At most **two** rounds of fixes; then deliver and say in plain words what is left ("with 15 % the label touches the
title").

**Several lessons** (a course): one recipe each, built together — `node scripts/build.mjs one.chalk two.chalk --out
course.html --title "The course"`. **For a README** (or wherever only an image goes), when asked: `node
scripts/build.mjs <id>.chalk --svg` writes `<id>.svg`, a picture that draws itself; the lesson is still the `.html`.

## 4. Deliver

Give the path of the `.html` (or the file itself where the person downloads files) and, in one line, **what you chose
and an offer to change it**: "I tied it to a credit card bill, for someone who never studied interest, with the
monthly rate to move — want another hook, another audience or anything changed?" Then one sentence on what to look at
("press Next; in chapter 3, move the rate"). The file opens offline, with chapters, the values beside the paper, and
PNG, SVG, GIF and WebM download — it can go by e-mail or on a projector.

## For a class

When the drawing is for a class, students, a talk or a course, **ask first, in one message**: up to three hooks, best
first, each with a line on why it works for that audience (`references/hooks.md`), who exactly it is for, and which
number the students may move. Never ask what was already said. Then show the four-part outline in a few lines and
wait for the go ("pode", "go"). The recipe adds `theme chalkboard`, a `pause ask` opening the part that answers it,
and a `quiz` at the end.

## No code execution (an artifact instead)

Where you cannot run code but can show an HTML artifact, put the recipe in this small page — nothing else — and show
it. The player loads from the CDN and checks the recipe itself:

```html
<!doctype html>
<meta charset="utf-8">
<title>LESSON TITLE</title>
<script type="text/chalk-talk" id="chalk-recipe">
THE RECIPE AS TEXT
</script>
<script src="https://cdn.jsdelivr.net/npm/chalk-talk@0.14.1/player.js"></script>
```

If the page says the recipe could not be opened, fix the line it names.

## Changing it later

"Make the arrow blue", "add a second person", "use 5 % instead": change only what was asked, keep the rest, build
again and say what changed. A different hook or audience is a new drawing.

## Never

- Never edit `assets/` or `scripts/contract.mjs`: they are generated.
- Never put HTML, links, scripts or images in a recipe: texts are plain text, colours are hex or names.
- Never write a script to generate the recipe: write it yourself (expressions and `repeat` do the arithmetic).
- Without code execution, never hand-write the player, an SVG or an image of the drawing: use the small page above. If
  you can neither run code nor show an artifact, say so and give the recipe.
