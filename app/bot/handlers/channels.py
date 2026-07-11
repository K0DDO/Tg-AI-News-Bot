from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import channels_keyboard
from app.bot.states import ChannelAddStates
from app.models import User
from app.services.channels import ChannelService

router = Router(name="channels")


async def _render_channels(message: Message, session: AsyncSession, user: User) -> None:
    service = ChannelService(session)
    pairs = await service.list_user_channels(user.id)
    if not pairs:
        await message.answer(
            "Каналов пока нет. Нажми «Добавить канал» или пришли @username.",
            reply_markup=channels_keyboard([]),
        )
        return
    items = [
        (ch.id, ch.title, ch.enabled, link.is_active)
        for ch, link in pairs
    ]
    await message.answer(
        "Твои каналы:\n"
        "• «Вкл/Выкл парсинг» — глобальный флаг канала\n"
        "• «Удалить у меня» — убрать из твоего списка",
        reply_markup=channels_keyboard(items),
    )


@router.message(Command("channels"))
async def cmd_channels(message: Message, session: AsyncSession, db_user: User) -> None:
    await _render_channels(message, session, db_user)


@router.callback_query(F.data == "ch:add")
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChannelAddStates.waiting_username)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Пришли username канала (например @techcrunch или techcrunch)."
        )


@router.message(ChannelAddStates.waiting_username)
async def add_channel_username(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    raw = (message.text or "").strip()
    await state.clear()
    if not raw:
        await message.answer("Нужен username канала.")
        return

    username = raw.lstrip("@").split("/")[-1]
    bot = message.bot
    try:
        chat = await bot.get_chat(f"@{username}")
    except Exception:
        await message.answer(
            "Не удалось найти канал. Убедись, что он публичный и username верный."
        )
        return

    if chat.type not in {"channel", "supergroup"}:
        await message.answer("Это не канал. Нужен публичный Telegram-канал.")
        return

    service = ChannelService(session)
    channel = await service.add_channel_for_user(
        db_user,
        telegram_id=chat.id,
        title=chat.title or username,
        username=chat.username or username,
    )
    await message.answer(f"Канал «{channel.title}» добавлен и включён.")
    await _render_channels(message, session, db_user)


@router.callback_query(F.data.startswith("ch:toggle:"))
async def cb_toggle(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[-1])
    service = ChannelService(session)
    channel = await service.get_channel(channel_id)
    if not channel:
        await callback.answer("Канал не найден", show_alert=True)
        return
    await service.set_channel_enabled(channel_id, not channel.enabled)
    await callback.answer("Обновлено")
    if callback.message:
        await _render_channels(callback.message, session, db_user)


@router.callback_query(F.data.startswith("ch:rm:"))
async def cb_remove(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    channel_id = int(callback.data.split(":")[-1])
    ok = await ChannelService(session).remove_user_channel(db_user.id, channel_id)
    await callback.answer("Удалено" if ok else "Не найдено")
    if callback.message:
        await _render_channels(callback.message, session, db_user)


@router.callback_query(F.data.startswith("ch:info:"))
async def cb_info(callback: CallbackQuery, session: AsyncSession) -> None:
    channel_id = int(callback.data.split(":")[-1])
    channel = await ChannelService(session).get_channel(channel_id)
    if not channel:
        await callback.answer("Не найден", show_alert=True)
        return
    await callback.answer(
        f"{channel.title} | enabled={channel.enabled}",
        show_alert=True,
    )
