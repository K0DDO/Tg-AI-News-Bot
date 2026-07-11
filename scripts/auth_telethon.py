"""Interactive login helper for Telethon user session."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.parser import create_telegram_client


async def main() -> None:
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
    client = create_telegram_client()
    await client.start()
    me = await client.get_me()
    print(f"Authorized as {me.username or me.id}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
