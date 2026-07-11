from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.models import User

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    await message.answer(
        f"Привет{', @' + db_user.username if db_user.username else ''}!\n\n"
        "Я AI-ассистент по новостям из твоих Telegram-каналов:\n"
        "фильтрую мусор, объединяю дубли, пишу краткие сводки.\n\n"
        "Команды:\n"
        "/digest — топ новостей\n"
        "/daily — сводка за 24 часа\n"
        "/search — смысловой AI-поиск\n"
        "/channels — управление каналами"
    )
