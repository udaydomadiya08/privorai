import asyncio

from app.services.job_store import InMemoryJobStore


def test_job_progress_updates() -> None:
    async def scenario():
        store = InMemoryJobStore()
        record = await store.create("directory")
        await store.mark_running(record.job_id, step="discovering files")
        await store.update_progress(
            record.job_id,
            progress_percent=42,
            current_step="parsing files (2/5)",
            items_processed=2,
            total_items=5,
        )
        status = await store.get(record.job_id)
        assert status is not None
        assert status.progress_percent == 42
        assert status.current_step == "parsing files (2/5)"
        assert status.items_processed == 2
        assert status.total_items == 5

    asyncio.run(scenario())
