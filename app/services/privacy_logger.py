from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from typing import Any, Optional

from app.config import Settings
from app.models import ChatResponse


class PrivacySafeLogger:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.privacy_logging_enabled
        self.logger = logging.getLogger("privorai.privacy")
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)
        self.logger.setLevel(getattr(logging, settings.privacy_log_level.upper(), logging.INFO))
        self.logger.propagate = False

    def event(self, event_type: str, **fields: Any) -> None:
        if not self.enabled:
            return
        payload = {"event": event_type, **fields}
        self.logger.info(json.dumps(payload, sort_keys=True))

    def session_token(self, session_id: str) -> str:
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]

    def request_started(self, *, request_id: str, path: str, method: str, session_id: Optional[str] = None) -> float:
        started_at = time.perf_counter()
        self.event(
            "request_started",
            request_id=request_id,
            path=path,
            method=method,
            session=self.session_token(session_id) if session_id else None,
        )
        return started_at

    def request_completed(
        self,
        *,
        request_id: str,
        path: str,
        method: str,
        status_code: int,
        started_at: float,
    ) -> None:
        self.event(
            "request_completed",
            request_id=request_id,
            path=path,
            method=method,
            status_code=status_code,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

    def firewall_result(self, response: ChatResponse) -> None:
        self.event(
            "firewall_result",
            session=self.session_token(response.session_id),
            mode=response.mode.value,
            provider=response.provider,
            local_llm_used=response.local_llm_used,
            cloud_llm_used=response.cloud_llm_used,
            transformations=len(response.transformations),
            detections=len(response.detections),
            artifacts=len(response.artifacts),
            sanitized_chars=len(response.sanitized_input),
            refined_chars=len(response.refined_prompt),
            answer_chars=len(response.answer),
            residual_risk_level=response.residual_risk.level if response.residual_risk else None,
            residual_risk_blocked=response.residual_risk.blocked if response.residual_risk else None,
        )

    def background_progress(
        self,
        *,
        job_id: str,
        step: str,
        progress_percent: int,
        items_processed: int,
        total_items: int,
    ) -> None:
        self.event(
            "background_progress",
            job_id=job_id,
            step=step,
            progress_percent=progress_percent,
            items_processed=items_processed,
            total_items=total_items,
        )
