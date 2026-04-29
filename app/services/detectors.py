from __future__ import annotations

import re
from typing import Iterable

from app.models import Detection


ORG_SUFFIX_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,'-]+(?:\s+[A-Z][A-Za-z0-9&.,'-]+){0,5}\s+(?:Inc|LLC|Ltd|Limited|Pvt Ltd|Corporation|Corp|Company|Co))\b"
)
NAME_INTRO_RE = re.compile(
    r"\b(?:my name is|i am|i'm|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}\b")
ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.,' -]+\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Drive|Dr)\b",
    re.IGNORECASE,
)
ID_RE = re.compile(r"\b(?:[A-Z]{2,5}-?\d{4,12}|\d{4}[- ]\d{4}[- ]\d{4})\b")
AMOUNT_RE = re.compile(
    r"(?:(?:USD|INR|EUR|GBP|Rs\.?|₹|\$|€|£)\s?)?\d[\d,]*(?:\.\d+)?(?:\s?(?:crore|lakh|million|billion|k|m))?",
    re.IGNORECASE,
)
CONFIDENTIAL_RE = re.compile(
    r"\b(password|api key|secret key|confidential|nda|internal code|token)\b",
    re.IGNORECASE,
)
PATH_RE = re.compile(r"(?:/[A-Za-z0-9._ -]+){2,}")
STRUCTURED_FIELD_RE = re.compile(r'"?([A-Za-z_][A-Za-z0-9 _-]{1,40})"?\s*[:=]\s*"?(.*?)"?(?:,|\n|$)')


class HybridPIIDetector:
    def __init__(self, enable_presidio: bool = False) -> None:
        self.enable_presidio = enable_presidio
        self._presidio_engine = None
        self._spacy_nlp = None
        if enable_presidio:
            self._bootstrap_optional_engines()

    def _bootstrap_optional_engines(self) -> None:
        try:
            from presidio_analyzer import AnalyzerEngine

            self._presidio_engine = AnalyzerEngine()
        except Exception:
            self._presidio_engine = None

        try:
            import spacy

            self._spacy_nlp = spacy.load("en_core_web_sm")
        except Exception:
            self._spacy_nlp = None

    def _iter_regex_detections(self, text: str) -> Iterable[Detection]:
        patterns = [
            ("EMAIL", EMAIL_RE, "regex"),
            ("PHONE", PHONE_RE, "regex"),
            ("ADDRESS", ADDRESS_RE, "regex"),
            ("ID", ID_RE, "regex"),
            ("FINANCIAL_AMOUNT", AMOUNT_RE, "regex"),
            ("CONFIDENTIAL_TERM", CONFIDENTIAL_RE, "regex"),
            ("FILE_PATH", PATH_RE, "regex"),
        ]
        for entity_type, pattern, source in patterns:
            for match in pattern.finditer(text):
                value = match.group(0)
                if entity_type == "FINANCIAL_AMOUNT" and not any(char.isdigit() for char in value):
                    continue
                yield Detection(
                    entity_type=entity_type,
                    start=match.start(),
                    end=match.end(),
                    value=value,
                    score=0.92,
                    source=source,
                )

        for match in NAME_INTRO_RE.finditer(text):
            yield Detection(
                entity_type="PERSON",
                start=match.start(1),
                end=match.end(1),
                value=match.group(1),
                score=0.88,
                source="heuristic",
            )

        for match in ORG_SUFFIX_RE.finditer(text):
            yield Detection(
                entity_type="ORG",
                start=match.start(1),
                end=match.end(1),
                value=match.group(1),
                score=0.9,
                source="heuristic",
            )

        for detection in self._iter_structured_field_detections(text):
            yield detection

    def _iter_structured_field_detections(self, text: str) -> Iterable[Detection]:
        person_keys = {"name", "full name", "employee", "employee_name", "customer", "client", "person"}
        org_keys = {"company", "organization", "employer", "vendor", "client_company"}
        financial_keys = {"salary", "income", "compensation", "revenue", "funding", "budget", "amount"}
        address_keys = {"address", "street", "location"}
        id_keys = {"id", "employee_id", "account_id", "passport", "ssn"}

        for match in STRUCTURED_FIELD_RE.finditer(text):
            key = match.group(1).strip().lower()
            raw_value = match.group(2).strip().strip('"').strip("'")
            if not raw_value:
                continue
            value_start = text.find(raw_value, match.start())
            if value_start < 0:
                continue
            value_end = value_start + len(raw_value)

            if key in person_keys and re.match(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}$", raw_value):
                yield Detection(
                    entity_type="PERSON",
                    start=value_start,
                    end=value_end,
                    value=raw_value,
                    score=0.86,
                    source="structured",
                )
            elif key in org_keys:
                yield Detection(
                    entity_type="ORG",
                    start=value_start,
                    end=value_end,
                    value=raw_value,
                    score=0.83,
                    source="structured",
                )
            elif key in financial_keys and any(char.isdigit() for char in raw_value):
                yield Detection(
                    entity_type="FINANCIAL_AMOUNT",
                    start=value_start,
                    end=value_end,
                    value=raw_value,
                    score=0.87,
                    source="structured",
                )
            elif key in address_keys:
                yield Detection(
                    entity_type="ADDRESS",
                    start=value_start,
                    end=value_end,
                    value=raw_value,
                    score=0.82,
                    source="structured",
                )
            elif key in id_keys:
                yield Detection(
                    entity_type="ID",
                    start=value_start,
                    end=value_end,
                    value=raw_value,
                    score=0.85,
                    source="structured",
                )

    def _iter_spacy_detections(self, text: str) -> Iterable[Detection]:
        if not self._spacy_nlp:
            return []
        label_map = {"PERSON": "PERSON", "ORG": "ORG", "GPE": "ADDRESS"}
        doc = self._spacy_nlp(text)
        detections: list[Detection] = []
        for ent in doc.ents:
            mapped = label_map.get(ent.label_)
            if not mapped:
                continue
            detections.append(
                Detection(
                    entity_type=mapped,
                    start=ent.start_char,
                    end=ent.end_char,
                    value=ent.text,
                    score=0.84,
                    source="spacy",
                )
            )
        return detections

    def _iter_presidio_detections(self, text: str) -> Iterable[Detection]:
        if not self._presidio_engine:
            return []
        detections: list[Detection] = []
        try:
            results = self._presidio_engine.analyze(text=text, language="en")
        except Exception:
            return detections
        for result in results:
            detections.append(
                Detection(
                    entity_type=result.entity_type,
                    start=result.start,
                    end=result.end,
                    value=text[result.start : result.end],
                    score=result.score,
                    source="presidio",
                )
            )
        return detections

    def detect(self, text: str) -> list[Detection]:
        candidates = list(self._iter_regex_detections(text))
        candidates.extend(self._iter_spacy_detections(text))
        candidates.extend(self._iter_presidio_detections(text))
        return self._deduplicate(candidates)

    def _deduplicate(self, detections: list[Detection]) -> list[Detection]:
        ordered = sorted(detections, key=lambda item: (item.start, -(item.end - item.start), -item.score))
        merged: list[Detection] = []
        for detection in ordered:
            if detection.value.strip() == "":
                continue
            if not merged:
                merged.append(detection)
                continue
            previous = merged[-1]
            overlaps = detection.start < previous.end and detection.end > previous.start
            if overlaps:
                prev_span = previous.end - previous.start
                new_span = detection.end - detection.start
                if detection.score > previous.score or new_span > prev_span:
                    merged[-1] = detection
            else:
                merged.append(detection)
        return merged
