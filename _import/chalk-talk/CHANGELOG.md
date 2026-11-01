# Changelog

## 0.13.0 — 2026-11-01

Things that pass something along, and more things to draw.

- **`chain`:** a line of pieces spread over the paper, each joined to the next, with the long `forward` and `back`
  arrows if asked. It also takes `direction=down` and `wrap` (more lines). The coffee chain of the roadmap is now
  written with one coordinate.
- **16 new props** (45 in all):
  - logistics: ship, container, warehouse, box, pallet, shop, shelf, field, cup;
  - cloud: function, api-gateway, cache, cluster;
  - school: board, book, pencil.
- **`define`:** a prop the recipe makes itself from polygons, polylines, curves and circles, on a 0–100 grid of whole
  numbers (y down, standing at 50,100). Up to 8 per recipe, of up to 24 shapes each.
- **`a -> b "label" -> c "label"`** in the text: a link per arrow, each label right after its end.
- **Balloons:** a balloon slides along the side it was asked for before trying another (a person at the paper's edge
  keeps it above).
- The cheat sheet has `chain`, `define` and the new props. The coffee eval (3 runs) used `chain` every time, read no
  reference file before writing, and drew the first lesson in 36 s with no round of fixes.

## 0.12.0 — 2026-11-01

Draws first, and checks itself in a second or two — in cloud sandboxes too.

- **Draws first.** For an ordinary request Claude no longer asks and shows an outline: it chooses the everyday hook,
  who it is for and the value to move, draws, and then says in a line what it chose and offers to change it. It still
  asks first for a class, students, a talk or a course, when the request could mean two things, or when asked to.
- **A cheat sheet in SKILL.md** covers the usual drawing (the header, props, placing, links, balloons, counters, bars,
  plots, `when`, `pause ask`, quizzes, `learning`) and says that a chapter never clears the paper: one board. The
  references are opened only for a step that is not in it.
- **A mistake shows how its line is written:** under `✗ text: line N …` or `✗ contract: Step N …` the build prints
  «write it like:» with a line of that kind that builds (`scripts/syntax.mjs`; the checks build every example and
  keep the cheat sheet in step with them).
- **The review talks to the browser over a pipe** (the DevTools protocol) instead of `--dump-dom`, which hung until a
  90 s timeout on some machines. It finds Playwright's Chromium too, runs without the sandbox as root on Linux, tries
  the next browser when one fails, says at once when a page cannot open, and gives up on a browser after 20 s
  (`--review-timeout`). A build with its review takes one to two seconds. «not checked» is said as such.
- **`--snapshots [folder]`:** a PNG of each chapter as it ends at each setting the review tries, and a contact sheet of
  them all — what Claude opens in the round of fixes.
- Evals: six fixed requests that measure speed (`--tag speed`, `tools/eval-metrics.mjs`), and the five vague requests
  now expect a drawing at once. First drawing in 28–41 s instead of 49–70 s, with no reference read before writing.

## 0.11.0 — 2026-10-30

All of Mermaid.

- Every kind of Mermaid 11.17 becomes a hand-drawn lesson (zenuml, a plugin apart, is the only one left out): pie,
  timeline, journey, gantt, xychart, quadrant, mindmap, kanban, gitGraph, sankey, block, packet, treemap, radar,
  requirement, C4, architecture, ishikawa, venn, treeView, cynefin, eventmodeling, railroad (EBNF, ABNF, PEG) and wardley,
  besides flowchart, sequence, class, state and ER. Each is drawn in a layout of its own, step by step; a `%% #` before
  a section, task, slice, branch, column or rule opens a chapter, and with none each section is one.
- sankey, wardley and eventmodeling are read by chalk-talk itself, so names with accents work (Mermaid's own lexers
  refuse them).
- The Mermaid support now carries Mermaid's parser: `scripts/mermaid.mjs` and `chalk-talk/embed-mermaid` are larger
  (about 1.3 MB gzipped), still loaded only for a Mermaid block. A new example: a sankey from the bean to the cup.

## 0.10.0 — 2026-10-30

More of Mermaid, and the lesson in VS Code and docs sites.

- **Mermaid:** sequence, class, state and ER diagrams are drawn too (a sequence top to bottom, message by message; ER
  relations with their cardinality written at the ends), and flowchart nodes keep their shape — stadium, cylinder,
  hexagon, parallelograms, trapezoids, flag, subroutine, double circle. Other kinds (pie, gantt…) say they are not
  drawn yet.
- npm: `chalk-talk/markdown` (`remarkChalkTalk`, `markdownItChalkTalk`) turns ```chalk-talk and ```chalk-mermaid fences
  into blocks, and `chalk-talk/mount` (or `mount.global.js`, one script) turns the blocks into lessons — the ones on the
  page and the ones that appear later. «Expand» opens the whole lesson in a dialog.

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
