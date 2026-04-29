import asyncio

from app.config import Settings
from app.models import ChatResponse, PrivacyMode
from app.services.firewall import PrivacyFirewallService
from app.services.outbound_guard import OutboundPrivacyGuard


class StubDetector:
    def detect(self, text: str):
        from app.models import Detection

        return [Detection(entity_type="PERSON", start=11, end=24, value="Uday Domadiya", score=1.0, source="test")]


class StubSanitizer:
    def sanitize(self, session_id: str, text: str, detections, mode: PrivacyMode):
        from app.models import SanitizationResult, Transformation

        return SanitizationResult(
            sanitized_text="My name is Person_TEST",
            transformations=[
                Transformation(
                    entity_type="PERSON",
                    original="Uday Domadiya",
                    replacement="Person_TEST",
                    strategy="synthetic_placeholder",
                    source="test",
                )
            ],
            detections=detections,
        )


class StubLocalLLM:
    async def refine_prompt(self, sanitized_text: str, mode: PrivacyMode):
        return f"Refined: {sanitized_text}", True

    async def answer_locally(self, refined_prompt: str):
        return f"Local answer to {refined_prompt}", True

    async def generalize_web_query(self, sanitized_text: str):
        return "generic query", True


class StubCloudLLM:
    async def answer(self, refined_prompt: str):
        assert "Uday Domadiya" not in refined_prompt
        return f"Cloud answer to {refined_prompt}"


class StubWebSearch:
    async def search(self, query: str):
        from app.models import SearchResult

        assert query == "generic query"
        return SearchResult(query=query, provider="test", results=[])


def _guard() -> OutboundPrivacyGuard:
    return OutboundPrivacyGuard(Settings(block_cloud_on_residual_risk=True))


def test_firewall_never_sends_raw_input_to_cloud() -> None:
    service = PrivacyFirewallService(
        detector=StubDetector(),
        sanitizer=StubSanitizer(),
        local_llm=StubLocalLLM(),
        cloud_llm=StubCloudLLM(),
        web_search=StubWebSearch(),
        outbound_guard=_guard(),
    )

    response = asyncio.run(service.process("session", "My name is Uday Domadiya", PrivacyMode.HYBRID, False))

    assert isinstance(response, ChatResponse)
    assert response.cloud_llm_used is True
    assert response.sanitized_input == "My name is Person_TEST"


def test_fully_local_mode_avoids_cloud_calls() -> None:
    service = PrivacyFirewallService(
        detector=StubDetector(),
        sanitizer=StubSanitizer(),
        local_llm=StubLocalLLM(),
        cloud_llm=StubCloudLLM(),
        web_search=StubWebSearch(),
        outbound_guard=_guard(),
    )

    response = asyncio.run(service.process("session", "My name is Uday Domadiya", PrivacyMode.FULLY_LOCAL, True))
    assert response.cloud_llm_used is False
    assert response.provider == "local"


def test_residual_risk_blocks_cloud_when_sensitive_patterns_remain() -> None:
    class RiskyLocalLLM(StubLocalLLM):
        async def refine_prompt(self, sanitized_text: str, mode: PrivacyMode):
            return "Please inspect /Users/private/secret.txt", True

    service = PrivacyFirewallService(
        detector=StubDetector(),
        sanitizer=StubSanitizer(),
        local_llm=RiskyLocalLLM(),
        cloud_llm=StubCloudLLM(),
        web_search=StubWebSearch(),
        outbound_guard=_guard(),
    )
    response = asyncio.run(service.process("session", "My name is Uday Domadiya", PrivacyMode.HYBRID, False))
    assert response.cloud_llm_used is False
    assert response.provider == "local_privacy_block"
    assert response.residual_risk is not None
    assert response.residual_risk.blocked is True
