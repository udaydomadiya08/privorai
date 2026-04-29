import asyncio

from app.services.job_store import InMemoryJobStore


def test_job_status_includes_eta_and_current_item() -> None:
    async def scenario():
        store = InMemoryJobStore()
        record = await store.create("directory")
        await store.mark_running(record.job_id, step="parsing files")
        await store.update_progress(
            record.job_id,
            progress_percent=50,
            current_step="parsing files (2/4)",
            items_processed=2,
            total_items=4,
            current_item_label="Document_B_PDF",
            current_item_parser="pypdf",
            eta_seconds=12,
            recent_items=["Document_A_TXT", "Document_B_PDF"],
        )
        status = await store.get(record.job_id)
        assert status is not None
        assert status.current_item_label == "Document_B_PDF"
        assert status.current_item_parser == "pypdf"
        assert status.eta_seconds == 12
        assert status.recent_items == ["Document_A_TXT", "Document_B_PDF"]

    asyncio.run(scenario())
