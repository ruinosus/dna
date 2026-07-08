"""ScannerPipeline — orchestrates tiered safety scanners.

Tier 1 (regex) is always available.  Higher tiers are optional and
gracefully degrade when their dependencies are not installed:

- Tier 2 — ML (Presidio NER + Detoxify toxicity)
- Tier 3 — API (OpenAI Moderation)
- Tier 4 — LLM Judge (topic restriction via LLM call)
"""
from __future__ import annotations

import logging
from typing import Any

from dna.safety.scanners.regex_scanner import RegexScanner, Violation

logger = logging.getLogger(__name__)


class SafetyBlockError(Exception):
    """Raised when a safety policy with action=block detects violations."""

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        types = ", ".join(sorted({v.rule_type for v in violations}))
        super().__init__(
            f"Safety policy blocked content: {len(violations)} violation(s) [{types}]"
        )


class ScannerPipeline:
    """Orchestrates multiple scanners in tier order.

    Tier 1 (RegexScanner) is always present.  Higher tiers are loaded
    opportunistically — if their dependencies are missing or they have
    no matching rules, they are silently skipped.
    """

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self.scanners: list[Any] = []
        # Always add regex scanner (Tier 1) — it filters rules internally
        self.scanners.append(RegexScanner(rules))

        # Tier 2: ML (optional — requires presidio / detoxify)
        try:
            from dna.safety.scanners.ml_scanner import MLScanner

            ml = MLScanner(rules)
            if ml.available():
                self.scanners.append(ml)
        except Exception:  # noqa: BLE001
            pass

        # Tier 3: API (optional — requires openai + OPENAI_API_KEY)
        try:
            from dna.safety.scanners.api_scanner import APIScanner

            api = APIScanner(rules)
            if api.available():
                self.scanners.append(api)
        except Exception:  # noqa: BLE001
            pass

        # Tier 4: LLM Judge (optional — requires openai + OPENAI_API_KEY)
        try:
            from dna.safety.scanners.llm_judge import LLMJudgeScanner

            llm = LLMJudgeScanner(rules)
            if llm.available():
                self.scanners.append(llm)
        except Exception:  # noqa: BLE001
            pass

    def scan(self, text: str) -> list[Violation]:
        """Scan text through all available scanners, returning violations."""
        violations: list[Violation] = []
        for scanner in self.scanners:
            if scanner.available():
                violations.extend(scanner.scan(text))
        return violations

    def apply(self, text: str, action: str) -> str:
        """Scan text and apply the specified action.

        - mask: replace violations inline
        - block: raise SafetyBlockError
        - log: return text unchanged (caller handles logging)
        """
        violations = self.scan(text)
        if not violations:
            return text

        if action == "block":
            raise SafetyBlockError(violations)

        if action == "mask":
            # Sort by position descending to avoid offset issues
            for v in sorted(violations, key=lambda v: -v.start):
                text = text[:v.start] + v.replacement + text[v.end:]
            return text

        # action == "log" — return text unchanged
        return text
