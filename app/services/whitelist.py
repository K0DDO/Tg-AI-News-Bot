"""Access whitelist + bot key/value settings."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminAccount
from app.models.user import User
from app.models.whitelist import BotSetting, WhitelistEntry

KEY_WHITELIST_ENABLED = "whitelist_enabled"


class WhitelistService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self._session.get(BotSetting, key)
        return row.value if row else default

    async def set_setting(self, key: str, value: str) -> None:
        row = await self._session.get(BotSetting, key)
        if row is None:
            self._session.add(BotSetting(key=key, value=value))
        else:
            row.value = value
        await self._session.commit()

    async def is_whitelist_enabled(self) -> bool:
        return (await self.get_setting(KEY_WHITELIST_ENABLED, "0")).strip() in {
            "1",
            "true",
            "yes",
            "on",
        }

    async def set_whitelist_enabled(self, enabled: bool) -> None:
        await self.set_setting(KEY_WHITELIST_ENABLED, "1" if enabled else "0")

    async def is_whitelisted(self, telegram_id: int) -> bool:
        row = (
            await self._session.execute(
                select(WhitelistEntry.id).where(WhitelistEntry.telegram_id == int(telegram_id))
            )
        ).scalar_one_or_none()
        return row is not None

    async def is_admin_telegram(self, telegram_id: int) -> bool:
        uid = (
            await self._session.execute(
                select(User.id).where(User.telegram_id == int(telegram_id))
            )
        ).scalar_one_or_none()
        if uid is None:
            return False
        acc = (
            await self._session.execute(
                select(AdminAccount.id).where(AdminAccount.user_id == uid)
            )
        ).scalar_one_or_none()
        return acc is not None

    async def can_use_bot(self, telegram_id: int) -> bool:
        """True if whitelist is off, or user is listed / is admin / is env admin."""
        from app.config import get_settings

        if int(telegram_id) in get_settings().admin_id_set():
            return True
        if not await self.is_whitelist_enabled():
            return True
        if await self.is_admin_telegram(telegram_id):
            return True
        return await self.is_whitelisted(telegram_id)

    async def add(self, telegram_id: int, note: str = "") -> WhitelistEntry:
        existing = (
            await self._session.execute(
                select(WhitelistEntry).where(WhitelistEntry.telegram_id == int(telegram_id))
            )
        ).scalar_one_or_none()
        if existing:
            if note:
                existing.note = note[:255]
            await self._session.commit()
            return existing
        entry = WhitelistEntry(telegram_id=int(telegram_id), note=(note or "")[:255])
        self._session.add(entry)
        await self._session.commit()
        return entry

    async def remove(self, telegram_id: int) -> bool:
        entry = (
            await self._session.execute(
                select(WhitelistEntry).where(WhitelistEntry.telegram_id == int(telegram_id))
            )
        ).scalar_one_or_none()
        if not entry:
            return False
        await self._session.delete(entry)
        await self._session.commit()
        return True

    async def list_entries(self, *, limit: int = 50) -> list[WhitelistEntry]:
        return list(
            (
                await self._session.execute(
                    select(WhitelistEntry)
                    .order_by(WhitelistEntry.created_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
        )
