"""RegexScanner — Tier 1 (built-in) pattern-based safety scanner.

Handles PII detection (CPF, CNPJ, email, phone, credit card) with checksum
validation where applicable, plus prompt injection heuristics, banned words,
and custom regex patterns.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _strip_accents(s: str) -> str:
    """Remove accents/diacritics for fuzzy matching (ã→a, ç→c, ā→a)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
from typing import Any


@dataclass
class Violation:
    """A single safety violation found by a scanner."""
    rule_type: str
    entity: str
    text: str
    start: int
    end: int
    replacement: str


# ---------------------------------------------------------------------------
# CPF validation (mod-11 checksum)
# ---------------------------------------------------------------------------

_CPF_PATTERN = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")


def _validate_cpf(raw: str) -> bool:
    """Validate a Brazilian CPF using mod-11 checksum."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 11:
        return False
    # Reject known invalid sequences (all same digit)
    if len(set(digits)) == 1:
        return False

    # First check digit
    total = sum(int(digits[i]) * (10 - i) for i in range(9))
    remainder = total % 11
    d1 = 0 if remainder < 2 else 11 - remainder
    if int(digits[9]) != d1:
        return False

    # Second check digit
    total = sum(int(digits[i]) * (11 - i) for i in range(10))
    remainder = total % 11
    d2 = 0 if remainder < 2 else 11 - remainder
    return int(digits[10]) == d2


# ---------------------------------------------------------------------------
# CNPJ validation (checksum)
# ---------------------------------------------------------------------------

_CNPJ_PATTERN = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")


def _validate_cnpj(raw: str) -> bool:
    """Validate a Brazilian CNPJ using checksum."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 14:
        return False
    if len(set(digits)) == 1:
        return False

    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(digits[i]) * weights1[i] for i in range(12))
    remainder = total % 11
    d1 = 0 if remainder < 2 else 11 - remainder
    if int(digits[12]) != d1:
        return False

    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(digits[i]) * weights2[i] for i in range(13))
    remainder = total % 11
    d2 = 0 if remainder < 2 else 11 - remainder
    return int(digits[13]) == d2


# ---------------------------------------------------------------------------
# Other PII patterns
# ---------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

_PHONE_PATTERN = re.compile(
    r"\+?\d{1,3}[\s.-]?\(?\d{2,3}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}"
)

_CREDIT_CARD_PATTERN = re.compile(
    r"\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}"
)


def _luhn_check(number: str) -> bool:
    """Validate a number using the Luhn algorithm."""
    digits = re.sub(r"\D", "", number)
    if not digits:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Prompt injection heuristics
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?prior\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Masking helpers
# ---------------------------------------------------------------------------

def _mask_cpf(text: str) -> str:
    return "***.***.***-**"


def _mask_cnpj(text: str) -> str:
    return "**.***.***/**.**-**"


def _mask_email(text: str) -> str:
    at_idx = text.index("@")
    domain = text[at_idx:]
    return "***" + domain


def _mask_phone(text: str) -> str:
    return "**-****-****"


def _mask_credit_card(text: str) -> str:
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 4:
        return "****-****-****-" + digits[-4:]
    return "****-****-****-****"


# ---------------------------------------------------------------------------
# RegexScanner
# ---------------------------------------------------------------------------

class RegexScanner:
    """Tier 1 scanner — pattern matching with checksum validation."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._pii_entities: set[str] = set()
        self._prompt_injection = False
        self._banned_words: list[str] = []
        self._custom_patterns: list[re.Pattern] = []

        for rule in rules:
            rule_type = rule.get("type", "")
            tier = rule.get("tier")

            # Skip non-regex tiers (ml, api, llm_judge)
            if tier and tier not in ("regex", None):
                continue

            if rule_type == "pii":
                entities = rule.get("entities", [])
                for e in entities:
                    # Only handle regex-capable entities
                    if e in ("cpf", "cnpj", "email", "phone", "credit_card"):
                        self._pii_entities.add(e)
                    # person, location need ML tier — skip silently
                if not entities:
                    # Default to all regex-capable PII entities
                    self._pii_entities.update(
                        ["cpf", "cnpj", "email", "phone", "credit_card"]
                    )
            elif rule_type == "prompt_injection":
                self._prompt_injection = True
            elif rule_type == "banned_words":
                self._banned_words.extend(rule.get("words", []))
            elif rule_type == "custom_regex":
                for pattern_str in rule.get("patterns", []):
                    try:
                        self._custom_patterns.append(re.compile(pattern_str))
                    except re.error:
                        pass  # Skip invalid patterns

    def available(self) -> bool:
        return True

    def scan(self, text: str) -> list[Violation]:
        # Normalize Unicode so LLM-generated variants (ā vs ã) match banned words
        import unicodedata
        text = unicodedata.normalize("NFC", text)
        violations: list[Violation] = []

        if "cpf" in self._pii_entities:
            for m in _CPF_PATTERN.finditer(text):
                if _validate_cpf(m.group()):
                    violations.append(Violation(
                        rule_type="pii",
                        entity="cpf",
                        text=m.group(),
                        start=m.start(),
                        end=m.end(),
                        replacement=_mask_cpf(m.group()),
                    ))

        if "cnpj" in self._pii_entities:
            for m in _CNPJ_PATTERN.finditer(text):
                if _validate_cnpj(m.group()):
                    violations.append(Violation(
                        rule_type="pii",
                        entity="cnpj",
                        text=m.group(),
                        start=m.start(),
                        end=m.end(),
                        replacement=_mask_cnpj(m.group()),
                    ))

        if "email" in self._pii_entities:
            for m in _EMAIL_PATTERN.finditer(text):
                violations.append(Violation(
                    rule_type="pii",
                    entity="email",
                    text=m.group(),
                    start=m.start(),
                    end=m.end(),
                    replacement=_mask_email(m.group()),
                ))

        if "phone" in self._pii_entities:
            for m in _PHONE_PATTERN.finditer(text):
                violations.append(Violation(
                    rule_type="pii",
                    entity="phone",
                    text=m.group(),
                    start=m.start(),
                    end=m.end(),
                    replacement=_mask_phone(m.group()),
                ))

        if "credit_card" in self._pii_entities:
            for m in _CREDIT_CARD_PATTERN.finditer(text):
                if _luhn_check(m.group()):
                    violations.append(Violation(
                        rule_type="pii",
                        entity="credit_card",
                        text=m.group(),
                        start=m.start(),
                        end=m.end(),
                        replacement=_mask_credit_card(m.group()),
                    ))

        if self._prompt_injection:
            for pattern in _INJECTION_PATTERNS:
                for m in pattern.finditer(text):
                    violations.append(Violation(
                        rule_type="prompt_injection",
                        entity="prompt_injection",
                        text=m.group(),
                        start=m.start(),
                        end=m.end(),
                        replacement="[BLOCKED]",
                    ))

        for word in self._banned_words:
            # Match with exact chars first
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            for m in pattern.finditer(text):
                violations.append(Violation(
                    rule_type="banned_words",
                    entity="banned_word",
                    text=m.group(),
                    start=m.start(),
                    end=m.end(),
                    replacement="[REDACTED]",
                ))
            # Also match on accent-stripped version (LLMs may use ā instead of ã)
            stripped_word = _strip_accents(word)
            stripped_text = _strip_accents(text)
            if stripped_word != word:  # only if word has accents
                pattern2 = re.compile(re.escape(stripped_word), re.IGNORECASE)
                for m in pattern2.finditer(stripped_text):
                    # Check we haven't already matched this position
                    already = any(v.start == m.start() and v.end == m.end() for v in violations)
                    if not already:
                        violations.append(Violation(
                            rule_type="banned_words",
                            entity="banned_word",
                            text=text[m.start():m.end()],
                            start=m.start(),
                            end=m.end(),
                            replacement="[REDACTED]",
                        ))

        for pattern in self._custom_patterns:
            for m in pattern.finditer(text):
                violations.append(Violation(
                    rule_type="custom_regex",
                    entity="custom",
                    text=m.group(),
                    start=m.start(),
                    end=m.end(),
                    replacement="[REDACTED]",
                ))

        return violations
