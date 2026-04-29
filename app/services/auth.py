from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Header, HTTPException

from app.config import Settings
from app.models import AuthContext


class APIKeyAuth:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def require_user(self, x_api_key: Optional[str] = Header(default=None)) -> AuthContext:
        return self._authorize(x_api_key, required_scope="chat")

    async def require_admin(self, x_api_key: Optional[str] = Header(default=None)) -> AuthContext:
        return self._authorize(x_api_key, required_scope="admin")

    def _authorize(self, presented_token: Optional[str], required_scope: str) -> AuthContext:
        if not self.settings.api_auth_enabled:
            return AuthContext(role="anonymous", scopes=["chat", "admin"])

        if not presented_token:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        tokens = self._token_map()
        if not tokens:
            raise HTTPException(status_code=500, detail="API auth is enabled but no token is configured")

        for role, data in tokens.items():
            if secrets.compare_digest(presented_token, data["token"]):
                if required_scope not in data["scopes"]:
                    raise HTTPException(status_code=403, detail="API key does not have the required scope")
                return AuthContext(role=role, scopes=data["scopes"])

        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    def _token_map(self) -> dict[str, dict[str, object]]:
        tokens: dict[str, dict[str, object]] = {}
        if self.settings.api_user_token:
            tokens["user"] = {"token": self.settings.api_user_token, "scopes": ["chat"]}
        if self.settings.api_admin_token:
            tokens["admin"] = {"token": self.settings.api_admin_token, "scopes": ["chat", "admin"]}
        if self.settings.api_auth_token:
            tokens.setdefault("legacy_admin", {"token": self.settings.api_auth_token, "scopes": ["chat", "admin"]})
        return tokens
