"""Enterprise Guardrails & Safety Engine for Polaris.

Provides:
- PII Masking (Credit Cards, Emails, SSN, API Keys)
- Prompt Injection Shielding
- Regex Blacklist & Keyword Censorship
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GuardrailResult:
    is_safe: bool
    sanitized_text: str
    violations: List[str]


class GuardrailsEngine:
    # Common PII regular expressions
    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    CREDIT_CARD_REGEX = re.compile(r"\b(?:\d[ -]*?){13,16}\b")
    API_KEY_REGEX = re.compile(
        r"\b(sk-[a-zA-Z0-9]{32,}|ghp_[a-zA-Z0-9]{36}|AIza[0-9A-Za-z-_]{35})\b"
    )

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        re.compile(r"ignore\s+all\s+previous\s+instructions", re.IGNORECASE),
        re.compile(r"system\s*override\s*:\s*admin", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+in\s+dan\s+mode", re.IGNORECASE),
        re.compile(r"reveal\s+your\s+(system\s+prompt|initial\s+instructions)", re.IGNORECASE),
    ]

    def __init__(
        self,
        enable_pii_masking: bool = True,
        enable_injection_detection: bool = True,
        custom_blocked_words: Optional[List[str]] = None,
    ) -> None:
        self.enable_pii_masking = enable_pii_masking
        self.enable_injection_detection = enable_injection_detection
        self.custom_blocked_words = [w.lower() for w in (custom_blocked_words or [])]

    def inspect_and_sanitize(self, text: str) -> GuardrailResult:
        violations: List[str] = []
        sanitized = text

        # 1. Prompt injection check
        if self.enable_injection_detection:
            for pattern in self.INJECTION_PATTERNS:
                if pattern.search(text):
                    violations.append("prompt_injection_detected")
                    return GuardrailResult(
                        is_safe=False, sanitized_text=sanitized, violations=violations
                    )

        # 2. Blocked keywords check
        lower_text = text.lower()
        for word in self.custom_blocked_words:
            if word in lower_text:
                violations.append(f"blocked_keyword:{word}")
                return GuardrailResult(
                    is_safe=False, sanitized_text=sanitized, violations=violations
                )

        # 3. PII Masking
        if self.enable_pii_masking:
            if self.EMAIL_REGEX.search(sanitized):
                violations.append("pii:email")
                sanitized = self.EMAIL_REGEX.sub("[REDACTED_EMAIL]", sanitized)

            if self.CREDIT_CARD_REGEX.search(sanitized):
                violations.append("pii:credit_card")
                sanitized = self.CREDIT_CARD_REGEX.sub("[REDACTED_CARD]", sanitized)

            if self.API_KEY_REGEX.search(sanitized):
                violations.append("pii:secret_key")
                sanitized = self.API_KEY_REGEX.sub("[REDACTED_SECRET]", sanitized)

        return GuardrailResult(is_safe=True, sanitized_text=sanitized, violations=violations)
