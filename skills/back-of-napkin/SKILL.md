---
name: back-of-napkin
description: Explains anything by drawing it, the way you would on the back of a napkin — a pitch, an architecture, a decision, data, a timeline or a story, drawn stroke by stroke with chapters and narration in one HTML file that opens offline. Use when someone wants to present, convince, decide, document or tell what happened by drawing it ("draw the architecture so I can present it to the client", "a pitch for our pilot", "draw the post-mortem", "desenha a decisão entre as duas opções", "monta um desenho para eu apresentar"). Not for teaching a concept (a class, "explain how X works by drawing", "me explica desenhando"): that is chalk-talk's.
license: MIT
compatibility: Best with code execution and Node.js 18 or later (Chrome, Chromium or Edge, when installed, lets the script check the drawing first).
metadata:
  version: "1.9.5"
---

# back-of-napkin: explain anything by drawing it

You write a **recipe** (`<id>.chalk`, a short text) that the player in this skill draws stroke by stroke, with
chapters and a short narration; `scripts/build.mjs` checks it and builds one HTML file. Never write the player or the
HTML yourself. Paths are relative to this skill's folder.

## 1. What is it for? — then read only that arc

| kind | for | arc |
|---|---|---|
| `pitch` | convincing someone to say yes | `arcs/pitch.md` |
| `arch` | how a system works, for a client or a team | `arcs/arch.md` |
| `decision` | choosing between options | `arcs/decision.md` |
| `data` | a number and what to do about it | `arcs/data.md` |
| `timeline` | what happened, in order (a post-mortem, a history) | `arcs/timeline.md` |
| `story` | a case, a before and after | `arcs/story.md` |

Pick the kind from the request and **read that one arc, nothing else**. A request to teach («explain how X works»)
is chalk-talk's, not this skill's. Whatever the kind: **one story with a beginning and an end, told stroke by stroke,
with a highlight at the end** — without it, it is a generic diagram, and Mermaid does that better.

**Draw first:** do not ask and do not show a plan; choose the details yourself — never an invented fact or number —
and say what you chose when you deliver. Ask first only when a figure only the person has is the point (their
numbers, their names), or when they ask to see the plan.

## 2. Write the recipe

`kind <kind>` on its own line, then the arc's chapters: `# Title` opens a chapter, `> sentence` narrates; both go to
the next step. The paper is 900 × 560 (`size 900x620` for a taller board), x right and y down, a prop's `at` is where
it stands; keep 30 px from the edges. **It is one board: a chapter never clears the paper** — give each part its own
place. 12 to 25 steps.

```
kind data
title Juros compostos ↔ a fatura do cartão
locale pt-BR
size 900x560
param taxa "juros ao mês (%)" 1..15 step=1 = 8
switch atraso "pagar com atraso" off
var f = "1 + taxa/100"
```

Props: person, person-sitting, person-pointing, house, car, bus, coin, phone, document, server, bank, cloud, queue,
desk, computer, clock, lock, money-arrow, tree, school, hospital, factory, truck, cart, safe, bulb, gear, database,
robot, ship, container, warehouse, box, pallet, shop, shelf, field, cup, function, api-gateway, cache, cluster, board,
book, pencil (a person takes `mood=` happy, sad, surprised, worried or idea).

```
person ana at 150,330 "Ana" mood=worried
text "R$ 1.000 viram quanto?" at 40,64 size=36
text "paga só o mínimo" right-of ana gap 16 align=start
ana thinks "e se eu atrasar?" side=above width=200
ana -> banco "paga" -> loja "repassa"
arrow 60,350 -> 840,350 color=#2E8F62 stroke=3
highlight 90,500 -> 810,500 thickness=24
```

Things in order, without coordinates:

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

Moving in place (one or two per drawing) and a ready-made animated emoji (only when asked; the file grows to about
610 KB):

```
animate caminhao drive
lottie celebrate at 720,180 size=120
```

Numbers that follow a value, and a failure the person can switch on:

```
counter at 470,270 "1000*f^6" "R$ {v:0} em seis meses" size=34
bars box 90,320,440,180 values 1000,"1000*f^3","1000*f^6" labels hoje,"3 meses","6 meses" format="R$ {v:0}"
plot "1000*(1+taxa/100)^x" domain 0..12 range 0..4000 box 480,120,360,240
when atraso:
  text "multa de 2%" at 600,100 color=#C8442C
```

```
define xicara
  polygon 24,48 76,48 70,90 30,90 fill=#FFFFFF
  curve 74,56 90,62 72,80
xicara minha at 450,300 "minha xícara"
pause ask "Quanto vai virar a fatura em seis meses?"
```

Colours: graphite (default), #2F5BEA, #C8442C, #2E8F62, #8C8578, marker #FFE45C; three accents at most. Titles 36–44,
labels 24–34, nothing under 22. Any other step (circle, curve, card, table, axis, timeline, brace, note, move): write
it; a mistake shows how it is written, and `references/text.md` has every line. `source "…"` says where numbers
come from. No quiz: that is a lesson's.

## 3. Build and check

```
node scripts/build.mjs <id>.chalk
```

The page opens presenting (it is still the same file). Add `--no-present` only when the drawing is not to be shown to
people (a document, a note).

- `✗ purpose / text / contract …` (exit 1): fix that line as the example under it shows.
- `! <kind> …` (exit 3): what the purpose usually misses (a pitch with no ask, an architecture with no failure…).
- `! review …` (exit 3): something off the paper or over something else. Fix, and build again with `--snapshots`:
  open `<id>.snapshots/<id>.contact-sheet.png` and fix what does not read right.
- `✓ review` (or `• review … checks itself when opened`): done; `✗ review not checked`: done, say so.

At most **two** rounds of fixes; then deliver and say what is left.

## 4. Deliver

The path of the `.html` (or the file, where the person downloads files) and, in one line, **what you chose and an
offer to change it**; then one sentence on how to present it: «it opens presenting — the first key goes full screen
and opens the speaker notes; PageDown (or a clicker) moves on, Esc stops», and the value or switch to move live.

Then offer the PowerPoint in one line. When asked, build again with `--pptx` (a slide per chapter), `--pptx steps`
(the drawing grows click by click) or `--pptx video` (each chapter drawing itself); the narration goes as speaker
notes, and `--settings a,b` adds a sequence per setting (the contact sheet's names). In claude.ai, for the Slides type:
`--slides <folder>` writes `NN.png`, `NN.gif` and `notes.json` — make the deck from them, a slide per chapter, its
notes as the speaker notes.

## Never

- Never edit `assets/`, `references/` or the generated `scripts/` (`engine-build.mjs`, `contract.mjs`, `syntax.mjs`).
- Never put HTML, links or scripts in a recipe; never invent a fact, a number or a quote, and never leave a blank
  like `[__]` on the board — say it in words, and say which numbers would help when you deliver. A sample screen
  (an app, a ranking, a dashboard) shows words, not figures: «your turn is next», not «3rd · 12 min».
- Never write `kind lesson` or a quiz: teaching is chalk-talk's.
