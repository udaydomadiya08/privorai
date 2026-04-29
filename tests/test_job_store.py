import asyncio

from app.models import ChatResponse, PrivacyMode
from app.services.job_store import InMemoryJobStore


def test_job_store_lifecycle() -> None:
    async def scenario():
        store = InMemoryJobStore()
        record = await store.create("directory")
        await store.mark_running(record.job_id)
        await store.mark_completed(
            record.job_id,
            ChatResponse(
                session_id="s1",
                mode=PrivacyMode.HYBRID,
                original_input="orig",
                sanitized_input="safe",
                refined_prompt="safe",
                answer="ok",
                transformations=[],
                detections=[],
                provider="local",
                local_llm_used=False,
                cloud_llm_used=False,
            ),
        )
        status = await store.get(record.job_id)
        assert status is not None
        assert status.status == "completed"
        assert status.result is not None

    asyncio.run(scenario())
