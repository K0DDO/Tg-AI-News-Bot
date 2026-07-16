"""Briefly brand banners — rare, key-screen only (never spam)."""

from __future__ import annotations

import random
from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

_ASSETS = Path(__file__).resolve().parent / "assets"
_BANNERS_DIR = _ASSETS / "banners"
BANNER_PATH = _ASSETS / "briefly_banner.png"
WELCOME_PATH = _ASSETS / "welcome.png"

# How often a photo is attached (text always sends).
# start/done = first impression; howto/empty = almost never.
_PHOTO_CHANCE = {
    "start": 1.0,   # /start welcome — always
    "done": 1.0,    # end of onboarding — always
    "howto": 0.12,  # «Как пользоваться» — редко
    "empty": 0.05,  # пустая лента — очень редко
}


def list_banners() -> list[Path]:
    paths: list[Path] = []
    if _BANNERS_DIR.is_dir():
        paths.extend(sorted(_BANNERS_DIR.glob("banner_*.png")))
    for fallback in (BANNER_PATH, WELCOME_PATH):
        if fallback.exists() and fallback not in paths:
            paths.append(fallback)
    # Prefer reasonably sized files (skip accidental junk)
    return [p for p in paths if 50_000 <= p.stat().st_size <= 500_000] or paths


def pick_banner(*, seed: str | None = None) -> Path | None:
    """Pick a random banner for variety (stable within a short seed if given)."""
    banners = list_banners()
    if not banners:
        return None
    if seed:
        rng = random.Random(seed)
        return rng.choice(banners)
    return random.choice(banners)


def banner_file(*, seed: str | None = None) -> FSInputFile | None:
    path = pick_banner(seed=seed)
    if path is None:
        return None
    return FSInputFile(path)


def _should_attach_photo(occasion: str) -> bool:
    chance = _PHOTO_CHANCE.get(occasion, 0.0)
    if chance >= 1.0:
        return True
    if chance <= 0.0:
        return False
    return random.random() < chance


async def send_banner(
    message: Message,
    caption: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    occasion: str = "start",
    force_photo: bool = False,
) -> Message:
    """
    Send caption; attach a brand photo only on rare key occasions.
    Rotates between banners when a photo is shown.
    """
    use_photo = force_photo or _should_attach_photo(occasion)
    photo = banner_file() if use_photo else None
    if photo is not None:
        return await message.answer_photo(
            photo,
            caption=caption,
            reply_markup=reply_markup,
        )
    return await message.answer(caption, reply_markup=reply_markup)
