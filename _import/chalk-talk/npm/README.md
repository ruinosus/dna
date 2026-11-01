# chalk-talk

Hand-drawn lessons that draw themselves, from a small JSON **recipe** — the player behind the
[chalk-talk skill](https://github.com/ruinosus/chalk-talk). See the [gallery](https://ruinosus.github.io/chalk-talk/).

## In a web page (or a claude.ai artifact)

```html
<!doctype html>
<meta charset="utf-8">
<title>My lesson</title>
<script type="application/json" id="chalk-recipe">{ "id": "my-lesson", "title": "…", "width": 900, "height": 560, "steps": [ … ] }</script>
<script src="https://cdn.jsdelivr.net/npm/chalk-talk@0.14.1/player.js"></script>
```

The player builds the page around the recipe — chapters, Next / Back, values to move, the check, downloads — and needs
nothing else. A course is `{ "course": "Title", "lessons": [recipe, recipe, …] }`, each lesson opened with
`?lesson=n`.

## Inside an element (a note, a docs page, an app)

```js
import { mountLesson, readRecipe } from 'chalk-talk/embed'

const lesson = await mountLesson(element, readRecipe(text), { compact: true })
// … later: lesson.destroy()
```

`readRecipe` takes the text syntax or JSON (a mistake in the text says its line: `ChalkTextError`). `compact` is the
lesson for a note: chapters, Values and Expand on top, the bar below, opening on chapter 1 drawn and still. Several
lessons can share a page. A Mermaid flowchart: `readMermaid(text)` from `chalk-talk/embed-mermaid` (apart, as it carries
Mermaid).

## From the command line

```
npx chalk-talk lesson.json                       # checks the recipe and writes lesson.html
npx chalk-talk one.json two.json --out course.html --title "The course"
npx chalk-talk lesson.chalk --svg                # an SVG that draws itself, for a README on GitHub
```

It checks the recipe contract, builds one HTML file that opens offline and, when Chrome, Chromium or Edge is
installed, reviews the drawing (nothing off the paper, no text over text). How to write a recipe:
[recipe.md](https://github.com/ruinosus/chalk-talk/blob/main/skills/chalk-talk/references/recipe.md).

MIT. Strokes by Rough.js (MIT); fonts Caveat and Shantell Sans (SIL Open Font License), embedded.
