"""Admin API dependencies (HTTP Basic)."""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session_factory

security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    settings = get_settings()
    user_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


async def get_db_session(
    _: str = Depends(require_admin),
) -> AsyncGenerator[AsyncSession, None]:
    """DB session is opened only after successful admin auth."""
    async with get_session_factory()() as session:
        yield session
