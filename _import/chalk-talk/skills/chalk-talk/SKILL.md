---
name: chalk-talk
description: Explains an idea by drawing it, the way a teacher does at the board — a hand-drawn lesson that appears stroke by stroke, chapter by chapter, with narration and values the person can move, delivered as one HTML file that opens offline. Use when someone asks to explain, teach or show something by drawing it ("explain compound interest by drawing", "draw how a web request works", "desenha pra mim como funciona…"), or wants a visual, step-by-step explanation of a concept, a process, an argument or a system for a class, a talk or themselves.
license: MIT
compatibility: Needs code execution with Node.js 18 or later. Chrome, Chromium or Edge, when installed, lets the script check the drawing before delivering it; without one, the page checks itself when opened.
metadata:
  version: "0.2.1"
---

# chalk-talk: explain by drawing

You make a hand-drawn explanation: a **recipe** (JSON) that the player in this skill draws stroke by stroke, with
chapters, a short narration and, when there is a real quantity, a value the person moves. You write only the recipe;
`scripts/build.mjs` checks it and builds one HTML file with everything inside. Never write or copy the player yourself.

Paths below are relative to this skill's folder (the folder this file is in).

## 1. Ask only what is missing — once, all together

Three things make a drawing:

- **the hook**: a thing of everyday life the idea is tied to (a card bill, a bus stop, a café queue) — read
  `references/hooks.md`;
- **who it is for** (a 14-year-old, a team of engineers, a class);
- **which number the person moves**, if any (the monthly rate, people arriving per minute) — or none.

Never ask what the person already said. Offer up to 3 hooks, best first, each with one line on why it works. If the
person says "you decide", decide and say what you chose in the outline.

## 2. Agree the outline before any stroke

Choose a **mold** (`references/molds.md`) and say which. Then the outline in four parts, a few lines in all:

1. **The hook as a question** — "why does a R$ 1,000 bill become R$ 1,974 in six months?"
2. **Take it apart** — draw the real thing simply and reveal what is hidden in it.
3. **The idea** — the relation, the argument, the flow; say which value moves, if any.
4. **The close** — a highlight on the result, a question to think about, and where the comparison stops.

Wait for the person's go ("pode", "go", "yes"). An edit to the outline is a new outline: show it again.

## 3. Write the recipe

Read `references/recipe.md` before writing: the step types, the expressions, the palette, the space rules and an
example. `references/examples/` has seven finished recipes (open one similar to yours if unsure). Keep:

- 8 to 40 steps, one `chapter` on the first step of each part of the outline, one short `say` when the idea changes;
- every text in the person's language, and `locale` set to it ("en-US", "pt-BR"…) so numbers are written its way;
  facts and numbers right — never invent a quote or a figure to make it work;
- props (`person`, `house`, `bus`, `coin`, `server`…) for people and things instead of drawing them stroke by stroke;
- `place` (beside another piece by its `id`), `row`/`column`/`grid`, `axis` and `timeline` instead of working out
  coordinates by hand whenever pieces sit next to each other, line up, or need marks along a line;
- `learning` always: goal, question, one grounded answer, and the caveat (what was simplified).

Save it as `<id>.json`: in the folder the person is working in, or, when an outputs folder exists for files the person
downloads (on claude.ai, `/mnt/user-data/outputs`), there.

## 4. Build and check

```
node scripts/build.mjs <id>.json
```

It prints a short report and writes `<id>.html` next to the recipe:

- `✗ contract: …` (exit 1): the recipe breaks the format; nothing was written. Fix exactly what the message says.
- `! review …` (exit 3): drawn, but something leaves the paper, a text covers another or a line crosses a text — at
  the values shown. Move or shorten what it names.
- `✓ review` or `• review … the page checks itself when opened` (exit 0): done.

Fix and run again **at most twice**. If something is still wrong, deliver it and tell the person in plain words what is
left ("with 15 % the label of the simple interest touches the title").

## 5. Deliver

Give the path of the `.html` file (or the file itself where the person downloads files) and say in one or two
sentences what to look at: "Open it and press Next; in chapter 3, move the rate and watch the curve." The file has
chapters (Next / Back, Play all), the values beside the paper, "Think about it", and PNG/SVG download. It needs no
internet and no install, so it can be sent by e-mail or projected in a class.

## 6. Changing it later

"Make the arrow blue", "add a second person", "use 5 % instead": change only what was asked in the recipe, keep the
rest as it is, build again and say what changed. A different hook or mold is a new outline (step 2).

## Never

- Never draw before the person agreed the outline.
- Never edit `assets/` or `scripts/contract.mjs`: they are generated, and the player inside them is the same one the
  recipe contract was written for.
- Never put HTML, links, scripts or images in a recipe: texts are plain text, colours are hex or names.
- Without code execution, say that this skill needs it to build the drawing and stop; do not hand-write the HTML.
