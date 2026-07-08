"""MLScanner — Tier 2: NER (Presidio) + toxicity (Detoxify).

Requires: pip install dna-sdk[safety-ml]
  -> presidio-analyzer, presidio-anonymizer, spacy, detoxify

Graceful degradation: if deps not installed, available() returns False.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy imports — only loaded if available
_presidio_available: bool | None = None
_detoxify_available: bool | None = None


def _check_presidio() -> bool:
    global _presidio_available
    if _presidio_available is None:
        try:
            import presidio_analyzer  # noqa: F401

            _presidio_available = True
        except ImportError:
            _presidio_available = False
            logger.info(
                "presidio-analyzer not installed — ML PII detection unavailable"
            )
    return _presidio_available


def _check_detoxify() -> bool:
    global _detoxify_available
    if _detoxify_available is None:
        try:
            import detoxify  # noqa: F401

            _detoxify_available = True
        except ImportError:
            _detoxify_available = False
            logger.info(
                "detoxify not installed — toxicity detection unavailable"
            )
    return _detoxify_available


class MLScanner:
    """Scanner using Presidio NER for person/location + Detoxify for toxicity."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._pii_entities: list[str] = []
        self._content_rules: list[dict[str, Any]] = []
        self._analyzer: Any = None
        self._detoxify_model: Any = None

        for rule in rules:
            tier = rule.get("tier") or self._infer_tier(rule)
            if tier != "ml":
                continue
            if rule.get("type") == "pii":
                self._pii_entities.extend(rule.get("entities", []))
            elif rule.get("type") == "content_safety":
                self._content_rules.append(rule)

    def available(self) -> bool:
        has_pii = len(self._pii_entities) > 0 and _check_presidio()
        has_content = len(self._content_rules) > 0 and _check_detoxify()
        return has_pii or has_content

    def scan(self, text: str) -> list[Any]:
        """Returns list of Violation objects."""
        from dna.safety.scanners.regex_scanner import Violation

        violations: list[Violation] = []

        # PII via Presidio
        if self._pii_entities and _check_presidio():
            violations.extend(self._scan_presidio(text))

        # Toxicity via Detoxify
        if self._content_rules and _check_detoxify():
            violations.extend(self._scan_detoxify(text))

        return violations

    def _scan_presidio(self, text: str) -> list[Any]:
        from dna.safety.scanners.regex_scanner import Violation

        if self._analyzer is None:
            from presidio_analyzer import AnalyzerEngine

            self._analyzer = AnalyzerEngine()

        # Map our entity names to Presidio entity types
        entity_map = {
            "person": "PERSON",
            "location": "LOCATION",
            "phone": "PHONE_NUMBER",
            "email": "EMAIL_ADDRESS",
            "credit_card": "CREDIT_CARD",
        }
        presidio_entities = []
        for e in self._pii_entities:
            if e in entity_map:
                presidio_entities.append(entity_map[e])

        if not presidio_entities:
            return []

        # Try English first (most recognizers available), then Portuguese
        results = []
        for lang in ("en", "pt"):
            try:
                results = self._analyzer.analyze(
                    text=text, entities=presidio_entities, language=lang
                )
                break  # Use first language that has matching recognizers
            except ValueError:
                # No recognizers for this language + entity combo — try next
                continue

        violations = []
        for r in results:
            entity_name = next(
                (k for k, v in entity_map.items() if v == r.entity_type),
                r.entity_type,
            )
            matched_text = text[r.start : r.end]
            violations.append(
                Violation(
                    rule_type="pii",
                    entity=entity_name,
                    text=matched_text,
                    start=r.start,
                    end=r.end,
                    replacement=f"[{entity_name.upper()}]",
                )
            )
        return violations

    def _scan_detoxify(self, text: str) -> list[Any]:
        from dna.safety.scanners.regex_scanner import Violation

        if self._detoxify_model is None:
            from detoxify import Detoxify

            self._detoxify_model = Detoxify("multilingual")

        results = self._detoxify_model.predict(text)
        violations = []

        # Map Detoxify output keys to our category names
        category_map = {
            "toxicity": "toxicity",
            "severe_toxicity": "severe_toxicity",
            "obscene": "obscene",
            "threat": "violence",
            "insult": "harassment",
            "identity_attack": "hate",
            "sexual_explicit": "sexual",
        }

        for rule in self._content_rules:
            categories = set(rule.get("categories", []))
            threshold = rule.get("threshold", 0.7)

            for detox_key, our_category in category_map.items():
                if our_category in categories or not categories:
                    score = results.get(detox_key, 0)
                    if score >= threshold:
                        violations.append(
                            Violation(
                                rule_type="content_safety",
                                entity=our_category,
                                text=f"[content scored {score:.2f} for {our_category}]",
                                start=0,
                                end=len(text),
                                replacement=f"[CONTENT BLOCKED: {our_category} score={score:.2f}]",
                            )
                        )
        return violations

    @staticmethod
    def _infer_tier(rule: dict[str, Any]) -> str:
        if rule.get("type") == "pii":
            entities = rule.get("entities", [])
            if any(e in ("person", "location") for e in entities):
                return "ml"
        if rule.get("type") == "content_safety":
            return "ml"  # Default content safety to ML if not specified
        return "regex"
