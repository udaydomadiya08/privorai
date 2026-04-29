from pathlib import Path

from cryptography.fernet import Fernet

from app.config import Settings
from app.models import ChatResponse, PrivacyMode
from app.services.audit_store import AuditSnapshotStore


def test_audit_store_round_trip(tmp_path: Path) -> None:
    settings = Settings(
        audit_snapshots_enabled=True,
        audit_snapshots_dir="audits",
        audit_encryption_key=Fernet.generate_key().decode("utf-8"),
    )
    store = AuditSnapshotStore(settings, tmp_path)
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

    audit_id = store.write(response)
    assert audit_id is not None
    record = store.read(audit_id)
    assert record is not None
    assert record.sanitized_input == "safe input"
    assert record.refined_prompt == "safe prompt"


def test_audit_store_disabled_without_key(tmp_path: Path) -> None:
    settings = Settings(
        audit_snapshots_enabled=True,
        audit_snapshots_dir="audits",
        audit_encryption_key="",
    )
    store = AuditSnapshotStore(settings, tmp_path)
    assert store.enabled() is False
