"""LLMJudgeScanner — Tier 4: uses the harness LLM to evaluate safety.

Used for topic_restriction and edge cases that regex/ML can't handle.
Requires: OPENAI_API_KEY (or whatever LLM the harness uses).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# s-externalize-safety-judge-prompt: the judge persona + user-prompt body + model
# are declarable per-rule (the Guardrail/safety rule dict IS the config surface,
# like gaia_judge's declarable judges). These literals are the fallback
# last-resort — no hardcoded behaviour as the only path.
_DEFAULT_JUDGE_SYSTEM = "You are a content classifier. Respond only with valid JSON."
_DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
_DEFAULT_JUDGE_TEMPLATE = (
    "Analyze this text and determine if it stays within allowed topics.\n\n"
    "Allowed topics: {allowed}\n"
    "Denied topics: {denied}\n\n"
    "Text to analyze:\n"
    '"""\n'
    "{text}\n"
    '"""\n\n'
    "Respond with JSON only:\n"
    '{{"on_topic": true/false, "detected_topic": "topic name", '
    '"reason": "brief explanation"}}'
)


class LLMJudgeScanner:
    """Scanner that asks an LLM to evaluate text against safety rules."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._rules = [
            r
            for r in rules
            if (r.get("tier") or self._infer_tier(r)) == "llm_judge"
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
                return []

        violations: list[Violation] = []
        for rule in self._rules:
            rule_violations = self._evaluate_rule(text, rule)
            violations.extend(rule_violations)

        return violations

    def _evaluate_rule(self, text: str, rule: dict[str, Any]) -> list[Any]:
        rule_type = rule.get("type", "")

        if rule_type == "topic_restriction":
            return self._check_topic(text, rule)

        # Generic safety check
        return self._check_generic(text, rule)

    def _check_topic(self, text: str, rule: dict[str, Any]) -> list[Any]:
        from dna.safety.scanners.regex_scanner import Violation

        allowed = rule.get("allowed", [])
        denied = rule.get("denied", [])

        # Declarable per-rule (config/Kind); inline constants are the fallback.
        template = rule.get("judge_prompt") or _DEFAULT_JUDGE_TEMPLATE
        system = rule.get("judge_system") or _DEFAULT_JUDGE_SYSTEM
        model = rule.get("model") or os.environ.get("OPENAI_MODEL") or _DEFAULT_JUDGE_MODEL
        prompt = template.format(
            allowed=", ".join(allowed) if allowed else "any",
            denied=", ".join(denied) if denied else "none",
            text=text[:2000],
        )

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=150,
            )
            result_text = response.choices[0].message.content or "{}"
            # Strip markdown code fences if present
            result_text = result_text.strip()
            if result_text.startswith("```"):
                result_text = (
                    result_text.split("\n", 1)[1]
                    if "\n" in result_text
                    else result_text
                )
                if result_text.endswith("```"):
                    result_text = result_text[:-3]
                result_text = result_text.strip()

            result = json.loads(result_text)

            if not result.get("on_topic", True):
                return [
                    Violation(
                        rule_type="topic_restriction",
                        entity=result.get("detected_topic", "off_topic"),
                        text=f"[Off-topic: {result.get('reason', 'unknown')}]",
                        start=0,
                        end=len(text),
                        replacement=f"[BLOCKED: off-topic content — {result.get('detected_topic', 'unknown')}]",
                    )
                ]
        except Exception as e:
            logger.warning("LLM judge topic check failed: %s", e)

        return []

    def _check_generic(
        self, text: str, rule: dict[str, Any]
    ) -> list[Any]:
        """Generic safety evaluation for rules without specific type handlers."""
        return []  # Extensible — add more rule types as needed

    @staticmethod
    def _infer_tier(rule: dict[str, Any]) -> str:
        if rule.get("type") == "topic_restriction":
            return "llm_judge"
        return "regex"
