"""Timezone + Do-Not-Disturb helpers for digests and trends."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import UserSettings

POPULAR_TIMEZONES = (
    "Europe/Moscow",
    "Europe/Kaliningrad",
    "Europe/Samara",
    "Asia/Yekaterinburg",
    "Asia/Novosibirsk",
    "Asia/Krasnoyarsk",
    "Asia/Irkutsk",
    "Asia/Vladivostok",
    "Europe/Berlin",
    "Europe/London",
    "America/New_York",
    "UTC",
)


def parse_hhmm(value: str, fallback: str = "00:00") -> time:
    raw = (value or fallback).strip()
    try:
        hh, mm = raw.split(":")
        return time(hour=int(hh), minute=int(mm))
    except Exception:
        fh, fm = fallback.split(":")
        return time(hour=int(fh), minute=int(fm))


def zone_for(settings: UserSettings | None) -> ZoneInfo:
    name = (settings.timezone if settings else None) or "Europe/Moscow"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def now_local(settings: UserSettings | None) -> datetime:
    return datetime.now(timezone.utc).astimezone(zone_for(settings))


def is_weekend(local_dt: datetime) -> bool:
    return local_dt.weekday() >= 5


def _in_dnd_window(local_dt: datetime, start: time, end: time) -> bool:
    t = local_dt.time().replace(second=0, microsecond=0)
    if start <= end:
        return start <= t < end
    # Overnight window (e.g. 23:00–08:00)
    return t >= start or t < end


def is_dnd_active(settings: UserSettings) -> bool:
    if not getattr(settings, "dnd_enabled", True):
        return False
    local = now_local(settings)
    if is_weekend(local):
        start = parse_hhmm(settings.dnd_weekend_start, "00:00")
        end = parse_hhmm(settings.dnd_weekend_end, "10:00")
    else:
        start = parse_hhmm(settings.dnd_weekday_start, "23:00")
        end = parse_hhmm(settings.dnd_weekday_end, "08:00")
    return _in_dnd_window(local, start, end)


def dnd_end_local(settings: UserSettings) -> datetime:
    """Next local datetime when DND ends."""
    local = now_local(settings)
    if is_weekend(local):
        end = parse_hhmm(settings.dnd_weekend_end, "10:00")
    else:
        end = parse_hhmm(settings.dnd_weekday_end, "08:00")
    candidate = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def trends_window_start(settings: UserSettings | None) -> datetime:
    """
    Before 08:00 local: last 24h.
    From 08:00: since local midnight.
    Returned as UTC-aware datetime.
    """
    local = now_local(settings)
    if local.hour < 8:
        start_local = local - timedelta(hours=24)
    else:
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc)


def digest_interval_hours(mode: str) -> int | None:
    return {"1h": 1, "3h": 3, "6h": 6}.get(mode)


def is_digest_due(settings: UserSettings, *, now_utc: datetime | None = None) -> bool:
    mode = (settings.digest_mode or "off").strip()
    if mode == "off" or not settings.notifications_enabled:
        return False
    if getattr(settings, "is_banned", False):
        return False
    if is_dnd_active(settings):
        return False

    now_utc = now_utc or datetime.now(timezone.utc)
    last = settings.last_digest_sent_at
    local = now_utc.astimezone(zone_for(settings))

    hours = digest_interval_hours(mode)
    if hours is not None:
        if last is None:
            return True
        # After DND: first send at dnd_end + interval (approx: if last before DND end, wait)
        if (now_utc - last) >= timedelta(hours=hours):
            return True
        return False

    if mode == "daily":
        target = parse_hhmm(settings.digest_time, "09:00")
        if local.time() < target:
            return False
        if last is None:
            return True
        last_local = last.astimezone(zone_for(settings))
        return last_local.date() < local.date()

    return False
