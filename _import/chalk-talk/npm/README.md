# chalk-talk

Hand-drawn lessons that draw themselves, from a small JSON **recipe** — the player behind the
[chalk-talk skill](https://github.com/ruinosus/chalk-talk). See the [gallery](https://ruinosus.github.io/chalk-talk/).

## In a web page (or a claude.ai artifact)

```html
<!doctype html>
<meta charset="utf-8">
<title>My lesson</title>
<script type="application/json" id="chalk-recipe">{ "id": "my-lesson", "title": "…", "width": 900, "height": 560, "steps": [ … ] }</script>
<script src="https://cdn.jsdelivr.net/npm/chalk-talk@0.6.1/player.js"></script>
```

The player builds the page around the recipe — chapters, Next / Back, values to move, the check, downloads — and needs
nothing else. A course is `{ "course": "Title", "lessons": [recipe, recipe, …] }`, each lesson opened with
`?lesson=n`.

## From the command line

```
npx chalk-talk lesson.json                       # checks the recipe and writes lesson.html
npx chalk-talk one.json two.json --out course.html --title "The course"
```

It checks the recipe contract, builds one HTML file that opens offline and, when Chrome, Chromium or Edge is
installed, reviews the drawing (nothing off the paper, no text over text). How to write a recipe:
[recipe.md](https://github.com/ruinosus/chalk-talk/blob/main/skills/chalk-talk/references/recipe.md).

MIT. Strokes by Rough.js (MIT); fonts Caveat and Shantell Sans (SIL Open Font License), embedded.
