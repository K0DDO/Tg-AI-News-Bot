"""Channel management shared by bot, admin API, and worker."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BackfillJob, Channel, User, UserChannel


class ChannelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_user(self, telegram_id: int, username: str | None = None) -> User:
        from datetime import datetime, timezone

        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if user:
            if username and user.username != username:
                user.username = username
            user.last_seen_at = now
            return user
        user = User(telegram_id=telegram_id, username=username, last_seen_at=now)
        self._session.add(user)
        await self._session.flush()
        return user

    async def upsert_channel(
        self,
        *,
        telegram_id: int,
        title: str,
        username: str | None = None,
        enabled: bool = True,
    ) -> Channel:
        result = await self._session.execute(
            select(Channel).where(Channel.telegram_id == telegram_id)
        )
        channel = result.scalar_one_or_none()
        if channel:
            channel.title = title
            if username is not None:
                channel.username = username.lstrip("@") if username else None
            if enabled:
                channel.enabled = True
            return channel
        channel = Channel(
            telegram_id=telegram_id,
            title=title,
            username=username.lstrip("@") if username else None,
            enabled=enabled,
        )
        self._session.add(channel)
        await self._session.flush()
        return channel

    async def link_user_channel(self, user: User, channel: Channel, *, is_active: bool = True) -> UserChannel:
        result = await self._session.execute(
            select(UserChannel).where(
                UserChannel.user_id == user.id,
                UserChannel.channel_id == channel.id,
            )
        )
        link = result.scalar_one_or_none()
        if link:
            link.is_active = is_active
            return link
        link = UserChannel(user_id=user.id, channel_id=channel.id, is_active=is_active)
        self._session.add(link)
        await self._session.flush()
        return link

    async def add_channel_for_user(
        self,
        user: User,
        *,
        telegram_id: int,
        title: str,
        username: str | None = None,
        backfill_days: int = 2,
        create_job: bool = True,
    ) -> Channel:
        channel = await self.upsert_channel(
            telegram_id=telegram_id,
            title=title,
            username=username,
            enabled=True,
        )
        channel.enabled = True
        days = max(1, min(int(backfill_days), 30))
        existing = channel.pending_backfill_days or 0
        channel.pending_backfill_days = max(existing, days)
        await self.link_user_channel(user, channel, is_active=True)
        await self._session.flush()
        if create_job:
            await self.create_backfill_job(user.id, days=days, channel_ids=[channel.id])
        await self._session.commit()
        await self._session.refresh(channel)
        return channel

    async def create_backfill_job(
        self,
        user_id: int,
        *,
        days: int,
        channel_ids: list[int],
    ) -> BackfillJob | None:
        if not channel_ids:
            return None
        job = BackfillJob(
            user_id=user_id,
            days=max(1, min(int(days), 30)),
            status="queued",
            channel_ids=list(channel_ids),
            done_channel_ids=[],
            messages_fetched=0,
            events_processed=0,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def request_backfill_for_user(self, user_id: int, *, days: int) -> BackfillJob | None:
        """Mark active user channels for history backfill and create a progress job."""
        days = max(1, min(int(days), 30))
        pairs = await self.list_user_channels(user_id)
        channel_ids: list[int] = []
        for channel, link in pairs:
            if not link.is_active:
                continue
            existing = channel.pending_backfill_days or 0
            channel.pending_backfill_days = max(existing, days)
            channel.enabled = True
            channel_ids.append(channel.id)
        if not channel_ids:
            await self._session.commit()
            return None
        job = await self.create_backfill_job(user_id, days=days, channel_ids=channel_ids)
        await self._session.commit()
        if job:
            await self._session.refresh(job)
        return job

    async def get_backfill_job(self, job_id: int) -> BackfillJob | None:
        return await self._session.get(BackfillJob, job_id)

    async def list_active_backfill_jobs(self) -> list[BackfillJob]:
        result = await self._session.execute(
            select(BackfillJob)
            .where(BackfillJob.status.in_(("queued", "running", "analyzing")))
            .order_by(BackfillJob.id)
        )
        return list(result.scalars().all())

    async def list_pending_backfill(self) -> list[Channel]:
        result = await self._session.execute(
            select(Channel)
            .where(Channel.pending_backfill_days.is_not(None))
            .where(Channel.pending_backfill_days > 0)
            .order_by(Channel.id)
        )
        return list(result.scalars().all())

    async def list_user_channels(self, user_id: int) -> list[tuple[Channel, UserChannel]]:
        result = await self._session.execute(
            select(UserChannel, Channel)
            .join(Channel, Channel.id == UserChannel.channel_id)
            .where(UserChannel.user_id == user_id)
            .order_by(Channel.title)
        )
        rows = result.all()
        return [(channel, link) for link, channel in rows]

    async def list_enabled_channels(self) -> list[Channel]:
        """Channels to ingest: enabled flag OR at least one active subscriber."""
        active_ids = select(UserChannel.channel_id).where(UserChannel.is_active.is_(True)).distinct()
        result = await self._session.execute(
            select(Channel)
            .where((Channel.enabled.is_(True)) | (Channel.id.in_(active_ids)))
            .order_by(Channel.id)
        )
        return list(result.scalars().all())

    async def list_all_channels(self) -> list[Channel]:
        result = await self._session.execute(select(Channel).order_by(Channel.title))
        return list(result.scalars().all())

    async def set_channel_enabled(self, channel_id: int, enabled: bool) -> Channel | None:
        channel = await self._session.get(Channel, channel_id)
        if not channel:
            return None
        channel.enabled = enabled
        await self._session.commit()
        await self._session.refresh(channel)
        return channel

    async def set_user_channel_active(
        self, user_id: int, channel_id: int, is_active: bool
    ) -> UserChannel | None:
        result = await self._session.execute(
            select(UserChannel).where(
                UserChannel.user_id == user_id,
                UserChannel.channel_id == channel_id,
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            return None
        link.is_active = is_active
        if is_active:
            channel = await self._session.get(Channel, channel_id)
            if channel:
                channel.enabled = True
        await self._session.commit()
        return link

    async def toggle_user_channel(self, user_id: int, channel_id: int) -> UserChannel | None:
        result = await self._session.execute(
            select(UserChannel).where(
                UserChannel.user_id == user_id,
                UserChannel.channel_id == channel_id,
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            return None
        return await self.set_user_channel_active(user_id, channel_id, not link.is_active)

    async def _active_subscriber_count(self, channel_id: int) -> int:
        n = await self._session.scalar(
            select(func.count())
            .select_from(UserChannel)
            .where(UserChannel.channel_id == channel_id)
        )
        return int(n or 0)

    async def remove_user_channel(self, user_id: int, channel_id: int) -> bool:
        result = await self._session.execute(
            select(UserChannel).where(
                UserChannel.user_id == user_id,
                UserChannel.channel_id == channel_id,
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            return False
        await self._session.delete(link)
        await self._session.flush()
        remaining = await self._active_subscriber_count(channel_id)
        if remaining == 0:
            channel = await self._session.get(Channel, channel_id)
            if channel:
                channel.enabled = False
        await self._session.commit()
        return True

    async def delete_channel(self, channel_id: int) -> bool:
        channel = await self._session.get(Channel, channel_id)
        if not channel:
            return False
        await self._session.delete(channel)
        await self._session.commit()
        return True

    async def get_channel(self, channel_id: int) -> Channel | None:
        return await self._session.get(
            Channel,
            channel_id,
            options=(selectinload(Channel.user_links),),
        )
