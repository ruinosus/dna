# back-of-napkin

Explain anything by drawing it — the command behind the
[back-of-napkin skill](https://github.com/ruinosus/back-of-napkin). See the [gallery](https://ruinosus.github.io/back-of-napkin/).

```
npx back-of-napkin pitch.chalk               # check it and build pitch.html, offline
npx back-of-napkin pitch.chalk --snapshots   # and a contact sheet of every chapter (needs Chrome, Chromium or Edge)
npx back-of-napkin pitch.chalk               # the page opens presenting (PageDown moves on, speaker notes)
npx back-of-napkin pitch.chalk --pptx steps  # pitch.pptx: static, steps or video, the narration as speaker notes
```

A recipe starts with what the drawing is for: `kind pitch`, `arch`, `decision`, `data`, `timeline` or `story`.
Exit codes: 0 drawn and checked; 1 the recipe breaks the format; 3 drawn, with something to fix. To teach a concept,
use [chalk-talk](https://www.npmjs.com/package/chalk-talk). Node.js 18 or later, nothing else. MIT.
