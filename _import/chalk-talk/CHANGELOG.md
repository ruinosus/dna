# Changelog

## 0.9.0 — 2026-10-30

A lesson you can mount inside any element — the base of the Obsidian plugin.

- npm: `chalk-talk/embed` (`mountLesson`, `readRecipe`, `stillLesson`) mounts a lesson inside an element; several can
  share a page, the styles live under `.chalk-talk`, the keys only work while the focus is in the lesson. `compact`
  is the lesson for a note. `chalk-talk/embed-mermaid` (`readMermaid`) turns a Mermaid flowchart into a recipe in the
  browser. Types included.
- The HTML file and the CDN player mount the same lesson: nothing changes for them.

## 0.8.0 — 2026-10-30

An SVG that draws itself, for a README on GitHub.

- `build.mjs <recipe> --svg` (also `npx chalk-talk … --svg`) writes `<id>.svg`: the lesson drawn stroke by stroke with
  CSS animations and no script, so it plays inside an `<img>` — a README on GitHub included. Texts are written left to
  right, counters count, moves walk; it plays once and stays as the finished drawing, and is still from the start with
  reduced motion. Only the fonts it uses go inside. A Markdown file with several blocks gives one SVG per lesson.
- README: an example workflow that redraws the SVGs on every push.

## 0.7.0 — 2026-10-30

Write it as text — or bring a Mermaid flowchart.

- **Text recipes** (`.chalk`, or a ```chalk-talk block in Markdown): one step per line, `# chapter`, `> narration`,
  indented steps inside rows, grids and `when`, `json {…}` for anything else. Errors name the line. The skill now
  writes the recipe as text (`references/text.md`); JSON still works.
- **Mermaid, animated**: a ```mermaid flowchart (or `.mmd`) with `%% # chapter` and `%% > narration` comments becomes a
  hand-drawn lesson, drawn in the order of its arrows — the same block still renders as a plain diagram on GitHub. The
  layout comes from mermaid-to-excalidraw (MIT), bundled as `scripts/mermaid.mjs` and loaded only when needed.
- `build.mjs` reads `.json`, `.chalk`, `.mmd` and `.md` (every ```chalk-talk / ```mermaid block is a lesson; several
  make a course). A page can carry the recipe as text: `<script type="text/chalk-talk" id="chalk-recipe">`.
- Two new examples: a coin jar (text) and a coffee order (Mermaid).

## 0.6.1 — 2026-10-30

What the evals found, fixed:

- Step 1 only asks: the outline (and any offer of a chalkboard or a quiz) comes after the answer.
- The class tools (chalkboard, a question that waits, a quiz) are offered only when the person mentions a class.
- Without code execution the skill never draws an SVG by hand: it shows the artifact page, or gives the recipe.
- Releases publish themselves: a tag runs a workflow that publishes to npm (trusted publishing, no token) and creates
  the GitHub release with the skill's zip.

## 0.6.0 — 2026-10-30

- **On npm** as `chalk-talk`: `player.js` sets up the whole page around a recipe (markup, styles and fonts inside),
  so a page — or a claude.ai artifact — needs only the recipe and
  `<script src="https://cdn.jsdelivr.net/npm/chalk-talk@0.6.0/player.js">`. And `npx chalk-talk lesson.json` is the
  same `build.mjs` as a command.
- The skill works **without code execution**: it shows the recipe in that small page as an artifact.
- The player starts once the page is parsed (a page with only the recipe and the script has no body yet).
- **GitHub Pages**: the gallery is at https://ruinosus.github.io/chalk-talk/.

## 0.5.0 — 2026-10-30

Taking it further.

- **GIF and video (WebM)** of the lesson drawing itself, from the player's Download buttons (the GIF with `gifenc`,
  MIT). The recorder is the engine's own, shared with the app it comes from.
- **A course in one file**: `build.mjs one.json two.json … --out course.html --title "…"` — the lessons in a list,
  each opened with `?lesson=n`, each reviewed on its own.
- `build.mjs` only ever writes a path ending in `.html` (a second `.json` used to be taken for the output).

## 0.4.0 — 2026-10-30

A lesson for a class.

- **Chalkboard**: `theme: "chalkboard"` draws in chalk on a green board; the player has a button to switch.
- **A question that waits**: a `pause` with `ask` stops the lesson on a question until someone presses «Show me».
- **Quiz**: `quiz` in the recipe — 2 to 4 options, one right, each with why — appears when the last chapter is drawn.
- **Narration** with the browser's own voice (a button; off by default) and a **transcript** of everything the lesson
  says, by chapter.
- The page checks itself in parallel with the first chapter; the skill writes the JSON itself, never a generator.
- A new example: why the Moon has phases, for an 8th-grade class (chalkboard, a question, a quiz).

## 0.3.0 — 2026-10-30

New pieces.

- `balloon`: what a person says (speech) or thinks (thought), wrapped, on the side asked — or the first side that fits.
- `brace` (a curly brace with a label), `note` (a handwritten note with a curved arrow), `table` (cells take
  `{expr}`) and `bars` (values that follow the sliders).
- Eleven props: tree, school, hospital, factory, truck, cart, safe, bulb, gear, database, robot.
- A person's `mood`: happy, sad, surprised, worried or idea (a lit bulb above the head).
- Moving a placed piece by hand nudges it (before, it did not move).
- A new example: supply and demand at a farmers market (balloons, axes, a counter).

## 0.2.1 — 2026-10-30

- The Pythagoras example: its red circle no longer cuts the result at the sliders' maximum (found by 0.2.0's stricter
  reviewer).
- `npm run check` tests the reviewer with a line across a text: a text off the paper now comes back on its own.

## 0.2.0 — 2026-10-30

Drawing better, with fewer coordinates worked out by hand.

- `place`: a text, prop, card, counter, circle or ellipse sits below, above, left or right of another piece by its `id`.
- `row`, `column` and `grid`: pieces (or the copies of a `repeat`) measured and lined up from one corner.
- `axis` (an arrow with marks and numbers in the recipe's language) and `timeline` (marks with a label above and a
  text under).
- The drawing settles: a text, prop, card or counter that would leave the paper comes back in, and a text that would
  cover another moves a little. The old drawings are unchanged (the regression gallery shows no difference).
- The reviewer no longer lets a circle that cuts through a label pass as a highlight.
- A new example: how the printing press changed Europe (timeline, rows, grid).

## 0.1.2 — 2026-10-30

- A gallery for GitHub Pages (`docs/`): every example as a lesson to play, with a picture (`npm run site`).
- Regression snapshots (`npm run snapshots`) and the skill's eval suite (`evals/`, for `claude plugin eval`).
- Six example recipes on general topics; the player gains `#snapshot` and `#still` modes for the tools.

## 0.1.1 — 2026-10-30

- Numbers in a drawing follow the recipe's `locale` (`3.00` in English, `3,00` in Portuguese); before, they were
  always written the Portuguese way. The slider value beside the paper follows it too.
- README with the drawings: an animation, four drawings made by the skill, the player, a real conversation.

## 0.1.0 — 2026-10-30

First version.

- The skill: ask what is missing, agree a four-part outline, write the recipe, build, deliver.
- `scripts/build.mjs`: checks the recipe contract and builds one HTML file; reviews the drawing in a headless Chrome,
  Chromium or Edge when there is one (exit 3 when something leaves the paper or covers a text).
- The player: chapters, Next / Back / Play all, values and switches, «Think about it», a check when opened, PNG and
  SVG download, English or Portuguese by the browser's language; works offline.
- Props with English names (`person`, `house`, `bus`…).
