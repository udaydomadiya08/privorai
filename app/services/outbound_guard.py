from __future__ import annotations

import re

from app.config import Settings
from app.models import PrivacyMode, ResidualRisk


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}\b")
ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.,' -]+\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Drive|Dr)\b",
    re.IGNORECASE,
)
RAW_PATH_RE = re.compile(r"(?:/[A-Za-z0-9._-]+)+")
PERSON_PLACEHOLDER_RE = re.compile(r"\bPerson_[A-Z0-9]{4}\b")
CONTACT_PLACEHOLDER_RE = re.compile(r"\bcontact_[a-z0-9]{4}@example\.test\b", re.IGNORECASE)
IDENTIFIER_RE = re.compile(r"\b[A-Z]{2,5}-?\d{4,12}\b")


class OutboundPrivacyGuard:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def inspect(self, sanitized_text: str, refined_prompt: str, mode: PrivacyMode) -> ResidualRisk:
        reasons: list[str] = []
        candidate = refined_prompt.strip()
        email_candidate = CONTACT_PLACEHOLDER_RE.sub("", candidate)

        if len(candidate) > self.settings.max_outbound_prompt_chars:
            reasons.append("refined prompt exceeds outbound size budget")

        if EMAIL_RE.search(email_candidate):
            reasons.append("residual email-like pattern found")
        if PHONE_RE.search(candidate):
            reasons.append("residual phone-like pattern found")
        if ADDRESS_RE.search(candidate):
            reasons.append("residual address-like pattern found")
        if RAW_PATH_RE.search(candidate):
            reasons.append("filesystem path pattern found in outbound prompt")
        if IDENTIFIER_RE.search(candidate):
            reasons.append("identifier-like token remains in outbound prompt")

        if mode == PrivacyMode.STRICT and PERSON_PLACEHOLDER_RE.search(candidate):
            reasons.append("strict mode still contains person placeholder tokens")

        blocked = bool(reasons) and self.settings.block_cloud_on_residual_risk
        level = "high" if blocked else ("medium" if reasons else "low")
        preview = sanitized_text[:300]
        return ResidualRisk(level=level, blocked=blocked, reasons=reasons, sanitized_preview=preview)

    def trim(self, refined_prompt: str) -> str:
        if len(refined_prompt) <= self.settings.max_outbound_prompt_chars:
            return refined_prompt
        return refined_prompt[: self.settings.max_outbound_prompt_chars].rstrip()
