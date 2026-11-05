# visual-explainer

Explainers that draw themselves — in a clean business look, or hand-drawn — from a small JSON **recipe** — the player behind the
[visual-explainer skill](https://github.com/ruinosus/dna). See the [gallery](https://ruinosus.github.io/dna/visual-explainer/).

## In a web page (or a claude.ai artifact)

```html
<!doctype html>
<meta charset="utf-8">
<title>My explainer</title>
<script type="application/json" id="chalk-recipe">{ "id": "my-explainer", "title": "…", "width": 900, "height": 560, "steps": [ … ] }</script>
<script src="https://cdn.jsdelivr.net/npm/@ruinosus/visual-explainer@0.22.0/player.js"></script>
```

The player builds the page around the recipe — chapters, Next / Back, values to move, the check, downloads — and needs
nothing else. A collection is `{ "collection": "Title", "explainers": [recipe, recipe, …] }`, each explainer opened with
`?explainer=n`.

## Inside an element (a note, a docs page, an app)

```js
import { mountExplainer, readRecipe } from '@ruinosus/visual-explainer/embed'

const explainer = await mountExplainer(element, readRecipe(text), { compact: true })
// … later: explainer.destroy()
```

`readRecipe` takes the text syntax or JSON (a mistake in the text says its line: `ChalkTextError`). `compact` is the
explainer for a note: chapters, Values and Expand on top, the bar below, opening on chapter 1 drawn and still. Several
explainers can share a page. A Mermaid flowchart: `readMermaid(text)` from `visual-explainer/embed-mermaid` (apart, as it carries
Mermaid).

## From the command line

```
npx @ruinosus/visual-explainer explainer.json                       # checks the recipe and writes explainer.html
npx @ruinosus/visual-explainer one.json two.json --out collection.html --title "The collection"
npx @ruinosus/visual-explainer explainer.chalk --svg                # an SVG that draws itself, for a README on GitHub
```

It checks the recipe contract, builds one HTML file that opens offline and, when Chrome, Chromium or Edge is
installed, reviews the drawing (nothing off the paper, no text over text). How to write a recipe:
[recipe.md](https://github.com/ruinosus/dna/blob/main/skills/visual-explainer/references/recipe.md).

MIT. Strokes by Rough.js (MIT); fonts Caveat and Shantell Sans (SIL Open Font License), embedded.
