# Agent-facing knowledge: declarative Kinds, not generated prose

DNA represents agent-facing knowledge as **declarative, curated Kinds with
provenance** — `Research` (a synthesis of N cited References, each finding
evidence-rated), `Engram`, and the SDLC timeline itself — rather than as
LLM-generated prose (the OpenWiki / DeepWiki approach of auto-writing a repo
wiki for coding agents).

The difference is epistemic. A generated wiki page is trusted by the next agent
that reads it, so a confidently-wrong page is worse than no page. A DNA
`Research` doc is **deterministic and verifiable**: its findings carry an
`evidence_rating`, cite specific sources, and live under the same review and
lifecycle (`draft → published → superseded`) as any other tracked artifact. The
knowledge is curated once and stays auditable, instead of being regenerated and
re-trusted on every run.

This is a positioning choice, not a rejection of the tools: a generated wiki can
still be run as an external tool against the repo. But on DNA's critical path,
agent knowledge is data with a citation graph — proof over prose.
