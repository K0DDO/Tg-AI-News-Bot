"""Admin accounts: roles, passwords, ban helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import bcrypt
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AdminAccount, Channel, Event, Message, User, UserChannel, UserEventState, UserSettings
from app.models.knowledge import Edge, Node
from app.models.whitelist import WhitelistEntry


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


class AdminService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_owner_row(self, user: User) -> AdminAccount | None:
        """Bootstrap OWNER from ENV if matching telegram id."""
        settings = get_settings()
        owner_tid = settings.owner_telegram_id_resolved()
        if not owner_tid or user.telegram_id != owner_tid:
            return await self.get_account(user.id)

        result = await self._session.execute(
            select(AdminAccount).where(AdminAccount.user_id == user.id)
        )
        acc = result.scalar_one_or_none()
        if acc:
            if acc.role != "owner":
                acc.role = "owner"
            return acc
        # Demote any other owners when env owner claims seat
        others = (
            await self._session.execute(select(AdminAccount).where(AdminAccount.role == "owner"))
        ).scalars().all()
        for o in others:
            o.role = "admin"
        acc = AdminAccount(
            user_id=user.id,
            role="owner",
            must_set_password=True,
            password_hash=None,
        )
        self._session.add(acc)
        await self._session.flush()
        return acc

    async def get_account(self, user_id: int) -> AdminAccount | None:
        return (
            await self._session.execute(
                select(AdminAccount).where(AdminAccount.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def is_admin_user(self, user: User) -> bool:
        """True only if an AdminAccount row exists (ENV owner or appointed)."""
        await self.ensure_owner_row(user)
        acc = await self.get_account(user.id)
        return acc is not None

    async def is_owner(self, user: User) -> bool:
        await self.ensure_owner_row(user)
        acc = await self.get_account(user.id)
        return bool(acc and acc.role == "owner")

    async def set_password(self, user: User, password: str) -> AdminAccount:
        acc = await self.ensure_owner_row(user) or await self.get_account(user.id)
        if not acc:
            raise PermissionError("not an admin")
        acc.password_hash = hash_password(password)
        acc.must_set_password = False
        await self._session.commit()
        return acc

    async def reset_password(self, target_user_id: int) -> AdminAccount | None:
        acc = await self.get_account(target_user_id)
        if not acc:
            return None
        acc.password_hash = None
        acc.must_set_password = True
        await self._session.commit()
        return acc

    async def appoint_admin(self, *, target: User, by: User) -> AdminAccount:
        if not await self.is_owner(by):
            raise PermissionError("owner only")
        acc = await self.get_account(target.id)
        if acc:
            if acc.role == "owner":
                return acc
            acc.role = "admin"
            acc.must_set_password = True
            acc.password_hash = None
            acc.created_by_user_id = by.id
        else:
            acc = AdminAccount(
                user_id=target.id,
                role="admin",
                must_set_password=True,
                created_by_user_id=by.id,
            )
            self._session.add(acc)
        await self._session.commit()
        return acc

    async def remove_admin(self, *, target_user_id: int, by: User) -> bool:
        if not await self.is_owner(by):
            raise PermissionError("owner only")
        acc = await self.get_account(target_user_id)
        if not acc or acc.role == "owner":
            return False
        await self._session.delete(acc)
        await self._session.commit()
        return True

    async def soft_reset_user(self, user: User) -> dict[str, int]:
        """Delegate to PreferencesService — channels kept, onboarding reset."""
        from app.services.preferences import PreferencesService

        return await PreferencesService(self._session).soft_reset_user(user)

    async def full_reset_user(
        self,
        user: User,
        *,
        purge_orphan_channels: bool = True,
        delete_user_row: bool = True,
    ) -> dict[str, int]:
        """Admin wipe: unlink, purge unique channels, remove user from DB."""
        from app.services.preferences import PreferencesService

        return await PreferencesService(self._session).full_reset_user(
            user,
            purge_orphan_channels=purge_orphan_channels,
            delete_user_row=delete_user_row,
        )

    async def ban_user(self, target: User) -> None:
        target.is_banned = True
        target.banned_at = datetime.now(timezone.utc)
        await self._session.commit()

    async def unban_user(self, target: User) -> None:
        target.is_banned = False
        target.banned_at = None
        await self._session.commit()

    async def find_user(self, query: str) -> User | None:
        q = (query or "").strip().lstrip("@")
        if not q:
            return None
        if q.isdigit():
            return (
                await self._session.execute(
                    select(User).where(
                        or_(User.telegram_id == int(q), User.id == int(q))
                    )
                )
            ).scalar_one_or_none()
        return (
            await self._session.execute(
                select(User).where(func.lower(User.username) == q.lower())
            )
        ).scalar_one_or_none()

    async def list_users(self, *, limit: int = 20, offset: int = 0) -> list[User]:
        return list(
            (
                await self._session.execute(
                    select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
                )
            ).scalars().all()
        )

    async def list_admins(self) -> list[tuple[AdminAccount, User]]:
        rows = (
            await self._session.execute(
                select(AdminAccount, User)
                .join(User, User.id == AdminAccount.user_id)
                .order_by(AdminAccount.role.desc(), AdminAccount.id)
            )
        ).all()
        return [(a, u) for a, u in rows]

    async def user_card_stats(self, user: User) -> dict:
        from app.models import AiUsageLog, UserActionLog

        ch_n = await self._session.scalar(
            select(func.count())
            .select_from(UserChannel)
            .where(UserChannel.user_id == user.id, UserChannel.is_active.is_(True))
        )
        read_n = await self._session.scalar(
            select(func.count())
            .select_from(UserEventState)
            .where(UserEventState.user_id == user.id, UserEventState.is_read.is_(True))
        )
        ai_n = await self._session.scalar(
            select(func.count())
            .select_from(AiUsageLog)
            .where(AiUsageLog.user_id == user.id)
        ) or 0
        tokens_in = await self._session.scalar(
            select(func.coalesce(func.sum(AiUsageLog.tokens_in), 0)).where(
                AiUsageLog.user_id == user.id
            )
        ) or 0
        tokens_out = await self._session.scalar(
            select(func.coalesce(func.sum(AiUsageLog.tokens_out), 0)).where(
                AiUsageLog.user_id == user.id
            )
        ) or 0
        ai_by_op = list(
            (
                await self._session.execute(
                    select(AiUsageLog.operation, func.count())
                    .where(AiUsageLog.user_id == user.id)
                    .group_by(AiUsageLog.operation)
                    .order_by(func.count().desc())
                    .limit(8)
                )
            ).all()
        )
        # Prefer user_id; also match telegram_id for actions after hard-delete recreate
        actions = list(
            (
                await self._session.execute(
                    select(UserActionLog)
                    .where(
                        or_(
                            UserActionLog.user_id == user.id,
                            UserActionLog.telegram_id == user.telegram_id,
                        )
                    )
                    .order_by(UserActionLog.created_at.desc())
                    .limit(12)
                )
            ).scalars().all()
        )
        return {
            "channels": int(ch_n or 0),
            "read": int(read_n or 0),
            "banned": bool(user.is_banned),
            "created_at": user.created_at,
            "last_seen_at": user.last_seen_at,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "ai_requests": int(ai_n),
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "ai_by_operation": [(str(op), int(n)) for op, n in ai_by_op],
            "actions": [
                {
                    "action": a.action,
                    "detail": a.detail,
                    "ts": a.created_at,
                }
                for a in actions
            ],
            "channel_list": await self.list_user_channels(user),
        }

    async def list_user_channels(self, user: User) -> list[dict]:
        rows = (
            await self._session.execute(
                select(Channel, UserChannel)
                .join(UserChannel, UserChannel.channel_id == Channel.id)
                .where(UserChannel.user_id == user.id)
                .order_by(UserChannel.is_active.desc(), Channel.title)
            )
        ).all()
        out: list[dict] = []
        for ch, link in rows:
            out.append(
                {
                    "id": ch.id,
                    "title": ch.title,
                    "username": ch.username,
                    "active": bool(link.is_active),
                }
            )
        return out

    async def purge_orphan_channels(self) -> int:
        from app.services.preferences import PreferencesService

        n = await PreferencesService(self._session).purge_all_orphan_channels()
        await self._session.commit()
        return n

    async def admin_statistics(self) -> dict:
        from datetime import timedelta

        from app.models import AiUsageLog
        from app.services.whitelist import WhitelistService

        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(days=1)
        users_total = await self._session.scalar(select(func.count()).select_from(User)) or 0
        users_active = (
            await self._session.scalar(
                select(func.count()).select_from(User).where(User.last_seen_at >= day_ago)
            )
            or 0
        )
        posts = await self._session.scalar(select(func.count()).select_from(Message)) or 0
        events = (
            await self._session.scalar(
                select(func.count()).select_from(Event).where(Event.status == "active")
            )
            or 0
        )
        nodes = await self._session.scalar(select(func.count()).select_from(Node)) or 0
        edges = await self._session.scalar(select(func.count()).select_from(Edge)) or 0
        channels = await self._session.scalar(select(func.count()).select_from(Channel)) or 0
        channels_linked = (
            await self._session.scalar(
                select(func.count(func.distinct(UserChannel.channel_id))).select_from(UserChannel)
            )
            or 0
        )
        channels_orphan = max(0, int(channels) - int(channels_linked))

        # Per-user channel counts (top)
        per_user = list(
            (
                await self._session.execute(
                    select(
                        User.id,
                        User.telegram_id,
                        User.username,
                        func.count(UserChannel.id).label("n"),
                    )
                    .outerjoin(UserChannel, UserChannel.user_id == User.id)
                    .group_by(User.id)
                    .order_by(func.count(UserChannel.id).desc())
                    .limit(15)
                )
            ).all()
        )

        ai_n = await self._session.scalar(select(func.count()).select_from(AiUsageLog)) or 0
        tokens_in = await self._session.scalar(
            select(func.coalesce(func.sum(AiUsageLog.tokens_in), 0))
        ) or 0
        tokens_out = await self._session.scalar(
            select(func.coalesce(func.sum(AiUsageLog.tokens_out), 0))
        ) or 0

        wl = WhitelistService(self._session)
        wl_on = await wl.is_whitelist_enabled()
        wl_n = await self._session.scalar(select(func.count()).select_from(WhitelistEntry)) or 0

        return {
            "users_total": int(users_total),
            "users_active_today": int(users_active),
            "posts": int(posts),
            "events": int(events),
            "nodes": int(nodes),
            "edges": int(edges),
            "channels": int(channels),
            "channels_linked": int(channels_linked),
            "channels_orphan": int(channels_orphan),
            "channels_by_user": [
                {
                    "user_id": int(uid),
                    "telegram_id": int(tid),
                    "username": uname,
                    "count": int(n or 0),
                }
                for uid, tid, uname, n in per_user
            ],
            "ai_requests": int(ai_n),
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "tokens_total": int(tokens_in) + int(tokens_out),
            "whitelist_enabled": wl_on,
            "whitelist_count": int(wl_n),
        }

    async def clear_user_unread(self, user_id: int) -> int:
        """Hide unread items for one user (not history)."""
        result = await self._session.execute(
            select(UserEventState).where(
                UserEventState.user_id == user_id,
                UserEventState.is_read.is_(False),
            )
        )
        n = 0
        for st in result.scalars().all():
            st.is_hidden = True
            n += 1
        await self._session.commit()
        return n

    async def clear_all_unread(self) -> int:
        result = await self._session.execute(
            select(UserEventState).where(UserEventState.is_read.is_(False))
        )
        n = 0
        for st in result.scalars().all():
            st.is_hidden = True
            n += 1
        await self._session.commit()
        return n
