from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.models import ChatResponse, JobStatusResponse


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: str
    progress_percent: int = 0
    current_step: str = "queued"
    items_processed: int = 0
    total_items: int = 0
    current_item_label: Optional[str] = None
    current_item_parser: Optional[str] = None
    eta_seconds: Optional[int] = None
    recent_items: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[ChatResponse] = None


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, kind: str) -> JobRecord:
        async with self._lock:
            record = JobRecord(job_id=uuid4().hex, kind=kind, status="queued")
            self._jobs[record.job_id] = record
            return record

    async def mark_running(self, job_id: str, step: str = "running") -> None:
        async with self._lock:
            record = self._jobs[job_id]
            record.status = "running"
            record.current_step = step

    async def update_progress(
        self,
        job_id: str,
        *,
        progress_percent: int,
        current_step: str,
        items_processed: int,
        total_items: int,
        current_item_label: Optional[str] = None,
        current_item_parser: Optional[str] = None,
        eta_seconds: Optional[int] = None,
        recent_items: Optional[list[str]] = None,
    ) -> None:
        async with self._lock:
            record = self._jobs[job_id]
            record.status = "running"
            record.progress_percent = max(0, min(progress_percent, 100))
            record.current_step = current_step
            record.items_processed = max(0, items_processed)
            record.total_items = max(0, total_items)
            record.current_item_label = current_item_label
            record.current_item_parser = current_item_parser
            record.eta_seconds = eta_seconds
            if recent_items is not None:
                record.recent_items = recent_items[-5:]

    async def mark_completed(self, job_id: str, result: ChatResponse) -> None:
        async with self._lock:
            record = self._jobs[job_id]
            record.status = "completed"
            record.progress_percent = 100
            record.current_step = "completed"
            record.items_processed = max(record.items_processed, record.total_items)
            record.current_item_label = None
            record.current_item_parser = None
            record.eta_seconds = 0
            record.result = result
            record.completed_at = _utcnow()

    async def mark_failed(self, job_id: str, error: str) -> None:
        async with self._lock:
            record = self._jobs[job_id]
            record.status = "failed"
            record.current_step = "failed"
            record.current_item_label = None
            record.current_item_parser = None
            record.error = error
            record.completed_at = _utcnow()

    async def get(self, job_id: str) -> Optional[JobStatusResponse]:
        async with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return None
            return self._to_response(record)

    async def list(self, limit: int = 20) -> list[JobStatusResponse]:
        async with self._lock:
            records = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
            return [self._to_response(record) for record in records[:limit]]

    def _to_response(self, record: JobRecord) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=record.job_id,
            status=record.status,
            kind=record.kind,
            created_at=record.created_at.isoformat(),
            progress_percent=record.progress_percent,
            current_step=record.current_step,
            items_processed=record.items_processed,
            total_items=record.total_items,
            current_item_label=record.current_item_label,
            current_item_parser=record.current_item_parser,
            eta_seconds=record.eta_seconds,
            recent_items=record.recent_items,
            completed_at=record.completed_at.isoformat() if record.completed_at else None,
            error=record.error,
            result=record.result,
        )
