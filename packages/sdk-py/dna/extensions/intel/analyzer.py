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
    and the portal shows real data. It is the default.
  - :class:`LLMAnalyzer` — a MINIMAL real LLM pass (one call over the source
    context + PIRs → candidate insights). Mirrors how the DNA safety
    ``LLMJudgeScanner`` calls the model (``openai.OpenAI`` gated on
    ``OPENAI_API_KEY``, ``chat.completions.create``). Without creds it raises
    cleanly — the SeedAnalyzer stays the default for the skeleton.
"""
from __future__ import annotations

import json
import os
from typing import Any, Protocol, runtime_checkable

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


# ── LLMAnalyzer — minimal real LLM pass (stub-default, no creds → clean raise) ─


_DEFAULT_SYSTEM = (
    "You are a portfolio-intelligence analyst. Given a watched source and its "
    "Priority Intelligence Requirements (PIRs), surface concise, ACTIONABLE "
    "insights. Respond ONLY with valid JSON."
)
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TEMPLATE = (
    "Source: {name} (type={type})\n"
    "Context/notes: {notes}\n"
    "Priority Intelligence Requirements: {pirs}\n\n"
    "Produce up to {k} candidate insights. Each MUST have a concrete, single "
    "suggested action. Respond with JSON only, shape:\n"
    '{{"insights": [{{"title": str, "fact": str, "why": str, "action": str, '
    '"pirs": [str], "evidence_rating": "evidence-based|opinion-practice|anecdotal"}}]}}'
)


class LLMAnalyzer:
    """MINIMAL real analyzer: one LLM pass over the source context + PIRs →
    candidate insights. Mirrors the DNA safety ``LLMJudgeScanner`` wiring
    (``openai.OpenAI`` gated on ``OPENAI_API_KEY``, ``chat.completions.create``,
    strip code fences, ``json.loads``).

    This is intentionally a minimal implementation for the walking skeleton:
    the SeedAnalyzer is the default. Without ``OPENAI_API_KEY`` (or the
    ``openai`` package) :meth:`analyze` raises ``LLMAnalyzerUnavailable`` cleanly
    rather than degrading silently — the caller falls back to the SeedAnalyzer.
    """

    def __init__(self, *, model: str | None = None, k: int = 5) -> None:
        self._model = model or os.environ.get("OPENAI_MODEL") or _DEFAULT_MODEL
        self._k = k
        self._client: Any = None

    def available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def analyze(self, source: dict[str, Any], context: dict[str, Any]) -> list[Candidate]:
        if not self.available():
            raise LLMAnalyzerUnavailable(
                "LLMAnalyzer needs OPENAI_API_KEY — falling back to SeedAnalyzer. "
                "(This is the minimal skeleton implementation.)"
            )
        if self._client is None:
            try:
                from openai import OpenAI  # noqa: PLC0415
            except ImportError as exc:  # pragma: no cover — optional dep
                raise LLMAnalyzerUnavailable(
                    "the 'openai' package is not installed — falling back to SeedAnalyzer"
                ) from exc
            self._client = OpenAI()

        name = source.get("name") or context.get("source_name") or "?"
        prompt = _DEFAULT_TEMPLATE.format(
            name=name,
            type=source.get("type", "?"),
            notes=(source.get("notes") or context.get("notes") or "none"),
            pirs=", ".join(source.get("pirs") or []) or "none",
            k=self._k,
        )
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _DEFAULT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        text = (response.choices[0].message.content or "{}").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        parsed = json.loads(text)
        out: list[Candidate] = []
        for item in parsed.get("insights", []) or []:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            out.append(
                {
                    "title": item.get("title"),
                    "fact": item.get("fact") or "",
                    "why": item.get("why"),
                    "action": item.get("action"),
                    "source_ref": name,
                    "pirs": list(item.get("pirs") or []),
                    "citations": list(item.get("citations") or []),
                    "evidence_rating": item.get("evidence_rating") or "anecdotal",
                }
            )
        return out


class LLMAnalyzerUnavailable(RuntimeError):
    """Raised by :class:`LLMAnalyzer` when no LLM credentials / client are
    available — the caller should fall back to the :class:`SeedAnalyzer`."""
