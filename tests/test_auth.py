import asyncio

from fastapi import HTTPException

from app.config import Settings
from app.services.auth import APIKeyAuth


def test_auth_allows_when_disabled() -> None:
    auth = APIKeyAuth(Settings(api_auth_enabled=False))
    context = asyncio.run(auth.require_user(None))
    assert context.role == "anonymous"


def test_auth_rejects_bad_token() -> None:
    auth = APIKeyAuth(Settings(api_auth_enabled=True, api_auth_token="secret"))
    try:
        asyncio.run(auth.require_user("wrong"))
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("Expected HTTPException for invalid token")


def test_user_token_cannot_access_admin_scope() -> None:
    auth = APIKeyAuth(Settings(api_auth_enabled=True, api_user_token="user-secret", api_admin_token="admin-secret"))
    context = asyncio.run(auth.require_user("user-secret"))
    assert context.role == "user"
    try:
        asyncio.run(auth.require_admin("user-secret"))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for insufficient scope")


def test_admin_token_can_access_admin_scope() -> None:
    auth = APIKeyAuth(Settings(api_auth_enabled=True, api_admin_token="admin-secret"))
    context = asyncio.run(auth.require_admin("admin-secret"))
    assert context.role == "admin"
