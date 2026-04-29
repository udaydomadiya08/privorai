from app.models import Detection, PrivacyMode
from app.services.sanitizer import SmartSanitizer
from app.services.session_store import SessionPlaceholderStore


def test_person_placeholders_are_consistent_within_session() -> None:
    store = SessionPlaceholderStore(ttl_minutes=60)
    sanitizer = SmartSanitizer(store)
    text = "My name is Uday Domadiya and Uday Domadiya works here."
    detections = [
        Detection(entity_type="PERSON", start=11, end=24, value="Uday Domadiya"),
        Detection(entity_type="PERSON", start=29, end=42, value="Uday Domadiya"),
    ]

    result = sanitizer.sanitize("session-1", text, detections, PrivacyMode.HYBRID)
    assert result.sanitized_text.count("Person_") == 2
    replacements = {item.replacement for item in result.transformations}
    assert len(replacements) == 1


def test_financial_amounts_become_contextual_abstractions() -> None:
    store = SessionPlaceholderStore(ttl_minutes=60)
    sanitizer = SmartSanitizer(store)
    text = "I earn ₹15,43,200 per year."
    detections = [Detection(entity_type="FINANCIAL_AMOUNT", start=7, end=17, value="₹15,43,200")]

    result = sanitizer.sanitize("session-2", text, detections, PrivacyMode.HYBRID)
    assert "mid-level salary" in result.sanitized_text


def test_orgs_become_generalized_in_strict_mode() -> None:
    store = SessionPlaceholderStore(ttl_minutes=60)
    sanitizer = SmartSanitizer(store)
    text = "XYZ Pharma Pvt Ltd needs help."
    detections = [Detection(entity_type="ORG", start=0, end=18, value="XYZ Pharma Pvt Ltd")]

    result = sanitizer.sanitize("session-3", text, detections, PrivacyMode.STRICT)
    assert "sector" in result.sanitized_text
