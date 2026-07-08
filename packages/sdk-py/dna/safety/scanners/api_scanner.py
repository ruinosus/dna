"""APIScanner — Tier 3: OpenAI Moderation API.

Requires: OPENAI_API_KEY environment variable.
Graceful degradation: if no API key, available() returns False.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class APIScanner:
    """Scanner using OpenAI Moderation API for content safety."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._rules = [
            r
            for r in rules
            if r.get("type") == "content_safety"
            and (r.get("tier") or "api") == "api"
        ]
        self._client: Any = None

    def available(self) -> bool:
        return len(self._rules) > 0 and bool(os.environ.get("OPENAI_API_KEY"))

    def scan(self, text: str) -> list[Any]:
        from dna.safety.scanners.regex_scanner import Violation

        if not self.available():
            return []

        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI()
            except ImportError:
                logger.info(
                    "openai package not installed — API content safety unavailable"
                )
                return []

        try:
            response = self._client.moderations.create(input=text)
            result = response.results[0]
        except Exception as e:
            logger.warning("OpenAI Moderation API call failed: %s", e)
            return []

        violations: list[Violation] = []
        # Map OpenAI categories to our names
        category_map = {
            "hate": "hate",
            "hate/threatening": "hate",
            "harassment": "harassment",
            "harassment/threatening": "harassment",
            "self-harm": "self_harm",
            "self-harm/intent": "self_harm",
            "self-harm/instructions": "self_harm",
            "sexual": "sexual",
            "sexual/minors": "sexual",
            "violence": "violence",
            "violence/graphic": "violence",
        }

        for rule in self._rules:
            target_categories = set(rule.get("categories", []))
            threshold = rule.get("threshold", 0.5)

            for oai_category, our_category in category_map.items():
                if target_categories and our_category not in target_categories:
                    continue

                attr_name = oai_category.replace("/", "_").replace("-", "_")
                flagged = getattr(result.categories, attr_name, False)
                score = getattr(result.category_scores, attr_name, 0.0)

                if flagged or score >= threshold:
                    violations.append(
                        Violation(
                            rule_type="content_safety",
                            entity=our_category,
                            text=f"[OpenAI flagged {oai_category}: {score:.3f}]",
                            start=0,
                            end=len(text),
                            replacement=f"[CONTENT BLOCKED: {our_category}]",
                        )
                    )
                    break  # One violation per category is enough

        return violations
