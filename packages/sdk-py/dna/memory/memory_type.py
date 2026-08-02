"""CoALA memory_type inference — heuristic, pure, conservative.

Ported verbatim (behavior) from the upstream ``cognitive.memory_type``.
Never overwrites an explicit ``memory_type``.

- procedural: a rule / how-to ("always X", "never Y" / pt-BR equiv).
- episodic:   an instance/event — ``area`` points at a Feature/Epic/Story/Issue.
- semantic:   a generalized fact (the default).

s-memory-verbs (2026-07-09).
"""
from __future__ import annotations

from typing import Any

_RULE_WORDS = (
    "always", "never", "must", "should", "don't", "do not", "ensure",
    "sempre", "nunca", "deve", "não ", "garanta", "evite", "prefira",
)
_EPISODIC_AREAS = ("feature/", "epic/", "story/", "issue/", "roadmap/")


def classify_memory_type(spec: dict[str, Any]) -> str:
    """Infer the CoALA memory_type for a memory spec. Respects an explicit
    ``memory_type`` when already set."""
    # ⚠️ QUALQUER tipo declarado vence a heuristica, nao so os tres conhecidos.
    #
    # A versao anterior comparava contra a tripla fechada, entao um workspace
    # que declarasse `preferencia` tinha o proprio valor SILENCIOSAMENTE
    # substituido por `semantic` — o classificador reescrevia a decisao de quem
    # sabia mais que ele, e nada avisava.
    #
    # A heuristica so opina quando NINGUEM opinou.
    existing = spec.get("memory_type")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()
    text = f"{spec.get('summary') or ''} {spec.get('body') or ''}".lower()
    if any(w in text for w in _RULE_WORDS):
        return "procedural"
    area = str(spec.get("area") or "").lower()
    if any(area.startswith(p) for p in _EPISODIC_AREAS):
        return "episodic"
    return "semantic"


__all__ = ["classify_memory_type"]
