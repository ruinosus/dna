---
apiVersion: github.com/ruinosus/dna/research/v1
kind: Research
metadata:
  name: rsh-openwiki-analysis
spec:
  title: LangChain OpenWiki — analysis and fit with DNA architecture
  objective: Determine what LangChain's OpenWiki is and whether/how it fits DNA (adopt as tool, model
    as a Kind/extension, or decline).
  methodology: synthesis
  overall_confidence: moderate
  conducted_by: claude-code
  conducted_at: '2026-07-09T00:00:00+00:00'
  scope_ref: dna-development
  status: published
  visibility: shared
  owner: claude-code
  tags:
  - openwiki
  - agent-docs
  - positioning
  key_takeaways:
  - OpenWiki is a LangChain CLI+agent that LLM-GENERATES a repo wiki (openwiki/ dir) for coding agents,
    references it via a pointer appended to AGENTS.md/CLAUDE.md (not embedded), and updates via a scheduled
    GitHub Action reading git diffs
  - It is an agent-facing, generated-prose layer — DIFFERENT from human narrative docs
  - 'Key risk: a confidently-wrong generated doc is worse than none — the agent trusts it and is misled'
  - DNA's declarative Kinds (Research, LessonLearned, the SDLC timeline) are the curated+cited+deterministic
    counter-position — better for agents because verifiable
  - Modeling OpenWiki as a Kind now is premature (single vendor, first release, no spec) and would violate
    DNA's own catalog-governance discipline
  executive_summary: 'OpenWiki is a recently-released LangChain open-source CLI and agent that uses an
    LLM to generate a repository wiki (an openwiki/ directory) aimed at coding agents. Rather than embedding
    the content, it appends a pointer to the repo''s AGENTS.md / CLAUDE.md so agents can find it, and
    it keeps the wiki fresh through a scheduled GitHub Action that reads git diffs. Architecturally it
    is an agent-facing, generated-prose layer — a different thing from human-authored narrative documentation.
    Its central risk is epistemic: a confidently wrong generated page is arguably worse than no page,
    because a downstream agent trusts it and is misled. This is precisely where DNA''s design takes the
    opposite stance: DNA represents agent-facing knowledge as declarative Kinds — Research, LessonLearned,
    and the SDLC timeline — that are curated, cited, and deterministic, and therefore verifiable. The
    recommendation is not to put OpenWiki on the pre-public critical path, and not to model it as a Kind
    yet: it is single-vendor, first-release, and specless, so modeling it now would violate DNA''s own
    catalog-governance discipline. The right move is to borrow the principle (curated declarative knowledge
    with provenance), file a watch-issue for the day a real portable standard with a spec emerges, and
    use the DNA-vs-OpenWiki contrast as a thesis point in the concepts docs. This very Research doc is
    the dogfood proof of why the Research Kind matters.'
  findings:
  - id: f-use-as-tool-orthogonal
    title: Use-as-tool is orthogonal to DNA's architecture (zero arch change)
    evidence_rating: opinion-practice
    summary: 'Running the OpenWiki CLI or GitHub Action against the DNA repo requires no architectural
      change — it produces an openwiki/ directory and a pointer, entirely outside the kernel. It can be
      evaluated as a tool independently. Sources: https://github.com/langchain-ai/openwiki and https://www.langchain.com/blog/introducing-openwiki-an-open-source-agent-for-repo-documentation'
    source_refs: []
    tags:
    - tool
    - adoption
  - id: f-future-reader-possible
    title: A future market-fidelity reader under the owner's namespace IS possible
    evidence_rating: opinion-practice
    summary: 'If OpenWiki (or a successor) becomes a real portable standard with a published spec, DNA
      could model it as a reader/extension under the owner''s namespace. That is conditional on a stable
      spec existing — not the case today (first release, single vendor). Source overview: https://www.timesofai.com/news/what-is-openwiki-explained/'
    source_refs: []
    tags:
    - future
    - extension
  - id: f-positioning-thesis
    title: DNA-vs-OpenWiki positioning is itself a thesis/selling point
    evidence_rating: evidence-based
    summary: DNA represents agent-facing knowledge as declarative, curated, cited, deterministic Kinds
      (Research, LessonLearned, the SDLC timeline); OpenWiki represents it as LLM-generated prose. The
      contrast — verifiable-by-construction vs generated-and-trusted — is a clear positioning argument
      for the concepts documentation. This is confirmed by OpenWiki's own design (generated prose referenced
      from AGENTS.md/CLAUDE.md) vs DNA's cited Kinds.
    source_refs: []
    tags:
    - positioning
    - concepts
  recommendations:
  - id: rec-not-on-critical-path
    priority: high
    summary: Do NOT adopt OpenWiki on the pre-public critical path.
    backed_by_findings:
    - f-use-as-tool-orthogonal
    - f-positioning-thesis
    status: proposed
  - id: rec-watch-issue
    priority: medium
    summary: 'File a watch-issue: if a stable agent-wiki standard with a spec emerges, evaluate a reader
      under the owner namespace.'
    backed_by_findings:
    - f-future-reader-possible
    status: proposed
  - id: rec-borrow-principle
    priority: medium
    summary: Borrow the principle (curated declarative knowledge with provenance), not the tool.
    backed_by_findings:
    - f-positioning-thesis
    status: proposed
  - id: rec-document-positioning
    priority: medium
    summary: Document the DNA-vs-OpenWiki positioning in the concepts docs; this Research doc is the dogfood
      proof.
    backed_by_findings:
    - f-positioning-thesis
    status: proposed
  created_at: '2026-07-09T12:48:13+00:00'
  updated_at: '2026-07-09T12:48:13+00:00'
---

# Research — LangChain OpenWiki — analysis and fit with DNA architecture

Methodology: synthesis · 0 sources · 3 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
