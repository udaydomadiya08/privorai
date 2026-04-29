from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import Settings
from app.models import AuditRecord, ChatResponse


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditSnapshotStore:
    def __init__(self, settings: Settings, base_dir: Path) -> None:
        self.settings = settings
        self.base_dir = (base_dir / settings.audit_snapshots_dir).resolve()
        self._fernet = self._build_fernet(settings.audit_encryption_key)
        if self.settings.audit_snapshots_enabled:
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def enabled(self) -> bool:
        return self.settings.audit_snapshots_enabled and self._fernet is not None

    def write(self, response: ChatResponse) -> str | None:
        if not self.enabled():
            return None
        created_at = _utcnow().isoformat()
        audit_id = uuid4().hex
        record = AuditRecord(
            audit_id=audit_id,
            session_id=response.session_id,
            created_at=created_at,
            provider=response.provider,
            mode=response.mode,
            cloud_llm_used=response.cloud_llm_used,
            local_llm_used=response.local_llm_used,
            sanitized_input=response.sanitized_input,
            refined_prompt=response.refined_prompt,
            residual_risk=response.residual_risk,
            artifacts=response.artifacts,
        )
        payload = record.model_dump_json(indent=2).encode("utf-8")
        token = self._fernet.encrypt(payload)
        (self.base_dir / f"{audit_id}.bin").write_bytes(token)
        return audit_id

    def read(self, audit_id: str) -> AuditRecord | None:
        if not self.enabled():
            return None
        path = self.base_dir / f"{audit_id}.bin"
        if not path.exists():
            return None
        token = path.read_bytes()
        payload = self._fernet.decrypt(token)
        return AuditRecord.model_validate_json(payload.decode("utf-8"))

    def list_ids(self) -> list[str]:
        if not self.enabled():
            return []
        return sorted(path.stem for path in self.base_dir.glob("*.bin"))

    def _build_fernet(self, key: str):
        if not key:
            return None
        try:
            from cryptography.fernet import Fernet
        except Exception:
            return None
        try:
            return Fernet(key.encode("utf-8"))
        except Exception:
            return None
