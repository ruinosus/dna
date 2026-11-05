<h1 align="center">visual-pitch</h1>

<p align="center"><b>Ask Claude to draw a pitch, an architecture, a decision, a number, what happened or a story. Get a hand-drawn board that draws itself, chapter by chapter, with a highlight at the end.</b></p>

<p align="center">
  <img src="https://ruinosus.github.io/dna/visual-pitch/thumbs/pitch-hr-self-service.png" alt="A hand-drawn pitch: the HR help desk queue at payroll close, then the question asked in Teams and answered from Workday, ending on «piloto: 2 áreas, 3 meses»" width="860">
</p>

<p align="center">
  An <a href="https://agentskills.io">Agent Skill</a> for Claude Code, claude.ai, the Claude API and other tools that load skills.<br>
  <a href="https://ruinosus.github.io/dna/visual-pitch/">Open the gallery</a> to play one drawing per purpose.
</p>

---

## What it does

The best explanation in a meeting is often a few strokes on a napkin: a queue, an arrow, the number that matters, and
what to do about it. visual-pitch makes Claude draw that — not a diagram that is all there at once, but **one story
with a beginning and an end, told stroke by stroke, with a highlight at the end**.

It starts from **what the drawing is for** and follows an arc for each purpose:

| Purpose | For | What it usually misses (the build says so) |
|---|---|---|
| `pitch` | convincing someone to say yes | an ask at the end |
| `arch` | how a system works, for a client or a team | what happens when something goes down |
| `decision` | choosing between options | which option wins, and why |
| `data` | a number and what to do about it | where the numbers come from |
| `timeline` | what happened, in order (a post-mortem, a history) | the line itself |
| `story` | a case, a before and after | — |

Claude writes a short text **recipe** (`.chalk`), never the drawing; `scripts/build.mjs` checks it, says what the
purpose usually misses, draws it into **one HTML file that opens offline** and — with a headless browser — checks that
nothing leaves the paper and no text covers another.

## Present it

- **In the browser:** the page opens presenting — one chapter at a time on the whole screen; a clicker's PageDown
  moves on, PageUp back, Esc stops; the speaker notes (the narration, the next chapter, a clock) open in a window of
  their own, and the values still move.
- **PowerPoint:** `--pptx` makes a slide per chapter, `--pptx steps` one per beat (the drawing grows click by click),
  `--pptx video` a video of each chapter drawing itself (MP4); the narration goes as speaker notes, and `--settings`
  adds a sequence per setting.
- **Claude's Slides:** `--slides <folder>` gives a picture and a GIF per chapter and the notes, for the Slides type.

**visual-pitch or visual-explainer?** To **teach** a concept — a class, «explain how X works by drawing» — use its sibling
[visual-explainer](https://github.com/ruinosus/dna), which draws an explainer. visual-pitch is for drawing to
**present, convince, decide, document or tell what happened**. Both draw with the same engine.

## Install

visual-pitch is one of the six skills of the [dna](../../README.md) plugin. **Claude Code:**

```
/plugin marketplace add ruinosus/dna
/plugin install dna@dna
```

Claude picks the skill by its description; to call it by name, `/dna:visual-pitch`. **claude.ai**: upload
`visual-pitch.zip` from the [latest release](https://github.com/ruinosus/dna/releases) in Settings › Capabilities ›
Skills (code execution on). **Claude API**: the same zip with the Skills API. **Other tools**: copy
`skills/visual-pitch` where the tool reads skills; it needs Node.js 18 or later. **npm**: `npx @ruinosus/dna visual-pitch <file>`.

## Develop

```
npm install       # at the repository root: the six skills are npm workspaces
npm run assets -w dev/visual-pitch/tools   # brings visual-explainer's engine from its npm package (never edit the generated files)
npm run check -w dev/visual-pitch/tools    # SKILL.md, one version, the six examples drawn clean, one warning per purpose, the refusals
npm run linux -w dev/visual-pitch/tools    # the six examples as in a cloud sandbox (Linux, root, Playwright's Chromium); needs Docker
npm run site -w dev/visual-pitch/tools     # the gallery in docs/
npm run zip -w dev/visual-pitch/tools      # dist/visual-pitch.zip
```

## Third parties

The player is visual-explainer's (MIT): strokes by Rough.js (MIT); fonts Caveat and Shantell Sans (SIL Open Font License);
animated emoji from Noto Emoji Animation (CC BY 4.0, see `assets/lottie/NOTICE.md`), played by lottie-web (MIT). The
PowerPoint is made by pptxgenjs (MIT), with JSZip inside it (dual MIT or GPLv3; used under MIT).

## License

MIT. Every example is fictional.
