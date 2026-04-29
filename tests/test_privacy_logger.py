from app.config import Settings
from app.models import ChatResponse, PrivacyMode
from app.services.privacy_logger import PrivacySafeLogger


def test_privacy_logger_session_token_is_stable_and_redacted() -> None:
    logger = PrivacySafeLogger(Settings(privacy_logging_enabled=False))
    token_one = logger.session_token("session-123")
    token_two = logger.session_token("session-123")
    assert token_one == token_two
    assert token_one != "session-123"


def test_privacy_logger_accepts_firewall_result_without_raw_text_logging_side_effects() -> None:
    logger = PrivacySafeLogger(Settings(privacy_logging_enabled=False))
    response = ChatResponse(
        session_id="session-1",
        mode=PrivacyMode.HYBRID,
        original_input="raw input",
        sanitized_input="safe input",
        refined_prompt="safe prompt",
        answer="safe answer",
        transformations=[],
        detections=[],
        provider="local",
        local_llm_used=True,
        cloud_llm_used=False,
    )
    logger.firewall_result(response)
