from app.config import Settings
from app.models import PrivacyMode
from app.services.outbound_guard import OutboundPrivacyGuard


def test_outbound_guard_blocks_paths_and_emails() -> None:
    settings = Settings(block_cloud_on_residual_risk=True)
    guard = OutboundPrivacyGuard(settings)

    risk = guard.inspect(
        sanitized_text="Generalized request",
        refined_prompt="Analyze /Users/secret/file.txt and email me at test@example.com",
        mode=PrivacyMode.HYBRID,
    )

    assert risk.blocked is True
    assert any("path" in reason for reason in risk.reasons)
    assert any("email" in reason for reason in risk.reasons)


def test_outbound_guard_allows_clean_prompt() -> None:
    settings = Settings(block_cloud_on_residual_risk=True)
    guard = OutboundPrivacyGuard(settings)

    risk = guard.inspect(
        sanitized_text="What causes revenue decline in mid-sized companies?",
        refined_prompt="What are common causes of revenue decline in mid-sized companies?",
        mode=PrivacyMode.HYBRID,
    )

    assert risk.blocked is False
    assert risk.level == "low"
