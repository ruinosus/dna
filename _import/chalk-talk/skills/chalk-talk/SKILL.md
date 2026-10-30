---
name: chalk-talk
description: Explains an idea by drawing it, the way a teacher does at the board — a hand-drawn lesson that appears stroke by stroke, chapter by chapter, with narration and values the person can move, delivered as one HTML file that opens offline. Use when someone asks to explain, teach or show something by drawing it ("explain compound interest by drawing", "draw how a web request works", "desenha pra mim como funciona…"), or wants a visual, step-by-step explanation of a concept, a process, an argument or a system for a class, a talk or themselves.
license: MIT
compatibility: Best with code execution and Node.js 18 or later (Chrome, Chromium or Edge, when installed, lets the script check the drawing first). Without code execution, an HTML artifact that loads the player from a CDN works too; the page then checks itself.
metadata:
  version: "0.10.0"
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
person says "you decide", decide and say what you chose in the outline. **This message only asks**: no outline, no
offers, nothing drawn — the outline comes after the answer.

## 2. Agree the outline before any stroke

Choose a **mold** (`references/molds.md`) and say which. Then the outline in four parts, a few lines in all:

1. **The hook as a question** — "why does a R$ 1,000 bill become R$ 1,974 in six months?"
2. **Take it apart** — draw the real thing simply and reveal what is hidden in it.
3. **The idea** — the relation, the argument, the flow; say which value moves, if any.
4. **The close** — a highlight on the result, a question to think about, and where the comparison stops.

Wait for the person's go ("pode", "go", "yes"). An edit to the outline is a new outline: show it again.

## 3. Write the recipe

Write it as **text**, one step per line (`references/text.md`: short, and the person can read and change it); what each
step draws, the expressions, the palette and the space rules are in `references/recipe.md` — read both before
writing. `references/examples/` has finished recipes in JSON (open one similar to yours if unsure); JSON still works.
If the person gives a **Mermaid diagram** (flowchart, sequence, class, state, ER, pie, timeline, journey, gantt,
xychart, quadrant, mindmap, kanban, gitGraph, sankey, block, packet, treemap, radar, requirement, C4, architecture,
ishikawa, venn, treeView), keep it as it is, add `%% title`,
`%% # chapter` and `%% > narration` lines, and build it as a `.mmd` (`references/text.md` shows how); other Mermaid kinds
are not drawn yet — say so and offer to write the lesson as text. Keep:

- 8 to 40 steps, one `chapter` on the first step of each part of the outline, one short `say` when the idea changes;
- every text in the person's language, and `locale` set to it ("en-US", "pt-BR"…) so numbers are written its way;
  facts and numbers right — never invent a quote or a figure to make it work;
- props (`person`, `house`, `bus`, `coin`, `server`, `school`, `robot`…) for people and things instead of drawing them
  stroke by stroke, a `mood` on a person, and a `balloon` when someone says or thinks something;
- `place` (beside another piece by its `id`), `row`/`column`/`grid`, `axis` and `timeline` instead of working out
  coordinates by hand whenever pieces sit next to each other, line up, or need marks along a line;
- `learning` always: goal, question, one grounded answer, and the caveat (what was simplified);
- for a class: `theme: "chalkboard"`, a `pause` with `ask` opening the part that answers it (the lesson waits), and a
  `quiz` at the end — only when the person mentions a class, students or a talk, and then in the outline (never in
  the questions of step 1).

Save it as `<id>.chalk` (or `<id>.mmd`, `<id>.json`): in the folder the person is working in, or, when an outputs
folder exists for files the person downloads (on claude.ai, `/mnt/user-data/outputs`), there. A `.md` file is read
too: each ```chalk-talk and ```mermaid block in it is a lesson.

## 4. Build and check

```
node scripts/build.mjs <id>.chalk
```

It prints a short report and writes `<id>.html` next to the recipe (`✗ text: line N: …` points at a line of the text):

- `✗ contract: …` (exit 1): the recipe breaks the format; nothing was written. Fix exactly what the message says.
- `! review …` (exit 3): drawn, but something leaves the paper, a text covers another or a line crosses a text — at
  the values shown. Move or shorten what it names.
- `✓ review` or `• review … the page checks itself when opened` (exit 0): done.

**Several lessons** (a course, a series for a class): write one recipe per lesson and build them together —
`node scripts/build.mjs one.json two.json three.json --out course.html --title "The course"` — one file with a list of
the lessons. Each lesson is checked on its own.

**For a README on GitHub** (or wherever only an image goes), when the person asks for it: `node scripts/build.mjs
<id>.chalk --svg` writes `<id>.svg`, a picture that draws itself once with no script; `![title](<id>.svg)` plays it.
It has no chapters, values or narration: the lesson is still the `.html`.

Fix and run again **at most twice**. If something is still wrong, deliver it and tell the person in plain words what is
left ("with 15 % the label of the simple interest touches the title").

## 5. Deliver

Give the path of the `.html` file (or the file itself where the person downloads files) and say in one or two
sentences what to look at: "Open it and press Next; in chapter 3, move the rate and watch the curve." The file has
chapters (Next / Back, Play all), the values beside the paper, "Think about it", and PNG, SVG, GIF and WebM
download (the GIF and the video record the lesson drawing itself — good for slides and messages). It needs no
internet and no install, so it can be sent by e-mail or projected in a class.

### No code execution (an artifact instead)

Where you cannot run code but can show an HTML artifact, put the recipe in this small page — nothing else — and show
it. The player loads from the CDN and checks the recipe itself:

```html
<!doctype html>
<meta charset="utf-8">
<title>LESSON TITLE</title>
<script type="text/chalk-talk" id="chalk-recipe">
THE RECIPE AS TEXT
</script>
<script src="https://cdn.jsdelivr.net/npm/chalk-talk@0.10.0/player.js"></script>
```

The text goes as it is (a JSON recipe also works, with `type="application/json"`; write `<` in it as `\u003c`). If
the page says the recipe could not be opened, fix the line it names.

## 6. Changing it later

"Make the arrow blue", "add a second person", "use 5 % instead": change only what was asked in the recipe, keep the
rest as it is, build again and say what changed. A different hook or mold is a new outline (step 2).

## Never

- Never draw before the person agreed the outline.
- Never edit `assets/` or `scripts/contract.mjs`: they are generated, and the player inside them is the same one the
  recipe contract was written for.
- Never put HTML, links, scripts or images in a recipe: texts are plain text, colours are hex or names.
- Never write a script to generate the recipe: write the JSON itself (expressions and `repeat` do the arithmetic).
- Without code execution, never hand-write the player, an SVG or an image of the drawing: use the small page in
  «No code execution» above. If you can neither run code nor show an artifact, say so and give the recipe.
