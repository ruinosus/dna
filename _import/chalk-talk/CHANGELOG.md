# Changelog

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
