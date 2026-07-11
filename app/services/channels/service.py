"""Channel management shared by bot, admin API, and worker."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Channel, User, UserChannel


class ChannelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_user(self, telegram_id: int, username: str | None = None) -> User:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            if username and user.username != username:
                user.username = username
            return user
        user = User(telegram_id=telegram_id, username=username)
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
    ) -> Channel:
        channel = await self.upsert_channel(
            telegram_id=telegram_id,
            title=title,
            username=username,
            enabled=True,
        )
        await self.link_user_channel(user, channel, is_active=True)
        await self._session.commit()
        await self._session.refresh(channel)
        return channel

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
        result = await self._session.execute(
            select(Channel).where(Channel.enabled.is_(True)).order_by(Channel.id)
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
        await self._session.commit()
        return link

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
