# Digest — what happened while you were away

Not everyone watches the board live. If you **delegate** work — to a teammate,
to a coding agent, to yesterday-you — and come back to review at the end, you
don't want a forward-looking to-do list. You want a **retrospective**: what
got done, what was decided, what was found, and — first — **what now needs
you**.

That is `dna sdlc digest`.

```bash
dna sdlc digest --since 24h            # everything that happened in the last day
dna sdlc digest --since last-digest    # since the last time you ran a digest
dna sdlc digest --since 3d --save      # persist it as a queryable StatusReport
```

## Digest vs brief — backward vs forward

DNA already has forward-looking surfaces. The digest is their mirror image:

| | Direction | Answers | Audience |
|---|---|---|---|
| `dna sdlc brief` / `next` / `current` | **forward** ⏩ | "what should I do next?" | whoever is about to *start* work |
| `dna sdlc digest` | **backward** ⏪ | "what already happened?" | whoever *delegated* and reviews at the end |

`brief` opens a session; `digest` closes the loop on one. Reach for `digest`
when you were *away* — the work happened without you and you need to catch up in
one screen.

## The window — `--since`

The digest aggregates every work-item timeline event inside a window. `--since`
accepts three forms (default: the **last 24h**):

- an **ISO-8601 timestamp** — `--since 2026-07-10T00:00:00Z`;
- a **relative span** — `--since 90m` / `24h` / `3d` / `2w`;
- **`last-digest`** — resolves to the `generated_at` of the most recent saved
  digest, so consecutive digests tile the timeline with no gaps or overlaps.

## What it aggregates

The digest walks the timelines of every lifecycle Kind in the scope (Story,
Feature, Epic, Issue, ADR, Kaizen, Spike, Bug, Task, Initiative) and groups
what it finds:

- **✅ Concluído** — items that reached a terminal status in the window
  (Stories `done`, Issues `resolved`, Features `shipped`, …).
- **🧠 Decidido** — ADRs accepted plus `decision` timeline events (the *why*).
- **🔍 Achado** — Kaizens and Issues filed in the window.
- **📈 Avançou** — Features/Epics that moved without closing.
- **🚀 Releases** — git tags dated in the window.
- **📎 Artefatos** — everything `produce`d (TestGuides, TestRuns, HTML, …).

## The part that matters most — "Precisa de você"

The digest leads with a **needs-your-attention** section, because that is the
point of reviewing at the end. Unlike the rest of the digest, this section is
**not windowed** — a Story that has been blocked for three days still needs you
today. It surfaces:

- 🚧 **blocked** items, with the recorded reason;
- 👀 Stories in **review** — with their open PR numbers matched from `gh`;
- 🧭 **owner decisions** — ADRs still `proposed`, awaiting ratification;
- ❓ **open questions** — Spikes still unanswered.

The digest also carries a PMO-style **RAG status**: 🔴 red when something is
blocked, 🟡 amber when there are pending reviews/decisions/questions, 🟢 green
when nothing needs you.

```text
🗞️  Digest — dna-development  (last 24h)
   39 concluído(s) · 5 decisão(ões) · 4 achado(s) · 8 release(s) — nada precisa da sua atenção.

🔔 PRECISA DE VOCÊ (0)
   (nada pendente — tudo tocou sozinho)

✅ Concluído (39)
   • s-tool-kind-descriptor   Tool Kind → record-plane descriptor   [→done]
   ...
🧠 Decidido (5)
   • adr-dna-pivot-portability   Pivot DNA into a vendor-neutral de-para layer
   ...
```

## Persisting it — `--save`

With `--save`, the digest is written as a
[`StatusReport`](../concepts/builtin-kinds.md) named `digest-<date>` — a durable,
queryable record rather than throwaway terminal output. The report's `verdict`
and `heuristic_explanation` are embedded, so a later semantic search recalls it:

```bash
dna sdlc digest --since last-digest --save
dna cognitive search "digest dna-development"   # find past digests
```

A saved digest also anchors the next `--since last-digest` window — run one at
the end of every delegated batch and the digests form a continuous, gapless log
of "what happened, in order".

## Related

- [Your git log is your SDLC](sdlc.md) — the full lifecycle loop the digest
  reads from.
- [How to use semantic recall & memory](semantic-recall.md) — how saved
  digests become searchable.
