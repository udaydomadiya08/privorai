from __future__ import annotations

import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SessionState:
    mappings: dict[str, str] = field(default_factory=dict)
    reverse_mappings: dict[str, str] = field(default_factory=dict)
    last_accessed: datetime = field(default_factory=_utcnow)


class SessionPlaceholderStore:
    def __init__(self, ttl_minutes: int = 60) -> None:
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sessions: dict[str, SessionState] = {}

    def _cleanup(self) -> None:
        now = _utcnow()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_accessed > self._ttl
        ]
        for session_id in expired:
            del self._sessions[session_id]

    def _state(self, session_id: str) -> SessionState:
        self._cleanup()
        state = self._sessions.setdefault(session_id, SessionState())
        state.last_accessed = _utcnow()
        return state

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get_or_create(self, session_id: str, key: str, prefix: str) -> str:
        state = self._state(session_id)
        compound_key = f"{prefix}:{key}"
        if compound_key not in state.mappings:
            alphabet = string.ascii_uppercase + string.digits
            token = "".join(secrets.choice(alphabet) for _ in range(4))
            value = f"{prefix}_{token}"
            state.mappings[compound_key] = value
            state.reverse_mappings[value] = key
        return state.mappings[compound_key]

    def rehydrate(self, session_id: str, text: str) -> str:
        state = self._sessions.get(session_id)
        if not state:
            return text
        hydrated = text
        for placeholder, original in state.reverse_mappings.items():
            hydrated = hydrated.replace(placeholder, original)
        return hydrated
