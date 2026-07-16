"""User settings and personalized Event feed / favorites / history."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.models import Channel, Event, EventSource, Message, User, UserChannel, UserEventState, UserSettings
from app.services.categories import (
    DEFAULT_CATEGORIES,
    THEME_OTHER,
    default_theme_weights,
    migrate_enabled_list,
    normalize_category,
)

LIKE_SCORE_DELTA = Decimal("1.5")
DISLIKE_SCORE_DELTA = Decimal("-2.0")


class PreferencesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user: User) -> UserSettings:
        result = await self._session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()
        if settings:
            self._ensure_categories(settings)
            self._ensure_theme_weights(settings)
            return settings
        settings = UserSettings(
            user_id=user.id,
            enabled_categories=DEFAULT_CATEGORIES.copy(),
            theme_weights=default_theme_weights(),
            language="ru",
            news_language="ru",
            timezone="Europe/Moscow",
            digest_mode="1h",
        )
        self._session.add(settings)
        await self._session.flush()
        return settings

    @staticmethod
    def _ensure_categories(settings: UserSettings) -> None:
        """Normalize theme keys; never re-enable user-disabled themes."""
        current = list(settings.enabled_categories or [])
        if not current:
            settings.enabled_categories = DEFAULT_CATEGORIES.copy()
            return
        mapped = migrate_enabled_list(current)
        if mapped != current:
            settings.enabled_categories = mapped
            try:
                flag_modified(settings, "enabled_categories")
            except Exception:
                pass

    @staticmethod
    def _ensure_theme_weights(settings: UserSettings) -> None:
        weights = dict(settings.theme_weights or {})
        changed = False
        for key in DEFAULT_CATEGORIES:
            if key not in weights:
                weights[key] = 3
                changed = True
        # Drop unknowns
        cleaned = {k: max(1, min(5, int(v))) for k, v in weights.items() if k in DEFAULT_CATEGORIES}
        if cleaned != settings.theme_weights or changed:
            settings.theme_weights = cleaned
            try:
                flag_modified(settings, "theme_weights")
            except Exception:
                pass

    async def lang(self, user: User) -> str:
        s = await self.get_or_create(user)
        return s.language or "ru"

    async def news_lang(self, user: User) -> str:
        s = await self.get_or_create(user)
        return s.news_language or s.language or "ru"

    async def soft_reset_user(self, user: User) -> dict[str, int]:
        """
        Make the user look 'new' for onboarding/testing:
        - reset settings flags (welcome/tutorial/language_chosen)
        - clear read/history/favorites (UserEventState) and reactions
        - KEEP UserChannel links (sources stay visible)
        - KEEP User row (still counted in stats)
        """
        from app.models import Reaction
        from app.services.user_activity import log_user_action

        settings = await self.get_or_create(user)
        settings.welcome_seen = False
        settings.tutorial_seen = False
        settings.language_chosen = False
        settings.language = "ru"
        settings.news_language = "ru"
        settings.digest_chat_id = None
        settings.digest_message_id = None
        settings.digest_feed_ids = None
        settings.last_digest_sent_at = None
        settings.ui_chat_id = None
        settings.ui_message_id = None

        st = await self._session.execute(
            delete(UserEventState).where(UserEventState.user_id == user.id)
        )
        rx = await self._session.execute(delete(Reaction).where(Reaction.user_id == user.id))
        await log_user_action(
            self._session,
            user=user,
            action="account_wipe_data",
            detail="soft reset: history/reactions cleared, channels kept",
        )
        await self._session.commit()
        return {
            "states": int(st.rowcount or 0),
            "reactions": int(rx.rowcount or 0),
            "channels": 0,
            "purged_channels": 0,
            "user_deleted": 0,
        }

    async def full_reset_user(
        self,
        user: User,
        *,
        purge_orphan_channels: bool = False,
        delete_user_row: bool = False,
    ) -> dict[str, int]:
        """
        Full first-run wipe:
        - reset settings + clear states/reactions
        - unlink UserChannel
        - optionally delete Channel rows unused by anyone else
        - optionally hard-delete User (drops from admin user count; /start recreates)
        """
        from app.models import Reaction
        from app.services.user_activity import log_user_action

        telegram_id = user.telegram_id
        user_id = user.id

        settings = await self.get_or_create(user)
        settings.welcome_seen = False
        settings.tutorial_seen = False
        settings.language_chosen = False
        settings.language = "ru"
        settings.news_language = "ru"
        settings.enabled_categories = DEFAULT_CATEGORIES.copy()
        settings.theme_weights = default_theme_weights()
        settings.digest_mode = "1h"
        settings.update_interval_minutes = 60
        settings.notifications_enabled = True
        settings.digest_chat_id = None
        settings.digest_message_id = None
        settings.digest_feed_ids = None
        settings.last_digest_sent_at = None
        settings.ui_chat_id = None
        settings.ui_message_id = None
        settings.ignored_topics = ""
        try:
            flag_modified(settings, "enabled_categories")
            flag_modified(settings, "theme_weights")
        except Exception:
            pass

        own_channel_ids = list(
            (
                await self._session.execute(
                    select(UserChannel.channel_id).where(UserChannel.user_id == user.id)
                )
            ).scalars().all()
        )

        st = await self._session.execute(
            delete(UserEventState).where(UserEventState.user_id == user.id)
        )
        rx = await self._session.execute(delete(Reaction).where(Reaction.user_id == user.id))
        ch = await self._session.execute(delete(UserChannel).where(UserChannel.user_id == user.id))
        await self._session.flush()

        purged = 0
        if purge_orphan_channels:
            if own_channel_ids:
                purged = await self._purge_orphan_channels(list(own_channel_ids))
            # Also sweep any leftover orphans (e.g. from older wipes / unsubscribes)
            purged += await self.purge_all_orphan_channels()

        action = "account_wipe_purge" if purge_orphan_channels else "account_wipe_full"
        await log_user_action(
            self._session,
            user=user,
            action=action,
            detail=(
                f"channels_unlinked={int(ch.rowcount or 0)} "
                f"purged_channels={purged} delete_user={int(delete_user_row)}"
            ),
        )

        user_deleted = 0
        if delete_user_row:
            # Re-fetch in case identity map is stale
            row = await self._session.get(User, user_id)
            if row is not None:
                await self._session.delete(row)
                user_deleted = 1
                await self._session.flush()
                if purge_orphan_channels:
                    purged += await self.purge_all_orphan_channels()

        await self._session.commit()
        return {
            "states": int(st.rowcount or 0),
            "reactions": int(rx.rowcount or 0),
            "channels": int(ch.rowcount or 0),
            "purged_channels": purged,
            "user_deleted": user_deleted,
            "telegram_id": telegram_id,
        }

    async def _purge_orphan_channels(self, channel_ids: list[int]) -> int:
        """Delete given channels that have zero remaining UserChannel links."""
        if not channel_ids:
            return 0
        await self._session.flush()
        still_linked = set(
            (
                await self._session.execute(
                    select(UserChannel.channel_id)
                    .where(UserChannel.channel_id.in_(channel_ids))
                    .distinct()
                )
            ).scalars().all()
        )
        orphan_ids = [cid for cid in channel_ids if cid not in still_linked]
        if not orphan_ids:
            return 0
        result = await self._session.execute(
            delete(Channel)
            .where(Channel.id.in_(orphan_ids))
            .execution_options(synchronize_session=False)
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def purge_all_orphan_channels(self) -> int:
        """Delete every channel with zero UserChannel links."""
        await self._session.flush()
        orphan_ids = list(
            (
                await self._session.execute(
                    select(Channel.id).where(
                        ~select(UserChannel.id)
                        .where(UserChannel.channel_id == Channel.id)
                        .exists()
                    )
                )
            ).scalars().all()
        )
        if not orphan_ids:
            return 0
        result = await self._session.execute(
            delete(Channel)
            .where(Channel.id.in_(orphan_ids))
            .execution_options(synchronize_session=False)
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def mark_welcome_seen(self, user: User) -> None:
        settings = await self.get_or_create(user)
        settings.welcome_seen = True
        await self._session.commit()

    async def mark_tutorial_seen(self, user: User) -> None:
        settings = await self.get_or_create(user)
        settings.tutorial_seen = True
        await self._session.commit()

    async def set_language(self, user: User, language: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.language = language
        settings.language_chosen = True
        await self._session.commit()
        return settings

    async def set_news_language(self, user: User, language: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.news_language = language
        await self._session.commit()
        return settings

    async def save_digest_message(
        self,
        user: User,
        chat_id: int,
        message_id: int,
        *,
        event_ids: list[int] | None = None,
    ) -> None:
        settings = await self.get_or_create(user)
        settings.digest_chat_id = chat_id
        settings.digest_message_id = message_id
        if event_ids is not None:
            settings.digest_feed_ids = [int(x) for x in event_ids]
        # Feed is the active screen — keep UI pointer in sync so menu nav deletes it
        settings.ui_chat_id = chat_id
        settings.ui_message_id = message_id
        await self._session.commit()

    async def clear_digest_message(self, user: User) -> None:
        settings = await self.get_or_create(user)
        # If UI pointer points at digest message, clear both
        if (
            settings.ui_message_id
            and settings.digest_message_id
            and settings.ui_message_id == settings.digest_message_id
        ):
            settings.ui_chat_id = None
            settings.ui_message_id = None
        settings.digest_chat_id = None
        settings.digest_message_id = None
        settings.digest_feed_ids = None
        await self._session.commit()

    async def save_ui_message(self, user: User, chat_id: int, message_id: int) -> None:
        settings = await self.get_or_create(user)
        settings.ui_chat_id = chat_id
        settings.ui_message_id = message_id
        await self._session.commit()

    async def get_ui_message(self, user: User) -> tuple[int | None, int | None]:
        settings = await self.get_or_create(user)
        return settings.ui_chat_id, settings.ui_message_id

    async def clear_ui_message(self, user: User) -> None:
        settings = await self.get_or_create(user)
        # Navigating away from feed — drop digest pointer if it was the same message
        if (
            settings.ui_message_id
            and settings.digest_message_id
            and settings.ui_message_id == settings.digest_message_id
        ):
            settings.digest_chat_id = None
            settings.digest_message_id = None
            settings.digest_feed_ids = None
        settings.ui_chat_id = None
        settings.ui_message_id = None
        await self._session.commit()

    async def digest_feed_still_unread(self, user: User) -> bool:
        """True if previous pushed feed still has unread items (user hasn't finished it)."""
        settings = await self.get_or_create(user)
        ids = [int(x) for x in (settings.digest_feed_ids or []) if x]
        if not ids:
            return bool(settings.digest_message_id)
        result = await self._session.execute(
            select(UserEventState).where(
                UserEventState.user_id == user.id,
                UserEventState.event_id.in_(ids),
                UserEventState.is_read.is_(True),
            )
        )
        read_ids = {s.event_id for s in result.scalars().all()}
        return any(eid not in read_ids for eid in ids)

    async def set_interval(self, user: User, minutes: int) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.update_interval_minutes = minutes
        # Keep digest_mode in sync for legacy callers
        if minutes <= 0:
            settings.digest_mode = "off"
        elif minutes <= 60:
            settings.digest_mode = "1h"
        elif minutes <= 180:
            settings.digest_mode = "3h"
        elif minutes <= 360:
            settings.digest_mode = "6h"
        else:
            settings.digest_mode = "daily"
        await self._session.commit()
        return settings

    async def set_digest_mode(self, user: User, mode: str) -> UserSettings:
        settings = await self.get_or_create(user)
        if mode not in {"off", "1h", "3h", "6h", "daily"}:
            return settings
        settings.digest_mode = mode
        settings.notifications_enabled = mode != "off"
        settings.update_interval_minutes = {"off": 0, "1h": 60, "3h": 180, "6h": 360, "daily": 1440}[mode]
        await self._session.commit()
        return settings

    async def set_digest_time(self, user: User, hhmm: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.digest_time = hhmm.strip()[:5]
        await self._session.commit()
        return settings

    async def set_timezone(self, user: User, tz: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.timezone = tz.strip()[:64] or "Europe/Moscow"
        await self._session.commit()
        return settings

    async def set_dnd(
        self,
        user: User,
        *,
        enabled: bool | None = None,
        weekday_start: str | None = None,
        weekday_end: str | None = None,
        weekend_start: str | None = None,
        weekend_end: str | None = None,
    ) -> UserSettings:
        settings = await self.get_or_create(user)
        if enabled is not None:
            settings.dnd_enabled = enabled
        if weekday_start:
            settings.dnd_weekday_start = weekday_start
        if weekday_end:
            settings.dnd_weekday_end = weekday_end
        if weekend_start:
            settings.dnd_weekend_start = weekend_start
        if weekend_end:
            settings.dnd_weekend_end = weekend_end
        await self._session.commit()
        return settings

    async def set_theme_weight(self, user: User, theme: str, stars: int) -> UserSettings:
        settings = await self.get_or_create(user)
        theme = normalize_category(theme)
        if theme not in DEFAULT_CATEGORIES:
            return settings
        weights = dict(settings.theme_weights or default_theme_weights())
        weights[theme] = max(1, min(5, int(stars)))
        settings.theme_weights = weights
        flag_modified(settings, "theme_weights")
        await self._session.commit()
        await self._session.refresh(settings)
        return settings

    async def set_min_importance(self, user: User, value: float) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.min_importance = max(0.0, min(10.0, value))
        await self._session.commit()
        return settings

    async def set_feed_page_size(self, user: User, size: int) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.feed_page_size = max(1, min(15, size))
        await self._session.commit()
        return settings

    async def toggle_bool(self, user: User, field: str) -> UserSettings:
        settings = await self.get_or_create(user)
        if not hasattr(settings, field):
            return settings
        setattr(settings, field, not bool(getattr(settings, field)))
        await self._session.commit()
        return settings

    async def toggle_category(self, user: User, category: str) -> UserSettings:
        settings = await self.get_or_create(user)
        if category not in DEFAULT_CATEGORIES:
            return settings
        cats = list(settings.enabled_categories or [])
        if category in cats:
            cats.remove(category)
        else:
            cats.append(category)
        settings.enabled_categories = cats
        flag_modified(settings, "enabled_categories")
        await self._session.commit()
        await self._session.refresh(settings)
        return settings

    async def set_ignored_topics(self, user: User, text: str) -> UserSettings:
        settings = await self.get_or_create(user)
        settings.ignored_topics = (text or "").strip()
        await self._session.commit()
        return settings

    async def reset_reactions(self, user: User) -> None:
        await self._session.execute(delete(UserEventState).where(UserEventState.user_id == user.id))
        from app.models import Reaction

        await self._session.execute(delete(Reaction).where(Reaction.user_id == user.id))
        await self._session.commit()

    async def user_stats(self, user: User) -> dict[str, int]:
        read_n = await self._session.scalar(
            select(func.count())
            .select_from(UserEventState)
            .where(UserEventState.user_id == user.id, UserEventState.is_read.is_(True))
        )
        fav_n = await self._session.scalar(
            select(func.count())
            .select_from(UserEventState)
            .where(UserEventState.user_id == user.id, UserEventState.is_favorite.is_(True))
        )
        liked_n = await self._session.scalar(
            select(func.count())
            .select_from(UserEventState)
            .where(UserEventState.user_id == user.id, UserEventState.is_liked.is_(True))
        )
        return {
            "read": int(read_n or 0),
            "saved": int(fav_n or 0),
            "liked": int(liked_n or 0),
        }


class FeedService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._prefs = PreferencesService(session)

    async def get_feed(
        self,
        user: User,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Event], int]:
        """Fast personal feed: SQL filters + theme weights + unread prune."""
        settings = await self._prefs.get_or_create(user)
        page_size = limit if limit is not None else int(settings.feed_page_size or 5)
        cats = list(settings.enabled_categories or DEFAULT_CATEGORIES)
        weights = dict(settings.theme_weights or default_theme_weights())
        ignored = [t.strip().lower() for t in (settings.ignored_topics or "").split(",") if t.strip()]

        channel_ids = await self._user_channel_ids(user.id)
        if not channel_ids:
            return [], 0

        await self.prune_unread_queue(user)

        via_msg = (
            select(EventSource.event_id)
            .join(Message, Message.id == EventSource.message_id)
            .where(Message.channel_id.in_(channel_ids))
            .where(Message.is_advertisement.is_(False))
        )
        via_user = (
            select(EventSource.event_id)
            .join(
                Channel,
                func.lower(Channel.username) == func.lower(EventSource.channel_username),
            )
            .where(EventSource.message_id.is_(None))
            .where(Channel.id.in_(channel_ids))
            .where(Channel.username.is_not(None))
        )
        allowed = via_msg.union(via_user)

        blocked = (
            select(UserEventState.event_id)
            .where(UserEventState.user_id == user.id)
            .where(
                or_(
                    UserEventState.is_read.is_(True),
                    UserEventState.is_hidden.is_(True),
                    UserEventState.is_disliked.is_(True),
                )
            )
        )
        personal = func.coalesce(UserEventState.personal_score, 0)

        stmt = (
            select(Event, personal.label("personal"))
            .outerjoin(
                UserEventState,
                and_(
                    UserEventState.event_id == Event.id,
                    UserEventState.user_id == user.id,
                ),
            )
            .options(defer(Event.embedding))
            .where(Event.status == "active")
            .where(Event.importance_score >= settings.min_importance)
            .where(Event.id.in_(allowed))
            .where(Event.id.not_in(blocked))
        )
        if not cats:
            return [], 0
        stmt = stmt.where(
            func.coalesce(Event.category, THEME_OTHER).in_(cats)
        )
        for topic in ignored:
            pat = f"%{topic}%"
            stmt = stmt.where(
                ~func.lower(func.coalesce(Event.title, "")).like(pat),
                ~func.lower(func.coalesce(Event.summary, "")).like(pat),
                ~func.lower(func.coalesce(Event.topic, "")).like(pat),
            )

        # Fetch a window, then re-rank with theme weights in Python.
        fetch_n = max(page_size * 4, 40) + offset
        stmt = stmt.order_by(
            (personal + Event.importance_score).desc(),
            Event.importance_score.desc(),
            Event.updated_at.desc(),
        ).limit(fetch_n)
        raw_rows = list((await self._session.execute(stmt)).unique().all())

        def score_row(ev: Event, pers) -> float:
            w = float(weights.get(normalize_category(ev.category), 3))
            imp = float(ev.importance_score or 0)
            p = float(pers or 0)
            return p + imp * (0.6 + 0.4 * (w / 5.0))

        ranked = sorted(raw_rows, key=lambda r: score_row(r[0], r[1]), reverse=True)
        events = self._collapse_near_duplicates([r[0] for r in ranked])
        page = events[offset : offset + page_size]
        has_more = len(events) > offset + page_size
        total = offset + len(page) + (1 if has_more else 0)
        return page, total

    @staticmethod
    def _collapse_near_duplicates(events: list[Event]) -> list[Event]:
        """Keep highest-ranked event when several cover the same story."""
        from app.services.events.merge import is_near_duplicate

        kept: list[Event] = []
        for ev in events:
            blob = f"{ev.title or ''}\n{ev.summary or ''}"
            dup = False
            for prev in kept:
                prev_blob = f"{prev.title or ''}\n{prev.summary or ''}"
                if is_near_duplicate(blob, prev_blob):
                    # Prefer more sources when collapsing
                    if int(ev.sources_count or 0) > int(prev.sources_count or 0):
                        kept[kept.index(prev)] = ev
                    dup = True
                    break
            if not dup:
                kept.append(ev)
        return kept

    async def prune_unread_queue(self, user: User) -> int:
        """Keep at most unread_queue_max unread items; hide weakest without marking read."""
        from app.config import get_settings

        max_n = int(get_settings().unread_queue_max or 50)
        settings = await self._prefs.get_or_create(user)
        cats = list(settings.enabled_categories or DEFAULT_CATEGORIES)
        channel_ids = await self._user_channel_ids(user.id)
        if not channel_ids or not cats:
            return 0

        allowed = await self._event_ids_for_channels(channel_ids)
        if not allowed:
            return 0
        blocked = (
            await self._session.execute(
                select(UserEventState.event_id).where(
                    UserEventState.user_id == user.id,
                    or_(
                        UserEventState.is_read.is_(True),
                        UserEventState.is_hidden.is_(True),
                        UserEventState.is_disliked.is_(True),
                    ),
                )
            )
        ).scalars().all()
        blocked_set = set(blocked)
        result = await self._session.execute(
            select(Event)
            .options(defer(Event.embedding))
            .where(Event.status == "active")
            .where(Event.id.in_(list(allowed)))
            .where(Event.importance_score >= settings.min_importance)
            .where(func.coalesce(Event.category, THEME_OTHER).in_(cats))
            .order_by(Event.importance_score.asc(), Event.updated_at.asc())
            .limit(max_n + 80)
        )
        candidates = [e for e in result.scalars().all() if e.id not in blocked_set]
        if len(candidates) <= max_n:
            return 0
        # Weakest first already ordered ascending — hide overflow
        to_hide = candidates[: len(candidates) - max_n]
        n = 0
        for ev in to_hide:
            st = await self._get_or_create_state(user, ev)
            if not st.is_read and not st.is_favorite:
                st.is_hidden = True
                n += 1
        if n:
            await self._session.commit()
        return n

    async def event_ids_for_user(self, user: User) -> set[int]:
        channel_ids = await self._user_channel_ids(user.id)
        return await self._event_ids_for_channels(channel_ids)

    async def _user_channel_ids(self, user_id: int) -> list[int]:
        result = await self._session.execute(
            select(UserChannel.channel_id).where(
                UserChannel.user_id == user_id,
                UserChannel.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def _event_ids_for_channels(self, channel_ids: list[int]) -> set[int]:
        """Events that have at least one source message from the given channels."""
        if not channel_ids:
            return set()

        via_msg = await self._session.execute(
            select(EventSource.event_id)
            .join(Message, Message.id == EventSource.message_id)
            .where(Message.channel_id.in_(channel_ids))
            .where(Message.is_advertisement.is_(False))
        )
        ids = set(via_msg.scalars().all())

        # Fallback for sources without message_id: exact username match only
        ch_result = await self._session.execute(
            select(Channel).where(Channel.id.in_(channel_ids))
        )
        usernames = {(c.username or "").lower() for c in ch_result.scalars().all() if c.username}
        if usernames:
            via_user = await self._session.execute(
                select(EventSource.event_id).where(
                    EventSource.message_id.is_(None),
                    EventSource.channel_username.is_not(None),
                    func.lower(EventSource.channel_username).in_(list(usernames)),
                )
            )
            ids |= set(via_user.scalars().all())

        return ids

    @staticmethod
    def _should_show(state: UserEventState | None) -> bool:
        if state is None:
            return True
        if state.is_hidden or state.is_disliked:
            return False
        return not state.is_read

    async def _load_states(self, user_id: int) -> dict[int, UserEventState]:
        result = await self._session.execute(
            select(UserEventState).where(UserEventState.user_id == user_id)
        )
        return {s.event_id: s for s in result.scalars().all()}

    async def _get_or_create_state(self, user: User, event: Event) -> UserEventState:
        result = await self._session.execute(
            select(UserEventState).where(
                UserEventState.user_id == user.id,
                UserEventState.event_id == event.id,
            )
        )
        state = result.scalar_one_or_none()
        if state is None:
            state = UserEventState(user_id=user.id, event_id=event.id)
            self._session.add(state)
            await self._session.flush()
        return state

    async def mark_shown(self, user: User, event: Event) -> None:
        state = await self._get_or_create_state(user, event)
        state.is_shown = True
        state.shown_count = int(state.shown_count or 0) + 1
        await self._session.commit()

    async def mark_read(self, user: User, event: Event, *, hidden: bool = False) -> None:
        state = await self._get_or_create_state(user, event)
        now = datetime.now(timezone.utc)
        state.is_read = True
        state.is_shown = True
        state.read_at = now
        state.opened_at = state.opened_at or now
        state.shown_count = max(int(state.shown_count or 0), 1)
        if hidden:
            state.is_hidden = True
            state.is_disliked = True
            state.is_liked = False
            state.personal_score = Decimal(state.personal_score or 0) + DISLIKE_SCORE_DELTA
        state.score_at_interaction = event.importance_score
        state.sources_at_interaction = event.sources_count or len(event.sources or [])
        await self._session.commit()

    async def mark_read_many(self, user: User, event_ids: list[int]) -> int:
        """Mark a feed block as read (e.g. user pressed Дальше / Закончить)."""
        if not event_ids:
            return 0
        from app.services.digest import NewsService

        news_svc = NewsService(self._session)
        n = 0
        now = datetime.now(timezone.utc)
        for eid in event_ids:
            event = await news_svc.get_event(eid)
            if not event:
                continue
            state = await self._get_or_create_state(user, event)
            if state.is_read:
                continue
            state.is_read = True
            state.is_shown = True
            state.read_at = now
            state.opened_at = state.opened_at or now
            state.shown_count = max(int(state.shown_count or 0), 1)
            state.score_at_interaction = event.importance_score
            state.sources_at_interaction = event.sources_count or len(event.sources or [])
            n += 1
        if n:
            await self._session.commit()
        return n

    async def mark_liked(self, user: User, event: Event) -> None:
        state = await self._get_or_create_state(user, event)
        if not state.is_liked:
            state.personal_score = Decimal(state.personal_score or 0) + LIKE_SCORE_DELTA
        state.is_liked = True
        state.is_disliked = False
        state.is_hidden = False
        state.is_read = True
        state.read_at = state.read_at or datetime.now(timezone.utc)
        state.opened_at = state.opened_at or datetime.now(timezone.utc)
        await self._session.commit()

    async def dislike(self, user: User, event: Event) -> None:
        await self.mark_read(user, event, hidden=True)

    async def toggle_favorite(self, user: User, event: Event) -> bool:
        state = await self._get_or_create_state(user, event)
        state.is_favorite = not state.is_favorite
        state.favorited_at = datetime.now(timezone.utc) if state.is_favorite else None
        await self._session.commit()
        return state.is_favorite

    async def remove_from_history(self, user: User, event: Event) -> None:
        state = await self._get_or_create_state(user, event)
        state.is_read = False
        state.read_at = None
        state.opened_at = None
        await self._session.commit()

    async def list_favorites(self, user: User, *, limit: int = 20) -> list[Event]:
        result = await self._session.execute(
            select(Event)
            .join(UserEventState, UserEventState.event_id == Event.id)
            .options(selectinload(Event.sources))
            .where(UserEventState.user_id == user.id, UserEventState.is_favorite.is_(True))
            .order_by(UserEventState.favorited_at.desc().nulls_last())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_history(
        self,
        user: User,
        *,
        limit: int = 10,
        offset: int = 0,
        since: datetime | None = None,
        query: str | None = None,
    ) -> tuple[list[tuple[Event, UserEventState]], int]:
        """Return (page rows, total matching count). Only is_read items (= history)."""
        stmt = (
            select(Event, UserEventState)
            .join(UserEventState, UserEventState.event_id == Event.id)
            .options(selectinload(Event.sources), defer(Event.embedding))
            .where(UserEventState.user_id == user.id, UserEventState.is_read.is_(True))
        )
        if since is not None:
            stmt = stmt.where(UserEventState.read_at >= since)
        stmt = stmt.order_by(UserEventState.read_at.desc().nulls_last())
        result = await self._session.execute(stmt)
        rows = list(result.all())
        q = (query or "").strip().lower()
        if q:
            rows = [
                (n, st)
                for n, st in rows
                if q in (n.title or "").lower()
                or q in (n.summary or "").lower()
                or q in (n.topic or "").lower()
            ]
        total = len(rows)
        return rows[offset : offset + limit], total
