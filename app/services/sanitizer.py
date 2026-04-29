from __future__ import annotations

import re

from app.models import Detection, SanitizationResult, Transformation
from app.models import PrivacyMode
from app.services.session_store import SessionPlaceholderStore


class SmartSanitizer:
    def __init__(self, store: SessionPlaceholderStore) -> None:
        self.store = store

    def sanitize(
        self, session_id: str, text: str, detections: list[Detection], mode: PrivacyMode
    ) -> SanitizationResult:
        if not detections:
            return SanitizationResult(sanitized_text=text, transformations=[], detections=[])

        output = text
        transformations: list[Transformation] = []
        for detection in sorted(detections, key=lambda item: item.start, reverse=True):
            replacement, strategy = self._replacement_for(session_id, detection, text, mode)
            output = output[: detection.start] + replacement + output[detection.end :]
            transformations.append(
                Transformation(
                    entity_type=detection.entity_type,
                    original=detection.value,
                    replacement=replacement,
                    strategy=strategy,
                    source=detection.source,
                )
            )

        transformations.reverse()
        return SanitizationResult(
            sanitized_text=self._cleanup_spacing(output),
            transformations=transformations,
            detections=detections,
        )

    def _replacement_for(
        self, session_id: str, detection: Detection, full_text: str, mode: PrivacyMode
    ) -> tuple[str, str]:
        entity = detection.entity_type.upper()
        if entity == "PERSON":
            return self.store.get_or_create(session_id, detection.value, "Person"), "synthetic_placeholder"
        if entity == "EMAIL":
            token = self.store.get_or_create(session_id, detection.value, "Contact")
            return f"{token.lower()}@example.test", "synthetic_placeholder"
        if entity == "PHONE":
            return self.store.get_or_create(session_id, detection.value, "Phone"), "synthetic_placeholder"
        if entity == "FILE_PATH":
            return "a local file path", "semantic_abstraction"
        if entity in {"ID", "US_SSN", "CREDIT_CARD", "PASSPORT"}:
            return self.store.get_or_create(session_id, detection.value, "Identifier"), "synthetic_placeholder"
        if entity == "ORG":
            return self._abstract_org(detection.value, mode), "semantic_abstraction"
        if entity in {"ADDRESS", "LOCATION"}:
            return self._abstract_address(detection.value, mode), "semantic_abstraction"
        if entity == "FINANCIAL_AMOUNT":
            return self._abstract_financial_amount(detection.value, full_text, mode), "semantic_abstraction"
        if entity == "CONFIDENTIAL_TERM":
            return "a confidential internal reference", "semantic_rewriting"
        return "a private detail", "generic_abstraction"

    def _abstract_org(self, value: str, mode: PrivacyMode) -> str:
        lower = value.lower()
        sector_map = {
            "pharma": "pharmaceutical company",
            "bank": "financial institution",
            "health": "healthcare organization",
            "tech": "technology company",
            "software": "software company",
            "hospital": "healthcare provider",
            "retail": "retail company",
            "manufact": "manufacturing company",
            "logistics": "logistics company",
        }
        sector = "private company"
        for keyword, label in sector_map.items():
            if keyword in lower:
                sector = label
                break
        if mode == PrivacyMode.STRICT:
            return f"an organization in the {sector.split()[0]} sector"
        return f"a mid-sized {sector}"

    def _abstract_address(self, value: str, mode: PrivacyMode) -> str:
        if mode == PrivacyMode.STRICT:
            return "a private physical location"
        if re.search(r"\b(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Drive|Dr)\b", value, re.IGNORECASE):
            return "a residential street address"
        return "a private address"

    def _abstract_financial_amount(self, amount: str, full_text: str, mode: PrivacyMode) -> str:
        context = full_text.lower()
        numeric = self._parse_amount(amount)
        if numeric is None:
            return "a material financial amount"

        if any(term in context for term in {"salary", "earn", "income", "compensation"}):
            if mode == PrivacyMode.STRICT:
                return "a private income level"
            if numeric < 500000:
                return "an entry-level salary"
            if numeric < 2000000:
                return "a mid-level salary"
            return "a senior compensation level"

        if any(term in context for term in {"lost", "loss", "decline", "drop"}):
            if numeric < 100000:
                return "a modest loss"
            if numeric < 5000000:
                return "a significant loss"
            return "a major loss"

        if any(term in context for term in {"revenue", "funding", "investment", "budget"}):
            if mode == PrivacyMode.STRICT:
                return "a material business amount"
            if numeric < 1000000:
                return "a small business amount"
            if numeric < 10000000:
                return "a medium-scale business amount"
            return "a large business amount"

        return "a material financial amount"

    def _parse_amount(self, amount: str) -> float | None:
        clean = amount.lower().replace(",", "").replace("₹", "").replace("$", "").replace("€", "").replace("£", "")
        clean = clean.replace("rs.", "").replace("rs", "").replace("usd", "").replace("inr", "").replace("eur", "").replace("gbp", "")
        multiplier = 1.0
        if "crore" in clean:
            multiplier = 10_000_000
            clean = clean.replace("crore", "")
        elif "lakh" in clean:
            multiplier = 100_000
            clean = clean.replace("lakh", "")
        elif "billion" in clean:
            multiplier = 1_000_000_000
            clean = clean.replace("billion", "")
        elif "million" in clean:
            multiplier = 1_000_000
            clean = clean.replace("million", "")
        elif "k" in clean:
            multiplier = 1_000
            clean = clean.replace("k", "")
        elif "m" in clean:
            multiplier = 1_000_000
            clean = clean.replace("m", "")
        clean = clean.strip()
        try:
            return float(clean) * multiplier
        except ValueError:
            return None

    def _cleanup_spacing(self, text: str) -> str:
        return re.sub(r"\s{2,}", " ", text).strip()
