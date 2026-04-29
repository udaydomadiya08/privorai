import asyncio

from app.services.job_store import InMemoryJobStore


def test_job_store_lists_recent_jobs() -> None:
    async def scenario():
        store = InMemoryJobStore()
        first = await store.create("directory")
        second = await store.create("directory")
        jobs = await store.list()
        assert len(jobs) == 2
        assert jobs[0].job_id == second.job_id
        assert jobs[1].job_id == first.job_id

    asyncio.run(scenario())
