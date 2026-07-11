# Gallery — the artifacts you still need to review

You delegate work, and it comes back as **visual artifacts** — a design doc, a
before/after mockup, a decision write-up, a report. Pasted into a chat, those
get lost the moment the conversation scrolls. You end up *hunting* for the one
you were supposed to look at.

`dna sdlc gallery` fixes that. It is the **board-native index of every
`HtmlArtifact` in a scope**, grouped by the status of the work item that
produced it. Because the index is *generated from the board*, it is always
current — nothing to keep in sync by hand.

```bash
dna sdlc gallery                       # text panel — the review queue leads
dna sdlc gallery --html panel.html     # ONE self-contained page you can open
dna sdlc gallery --html panel.html --open   # …and open it in the browser
dna sdlc gallery --json                # the structured aggregate
```

## Gallery vs digest — artifacts vs events

The gallery is the sibling of [`dna sdlc digest`](sdlc-digest.md). They answer
two different "what happened while I was away" questions:

| | Shows | Answers | Reach for it when |
|---|---|---|---|
| `dna sdlc digest` | **events** — timeline changes in a window | "what *happened*?" | you want the running story of the work |
| `dna sdlc gallery` | **artifacts** — the `HtmlArtifact`s on the board | "what *visuals* do I need to review?" | you want to *look at* the deliverables |

The digest tells you a Story reached `review`; the gallery hands you the mockup
that Story produced, with a link, filed under **Precisa de avaliação**.

## How an artifact lands in a bucket

The gallery walks every work item's outputs (`produces[]` ∪ the legacy
back-refs — the same resolver the board uses) to find **which work item
produced each `HtmlArtifact`**, then buckets the artifact by that work item's
state:

- 👀 **Precisa de avaliação** — produced by a Story in `review`, *or* by any
  work item with an open PR matched to it (from `gh`). This is your queue.
- 🧭 **Decisões** — produced by an **ADR**. The visual that grounds a decision.
- ✅ **Shipado** — produced by a work item in a terminal status (`done`,
  `accepted`, `resolved`, …). Done, kept for reference.
- 📈 **Em andamento** — produced by a work item still being worked.
- 📎 **Sem work item** — an orphan: an artifact nobody `produce`d yet. Link it
  with `dna sdlc produces add <WiKind>/<wi> HtmlArtifact/<name>`.

```text
🖼️  Gallery — dna-development  (6 HtmlArtifacts)
   artefatos visuais pra revisar, agrupados pelo status do work item

🧭 Decisões (1)
   • ha-dna-vs-agentframework  DNA vs Agent Framework — pivot portabilidade
       ← ADR/adr-dna-pivot-portability [accepted]
       🔗 https://claude.ai/code/artifact/34adbfd0-…

✅ Shipado (2)
   • ha-dna-dx-antes-depois  DNA DX — Agora → Depois
       ← Epic/e-dna-dx [done]
       🔗 https://claude.ai/code/artifact/8f9006ec-…
```

## Getting artifacts onto the board

An `HtmlArtifact` stores an HTML page byte-faithfully as a first-class,
linkable work-item output. Register one, stamp its hosted URL, and link it:

```bash
dna sdlc artifact create ha-my-mockup \
    --from ./mockup.html \
    --title "Checkout redesign" \
    --description "Before/after of the checkout flow" \
    --published-url "https://claude.ai/code/artifact/…"

dna sdlc produces add Story/s-checkout HtmlArtifact/ha-my-mockup
```

The `--published-url` is the canonical hosted location (e.g. a claude.ai
artifact link). The gallery renders it as the clickable **Abrir artifact ↗**
on each card, so the panel points straight at the live page — not just the
stored bytes.

An **ADR** can produce its artifact too (its decision-visualization), which is
what lands it in the **Decisões** bucket:

```bash
dna sdlc produces add ADR/adr-my-decision HtmlArtifact/ha-decision-viz
```

## The `--html` panel

`--html <out>` writes **one self-contained HTML file** — no CDN, no external
assets, theme-aware (light/dark). Cards per artifact, a status chip, the
producing work item, the published link, and the open PRs. It is the page you
hand to whoever delegated: a board-native review surface they can open and
regenerate any time to reflect the current board.

`--open` opens the generated file in your browser (writing a temp file if you
didn't pass `--html`).

## Related

- [Digest: what happened while you were away](sdlc-digest.md) — the event-side
  sibling of the gallery.
- [Your git log is your SDLC](sdlc.md) — the lifecycle loop the gallery reads
  from.
