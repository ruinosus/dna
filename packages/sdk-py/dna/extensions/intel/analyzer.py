"""Analyzers — the "pass" stage of the intel pipeline (pure application logic).

An :class:`Analyzer` turns an :class:`~dna.extensions.intel` source (an
``IntelSource`` spec + a built context) into a list of *candidate* insight
dicts. It is transport-agnostic: no HTTP, no CLI, no kernel writes — it only
reads the source/context it is handed and returns candidates. The ranker scores
them and the engine persists the survivors.

A *candidate* is a plain dict with the ``IntelInsight`` authoring shape::

    {
        "title": str,            # the headline
        "fact": str,             # what happened / the cited fact
        "why": str | None,       # why it matters to this source
        "action": str | None,    # the single suggested action
        "source_ref": str,       # the IntelSource name it came from
        "pirs": list[str],       # which PIRs it matches
        "citations": list[dict], # [{url, title?}] backing the fact
        "evidence_rating": str,  # evidence-based | opinion-practice | anecdotal
    }

Two analyzers ship:

  - :class:`SeedAnalyzer` — deterministic, offline, credential-free. Returns the
    REAL insights from the DNA experiments for known sources, so the whole
    pipeline (pass → rank → suppress → deliver) runs end-to-end WITHOUT any LLM
    and the portal shows real data. It is the offline default/fallback.
  - :class:`LLMAnalyzer` — a REAL LLM research pass that works for ANY source.
    It gathers the source's CONTEXT per its ``type`` (``repo`` → README + key
    docs read from the local ``uri``; ``scope`` → the scope's docs handed in via
    ``context['documents']`` by the kernel-bound engine; ``external`` → the
    ``uri`` as a hint), folds in the PIRs, prompts the model for candidate
    insights as JSON, and parses + validates them robustly (bad/absent JSON →
    empty list + a logged warning, NEVER a crash). It mirrors how the DNA safety
    ``LLMJudgeScanner`` calls the model (``openai.OpenAI`` gated on
    ``OPENAI_API_KEY``, ``chat.completions.create``, strip code fences,
    ``json.loads``) and accepts an INJECTED client so tests mock it
    deterministically (no live key required).

Selection: :func:`select_analyzer` maps the ``--analyzer [auto|llm|seed]`` flag
to an analyzer — ``auto`` picks the LLM when ``OPENAI_API_KEY`` is set (or a
client is injected) and falls back to the Seed otherwise.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger("dna.intel.analyzer")

# ── candidate insight shape (documented above) ─────────────────────────────

Candidate = dict[str, Any]


@runtime_checkable
class Analyzer(Protocol):
    """The pluggable pass-stage contract. Implementations read ``source``
    (the IntelSource spec) + ``context`` (engine-built extras) and return a
    list of candidate insight dicts. Pure — no I/O beyond what an impl needs
    to research; NEVER writes docs (the engine owns persistence)."""

    def analyze(self, source: dict[str, Any], context: dict[str, Any]) -> list[Candidate]:
        ...


# ── SeedAnalyzer — real experiment insights, offline ───────────────────────


def _copiloto_medico_candidates() -> list[Candidate]:
    """The REAL, curated insights from ``rsh-copiloto-medico-fusion-insights``
    (the sp-fusion-validation experiment: 8 evidence-based findings + 6
    recommendations). Faithful to the Research doc on the board. One candidate
    is deliberately weak (no action, anecdotal, no PIR match) so the pipeline
    demonstrates SUPPRESSION on real seed data, not only in tests."""
    ref = "copiloto-medico"
    return [
        {
            "title": "Sugerir conduta = SaMD Classe II regulado — rache a arquitetura",
            "fact": (
                "ANVISA RDC 657/2022 regra 9: no instante em que o software indica o "
                "tratamento vira dispositivo médico regulado (SaMD Classe II). "
                "Human-in-the-loop NÃO isenta; só documentação pura é isenta."
            ),
            "why": (
                "Boltar sugestão de conduta no scribe converte um produto isento em "
                "SaMD regulado, com exposição de liability e deskilling."
            ),
            "action": (
                "Rachar a arquitetura: core-scribe ISENTO (shipa já) + módulo de "
                "sugestão-de-conduta SEPARADO, governado, em formato safety-net, "
                "planejado pra regularizar na ANVISA."
            ),
            "source_ref": ref,
            "pirs": ["regulação"],
            "citations": [],
            "evidence_rating": "evidence-based",
        },
        {
            "title": '"Sugerir conduta em tempo real" é white-space real',
            "fact": (
                "Até a Corti FactsR (jun/2025, o especialista mais avançado) para "
                'explicitamente em "o caminho PARA" decision support, sem empurrar '
                "conduta no ponto de cuidado."
            ),
            "why": (
                "O diferencial de sugerir conduta é genuíno e desocupado — mas é "
                "exatamente a linha onde a regulação morde."
            ),
            "action": (
                'Cunhar na conduta / "o que passou batido", NÃO no scribing (perde '
                "pra Voa na distribuição)."
            ),
            "source_ref": ref,
            "pirs": ["concorrentes"],
            "citations": [],
            "evidence_rating": "evidence-based",
        },
        {
            "title": "Safety-net HITL tem prova de eficácia (OpenAI–Penda)",
            "fact": (
                "Estudo OpenAI–Penda (~40k visitas, Nairóbi): um safety-net que "
                "dispara só em erro detectado cortou −16% erro diagnóstico e −13% de "
                "tratamento — mas exigiu integração profunda de prontuário, não "
                "escuta passiva."
            ),
            "why": (
                "É a prova mais forte de que o design HITL do Copiloto funciona — e "
                "valida o enquadramento safety-net como defensável clínica e "
                "legalmente."
            ),
            "action": (
                'Adotar "safety-net que ativa só em risco detectado" em vez de '
                "sugeridor sempre-ligado; orçar contexto estruturado do paciente."
            ),
            "source_ref": ref,
            "pirs": ["regulação"],
            "citations": [],
            "evidence_rating": "evidence-based",
        },
        {
            "title": "ASR médico PT-BR não é production-grade de prateleira",
            "fact": (
                "WER >30% em fala clínica e sem dataset público — precisa de LM PT-BR "
                "+ normalização (siglas/unidades/falado→documentado)."
            ),
            "why": "Um corpus proprietário PT-BR é moat de dados real, pois não há público.",
            "action": (
                "Não confiar no Whisper puro: montar stack LM médico PT-BR + "
                "normalização e começar já um corpus proprietário PT-BR."
            ),
            "source_ref": ref,
            "pirs": ["tech PT-BR"],
            "citations": [],
            "evidence_rating": "evidence-based",
        },
        {
            "title": "Voa Health já domina o scribe PT-BR — não é onde competir",
            "fact": (
                "Voa Health (60k+ médicos, seed $3M Prosus) domina o scribe PT-BR, "
                "mas é scribe, não sugeridor de conduta; iClinic Assist (Afya) está "
                "mais perto da linha."
            ),
            "why": "Entrar por scribing perde na distribuição; o diferencial está na conduta.",
            "action": (
                "Considerar complementar/integrar scribes existentes em vez de "
                "substituir; cunha na conduta."
            ),
            "source_ref": ref,
            "pirs": ["concorrentes"],
            "citations": [],
            "evidence_rating": "evidence-based",
        },
        {
            "title": 'UI "concorda/discorda" tem risco documentado de deskilling',
            "fact": (
                "Revisão superficial degrada o julgamento clínico (automation bias) — "
                "risco documentado."
            ),
            "why": '"Preserva o julgamento" vira um claim testável e diferenciador.',
            "action": (
                "Mostrar raciocínio/evidência (não só veredito); exigir justificativa "
                "ativa em aceites de alto risco; instrumentar taxa de aceite/override."
            ),
            "source_ref": ref,
            "pirs": [],
            "citations": [],
            "evidence_rating": "evidence-based",
        },
        {
            "title": "HITL NÃO blinda o médico da responsabilidade legal",
            "fact": (
                "O médico segue 100% responsável, mas usar+seguir um aid explicável "
                "historicamente PROTEGE em mock-juries."
            ),
            "why": "Design explicável é também mitigação legal — não só UX.",
            "action": (
                "Nunca deixar a IA aconselhar o paciente direto; consultar advogado "
                "regulatório/saúde BR antes de shipar a camada de conduta."
            ),
            "source_ref": ref,
            "pirs": ["regulação"],
            "citations": [],
            "evidence_rating": "opinion-practice",
        },
        {
            # Deliberately weak — no concrete action, anecdotal, no PIR match →
            # scores below the 0.6 threshold → SUPPRESSED (anti-noise demo).
            "title": "LLM clínico em PT é bom mas limitado",
            "fact": "~89% GPT-4o vs ~78% open-source no exame de residência.",
            "why": None,
            "action": None,
            "source_ref": ref,
            "pirs": [],
            "citations": [],
            "evidence_rating": "anecdotal",
        },
    ]


def _dna_cloud_candidates(source_name: str) -> list[Candidate]:
    """Seed insights for the DNA / DNA Cloud positioning + intelligence-layer
    experiments (``rsh-dna-cloud-positioning`` + ``rsh-dna-cloud-intelligence``).
    The Research docs are briefs on the board; these are the actionable
    directions they encode."""
    return [
        {
            "title": "Memory-portable é categoria lotada — lidere por Definitions",
            "fact": (
                "Mem/mem0/Zep/Letta/Cognee/Pieces + memory nativo de "
                "ChatGPT/Claude/Cursor já disputam 'memória portátil'. O que ninguém "
                "entrega é a DEFINIÇÃO declarativa (agentes/SDLC/tools) composta ao "
                "vivo e tenant-aware."
            ),
            "why": (
                "Competir em 'memória' é red ocean; o diferencial defensável do DNA é "
                "o contexto (memory + SDLC) como fonte única vendor-neutral."
            ),
            "action": (
                "Posicionar o DNA Cloud pela camada de Definitions/composição ao vivo, "
                "não como mais um app de memória."
            ),
            "source_ref": source_name,
            "pirs": ["concorrentes"],
            "citations": [],
            "evidence_rating": "opinion-practice",
        },
        {
            "title": "Willingness-to-pay do ICP time: ~$15–40k/ano",
            "fact": (
                "Times pagam por ferramentas de contexto/inteligência de portfólio na "
                "faixa de $15–40k/ano; individual dev tolera $15–40/mês (Pro $29 bate "
                "a faixa)."
            ),
            "why": "Ancora o tier Pro $29 e um Enterprise custom no ICP time/org.",
            "action": (
                "Validar o Enterprise custom no piso $15k/ano com 2–3 design partners "
                "antes de tabelar preço."
            ),
            "source_ref": source_name,
            "pirs": ["willingness-to-pay"],
            "citations": [],
            "evidence_rating": "opinion-practice",
        },
        {
            "title": "Operar-as-ferramentas (Jira/ADO/GitHub), não competir",
            "fact": (
                "Os que sobrevivem ao risco 'insight-como-ruído' agem NAS ferramentas "
                "que o time já usa e resolvem relevância/timing pelo contexto próprio."
            ),
            "why": (
                "A moat é o contexto (memory + SDLC) filtrando o que importa — um feed "
                "genérico vira ruído e é descartado."
            ),
            "action": (
                "Priorizar conectores que AGEM (abrir/atualizar work items) sobre um "
                "feed read-only; suprimir agressivamente abaixo do threshold da fonte."
            ),
            "source_ref": source_name,
            "pirs": ["moat"],
            "citations": [],
            "evidence_rating": "opinion-practice",
        },
    ]


class SeedAnalyzer:
    """Default analyzer — returns the REAL experiment insights for known
    sources, so the pipeline runs end-to-end offline (no LLM creds). Unknown
    sources yield ``[]`` (the engine then writes nothing — an honest empty
    pass). Match is by the source's ``name`` (falling back to the doc name in
    ``context``)."""

    def __init__(self) -> None:
        self._registry = {
            "copiloto-medico": _copiloto_medico_candidates(),
            "dna": _dna_cloud_candidates("dna"),
            "dna-cloud": _dna_cloud_candidates("dna-cloud"),
        }

    def analyze(self, source: dict[str, Any], context: dict[str, Any]) -> list[Candidate]:
        name = source.get("name") or context.get("source_name")
        candidates = self._registry.get(name or "")
        # Return copies so callers/ranker can annotate freely without mutating
        # the shared seed registry.
        return [dict(c) for c in (candidates or [])]


# ── context gathering — turn an IntelSource into research material ─────────

# Bounds so a big repo/scope can't blow the prompt (and the token bill) up.
_MAX_DOC_CHARS = 4000        # per document
_MAX_TOTAL_CHARS = 12000     # across all gathered material
_MAX_REPO_DOCS = 6           # extra docs/specs beyond the README
_README_CANDIDATES = ("README.md", "README.rst", "README.txt", "readme.md")
_REPO_DOC_GLOBS = (
    "ARCHITECTURE.md", "AGENTS.md", "CLAUDE.md",
    "docs/**/*.md", "specs/**/*.md", "spec/**/*.md", "design/**/*.md",
)


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:_MAX_DOC_CHARS]
    except OSError as exc:  # noqa: BLE001 — a bad file must not abort the pass
        logger.warning("intel: could not read %s: %s", path, exc)
        return ""


def _repo_material(uri: str | None) -> list[tuple[str, str]]:
    """For a ``type: repo`` source: read the README + a bounded set of key docs
    from the LOCAL checkout at ``uri`` (a filesystem path). Returns ``(label,
    text)`` chunks. Missing path / no docs → ``[]`` (an honest empty context —
    the LLM then works from the name + PIRs alone)."""
    if not uri:
        return []
    base = pathlib.Path(uri).expanduser()
    if not base.is_dir():
        return []
    chunks: list[tuple[str, str]] = []
    for cand in _README_CANDIDATES:
        p = base / cand
        if p.is_file():
            text = _read_text(p)
            if text.strip():
                chunks.append((cand, text))
            break
    seen: set[pathlib.Path] = set()
    for pattern in _REPO_DOC_GLOBS:
        for p in sorted(base.glob(pattern)):
            if len(chunks) >= _MAX_REPO_DOCS + 1:
                break
            if not p.is_file() or p in seen:
                continue
            seen.add(p)
            text = _read_text(p)
            if text.strip():
                chunks.append((str(p.relative_to(base)), text))
    return chunks


def _scope_material(context: dict[str, Any]) -> list[tuple[str, str]]:
    """For a ``type: scope`` source: the target scope's docs, pre-fetched by the
    kernel-bound engine into ``context['documents']`` (a list of ``{title/name,
    text}``). The analyzer is pure — it has no kernel — so the engine (which
    owns kernel I/O) hands the docs in via context; here we just fold them in."""
    docs = context.get("documents")
    if not isinstance(docs, list):
        return []
    chunks: list[tuple[str, str]] = []
    for d in docs:
        if not isinstance(d, dict):
            continue
        label = str(d.get("title") or d.get("name") or "doc")
        text = str(d.get("text") or d.get("body") or "")[:_MAX_DOC_CHARS]
        if text.strip():
            chunks.append((label, text))
    return chunks


def _gather_material(source: dict[str, Any], context: dict[str, Any]) -> str:
    """Assemble the research MATERIAL block for the prompt from the source's
    type-appropriate context. Always bounded to ``_MAX_TOTAL_CHARS``."""
    stype = source.get("type")
    uri = source.get("uri")
    chunks: list[tuple[str, str]] = []
    if stype == "repo":
        chunks = _repo_material(uri)
    elif stype == "scope":
        chunks = _scope_material(context)
    elif stype == "external" and uri:
        chunks = [("source uri", str(uri))]
    # scope docs may also be present for a repo/external source that the engine
    # enriched — never drop them.
    if stype != "scope":
        chunks += _scope_material(context)

    notes = source.get("notes") or context.get("notes")
    parts: list[str] = []
    if notes:
        parts.append(f"### Operator notes\n{notes}")
    total = len(parts[0]) if parts else 0
    for label, text in chunks:
        block = f"### {label}\n{text}"
        if total + len(block) > _MAX_TOTAL_CHARS:
            remaining = _MAX_TOTAL_CHARS - total
            if remaining <= 0:
                break
            block = block[:remaining]
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "(no additional context available)"


# ── LLMAnalyzer — real LLM research pass (works for ANY source) ────────────


_DEFAULT_SYSTEM = (
    "You are a portfolio-intelligence analyst. Given a watched source, the "
    "research material about it, and its Priority Intelligence Requirements "
    "(PIRs), surface concise, ACTIONABLE insights grounded in the material. "
    "Respond ONLY with valid JSON."
)
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TEMPLATE = (
    "Source: {name} (type={type})\n"
    "Priority Intelligence Requirements: {pirs}\n\n"
    "Research material:\n"
    '"""\n'
    "{material}\n"
    '"""\n\n'
    "Produce up to {k} candidate insights, grounded in the material above. Each "
    "MUST have a concrete, single suggested action. Prefer the PIRs. When the "
    "material backs a fact with a URL, include it in citations. Respond with "
    "JSON only, shape:\n"
    '{{"insights": [{{"title": str, "fact": str, "why": str, "action": str, '
    '"pirs": [str], "citations": [{{"url": str, "title": str}}], '
    '"evidence_rating": "evidence-based|opinion-practice|anecdotal"}}]}}'
)


class LLMAnalyzer:
    """Real analyzer: gather the source's context (per its ``type``) + PIRs → one
    LLM pass → candidate insights. Mirrors the DNA safety ``LLMJudgeScanner``
    wiring (``openai.OpenAI`` gated on ``OPENAI_API_KEY``,
    ``chat.completions.create``, strip code fences, ``json.loads``).

    Robust by construction: if no client is usable (no injected client AND no
    ``OPENAI_API_KEY`` / ``openai`` package), or the model returns bad/absent
    JSON, or the call fails, :meth:`analyze` logs a warning and returns ``[]`` —
    it NEVER raises into the pipeline. The engine's ``auto`` selection only
    picks the LLM when it is :meth:`available`, so the empty-return path is the
    belt-and-braces safety net, not the normal flow.

    Tests inject a fake ``client`` (any object exposing
    ``chat.completions.create(...)`` → ``.choices[0].message.content``) so they
    run deterministically without a live key.
    """

    def __init__(
        self,
        *,
        client: Any = None,
        model: str | None = None,
        k: int = 5,
    ) -> None:
        self._model = model or os.environ.get("OPENAI_MODEL") or _DEFAULT_MODEL
        self._k = k
        self._client: Any = client  # injected client wins (tests / custom wiring)

    def available(self) -> bool:
        """True when a pass can run — an injected client, or an API key to build
        the default ``openai.OpenAI`` from."""
        return self._client is not None or bool(os.environ.get("OPENAI_API_KEY"))

    def _ensure_client(self) -> Any:
        """Return the LLM client, lazily building the default ``openai.OpenAI``
        (gated on ``OPENAI_API_KEY``) if none was injected. Raises
        ``LLMAnalyzerUnavailable`` when neither is possible — caught by
        :meth:`analyze`."""
        if self._client is not None:
            return self._client
        if not os.environ.get("OPENAI_API_KEY"):
            raise LLMAnalyzerUnavailable(
                "LLMAnalyzer needs an injected client or OPENAI_API_KEY"
            )
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover — optional dep
            raise LLMAnalyzerUnavailable(
                "the 'openai' package is not installed"
            ) from exc
        self._client = OpenAI()
        return self._client

    def analyze(self, source: dict[str, Any], context: dict[str, Any]) -> list[Candidate]:
        name = source.get("name") or context.get("source_name") or "?"
        try:
            client = self._ensure_client()
            material = _gather_material(source, context)
            prompt = _DEFAULT_TEMPLATE.format(
                name=name,
                type=source.get("type", "?"),
                pirs=", ".join(source.get("pirs") or []) or "none",
                material=material,
                k=self._k,
            )
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _DEFAULT_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            text = (response.choices[0].message.content or "{}").strip()
        except LLMAnalyzerUnavailable as exc:
            logger.warning("intel: LLM analyzer unavailable for %s: %s — no candidates", name, exc)
            return []
        except Exception as exc:  # noqa: BLE001 — a failed call must not break a pass
            logger.warning("intel: LLM call failed for %s: %s — no candidates", name, exc)
            return []
        return _parse_candidates(text, name)


def _strip_code_fences(text: str) -> str:
    """Strip a leading ```lang fence and trailing ``` (mirrors LLMJudgeScanner)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    return text


def _clean_citations(raw: Any) -> list[dict[str, Any]]:
    """Keep only well-formed ``{url, title?}`` citations (the IntelInsight schema
    requires a ``url`` on each)."""
    out: list[dict[str, Any]] = []
    for c in raw or []:
        if isinstance(c, dict) and isinstance(c.get("url"), str) and c["url"].strip():
            cit: dict[str, Any] = {"url": c["url"]}
            if c.get("title"):
                cit["title"] = str(c["title"])
            out.append(cit)
    return out


def _parse_candidates(text: str, name: str) -> list[Candidate]:
    """Parse the model's JSON into validated candidates. Bad/absent JSON → ``[]``
    + a logged warning (never raises)."""
    try:
        parsed = json.loads(_strip_code_fences(text) or "{}")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("intel: LLM returned non-JSON for %s: %s — no candidates", name, exc)
        return []
    if not isinstance(parsed, dict):
        logger.warning("intel: LLM JSON for %s was not an object — no candidates", name)
        return []
    out: list[Candidate] = []
    for item in parsed.get("insights") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        out.append(
            {
                "title": str(item.get("title")),
                "fact": item.get("fact") or "",
                "why": item.get("why"),
                "action": item.get("action"),
                "source_ref": name,
                "pirs": [str(p) for p in (item.get("pirs") or [])],
                "citations": _clean_citations(item.get("citations")),
                "evidence_rating": item.get("evidence_rating") or "anecdotal",
            }
        )
    return out


class LLMAnalyzerUnavailable(RuntimeError):
    """Raised internally by :class:`LLMAnalyzer` when no LLM client / credentials
    are available. Caught by :meth:`LLMAnalyzer.analyze` (→ empty candidates);
    the engine's ``auto`` selection avoids it by only choosing the LLM when
    :meth:`LLMAnalyzer.available` is true."""


# ── selection — map the --analyzer flag to an analyzer ─────────────────────


def select_analyzer(mode: str = "auto", *, client: Any = None, **kwargs: Any) -> Analyzer:
    """Resolve the ``--analyzer [auto|llm|seed]`` flag to a concrete analyzer.

      - ``seed`` → :class:`SeedAnalyzer` (offline, credential-free).
      - ``llm``  → :class:`LLMAnalyzer` (real research pass).
      - ``auto`` → the LLM when it is available (an injected ``client`` or
        ``OPENAI_API_KEY`` is set), else the Seed — so the layer works out of the
        box offline and lights up the moment a key is present.

    ``client`` + ``kwargs`` (e.g. ``model``, ``k``) are forwarded to the
    :class:`LLMAnalyzer`. Raises ``ValueError`` on an unknown mode."""
    mode = (mode or "auto").lower()
    if mode == "seed":
        return SeedAnalyzer()
    if mode == "llm":
        return LLMAnalyzer(client=client, **kwargs)
    if mode == "auto":
        llm = LLMAnalyzer(client=client, **kwargs)
        return llm if llm.available() else SeedAnalyzer()
    raise ValueError(f"unknown analyzer mode {mode!r} — use auto, llm or seed")
