"""Telegram admin panel (/admin) — password-gated menu."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.reply import main_menu
from app.bot.states import AdminAuthStates
from app.models import User
from app.services.admin_service import AdminService, verify_password
from app.services.preferences import PreferencesService

router = Router(name="admin_panel")

BTN_STATS = "📊 Статистика"
BTN_USERS = "👥 Пользователи"
BTN_NEWS = "📰 Новости"
BTN_CHANNELS = "📡 Каналы"
BTN_AI = "🤖 AI/Graph"
BTN_ADMINS = "🛡 Администраторы"
BTN_EXIT = "🚪 Выйти"
BTN_BACK = "🔙 Назад"


def admin_menu_keyboard(*, is_owner: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_USERS)],
        [KeyboardButton(text=BTN_NEWS), KeyboardButton(text=BTN_CHANNELS)],
        [KeyboardButton(text=BTN_AI)],
    ]
    if is_owner:
        rows.append([KeyboardButton(text=BTN_ADMINS)])
    rows.append([KeyboardButton(text=BTN_EXIT)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


async def _require_session(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(data.get("admin_ok"))


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    svc = AdminService(session)
    await svc.ensure_owner_row(db_user)
    if not await svc.is_admin_user(db_user):
        return

    acc = await svc.get_account(db_user.id)
    if not acc:
        return

    await state.clear()
    if acc.must_set_password or not acc.password_hash:
        await state.set_state(AdminAuthStates.create_password)
        await message.answer(
            "Создайте пароль для админ-панели (минимум 6 символов):",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.set_state(AdminAuthStates.enter_password)
    await message.answer("Введите пароль админ-панели:", reply_markup=ReplyKeyboardRemove())


@router.message(AdminAuthStates.create_password)
async def admin_create_password(message: Message, state: FSMContext) -> None:
    pwd = (message.text or "").strip()
    if len(pwd) < 6:
        await message.answer("Пароль слишком короткий. Минимум 6 символов:")
        return
    await state.update_data(new_password=pwd)
    await state.set_state(AdminAuthStates.confirm_password)
    await message.answer("Повторите пароль:")


@router.message(AdminAuthStates.confirm_password)
async def admin_confirm_password(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    pwd = data.get("new_password") or ""
    if (message.text or "").strip() != pwd:
        await state.set_state(AdminAuthStates.create_password)
        await message.answer("Пароли не совпали. Введите новый пароль:")
        return
    svc = AdminService(session)
    await svc.set_password(db_user, pwd)
    is_owner = await svc.is_owner(db_user)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, is_owner=is_owner)
    await message.answer("Пароль сохранён. Админ-меню:", reply_markup=admin_menu_keyboard(is_owner=is_owner))


@router.message(AdminAuthStates.enter_password)
async def admin_enter_password(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    svc = AdminService(session)
    acc = await svc.get_account(db_user.id)
    if not acc or not verify_password(message.text or "", acc.password_hash):
        await message.answer("Неверный пароль. Попробуйте ещё раз или /admin")
        return
    is_owner = await svc.is_owner(db_user)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, is_owner=is_owner)
    await message.answer("Админ-меню:", reply_markup=admin_menu_keyboard(is_owner=is_owner))


@router.message(AdminAuthStates.menu, F.text == BTN_EXIT)
async def admin_exit(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    lang = await PreferencesService(session).lang(db_user)
    await message.answer("Вышли из админ-панели.", reply_markup=main_menu(lang))


@router.message(AdminAuthStates.menu, F.text == BTN_STATS)
async def admin_stats(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    stats = await AdminService(session).admin_statistics()
    text = (
        "<b>📊 Статистика</b>\n\n"
        f"👥 Пользователи: <b>{stats['users_total']}</b> "
        f"(активных за сутки: {stats['users_active_today']})\n"
        f"📡 Каналы: <b>{stats['channels']}</b>\n"
        f"📰 Посты: <b>{stats['posts']}</b>\n"
        f"⚡️ События: <b>{stats['events']}</b>\n"
        f"🕸 Nodes / Edges: <b>{stats['nodes']}</b> / <b>{stats['edges']}</b>\n"
        f"🤖 AI запросов: <b>{stats['ai_requests']}</b>\n"
        f"🪙 Tokens in/out/Σ: {stats['tokens_in']} / {stats['tokens_out']} / {stats['tokens_total']}"
    )
    await message.answer(text)


@router.message(AdminAuthStates.menu, F.text == BTN_USERS)
async def admin_users_prompt(message: Message, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    await state.set_state(AdminAuthStates.find_user)
    await message.answer(
        "Пришлите @username, telegram_id или id пользователя.\n"
        "Или «list» для последних 20.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_BACK)]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminAuthStates.find_user, F.text == BTN_BACK)
async def admin_users_back(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    is_owner = await AdminService(session).is_owner(db_user)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, is_owner=is_owner)
    await message.answer("Админ-меню:", reply_markup=admin_menu_keyboard(is_owner=is_owner))


@router.message(
    StateFilter(AdminAuthStates.menu, AdminAuthStates.find_user),
    F.text.regexp(r"(?i)^(ban|unban|clear)\s+\d+$"),
)
async def admin_user_action(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if not await _require_session(state):
        return
    parts = (message.text or "").split()
    action, uid_s = parts[0].lower(), parts[1]
    svc = AdminService(session)
    target = await svc.find_user(uid_s)
    if not target:
        await message.answer("Пользователь не найден.")
        return
    if action == "ban":
        await svc.ban_user(target)
        await message.answer(f"Забанен user_id={target.id}")
    elif action == "unban":
        await svc.unban_user(target)
        await message.answer(f"Разбанен user_id={target.id}")
    else:
        n = await svc.clear_user_unread(target.id)
        await message.answer(f"Скрыто непрочитанных: {n}")


@router.message(AdminAuthStates.find_user)
async def admin_users_find(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    svc = AdminService(session)
    q = (message.text or "").strip()
    if q.lower() == "list":
        users = await svc.list_users(limit=20)
        if not users:
            await message.answer("Пользователей нет.")
            return
        lines = ["<b>👥 Последние пользователи</b>", ""]
        for u in users:
            uname = f"@{u.username}" if u.username else "—"
            ban = " 🚫" if u.is_banned else ""
            lines.append(f"• {u.id} · {uname} · tg:{u.telegram_id}{ban}")
        await message.answer("\n".join(lines))
        return

    user = await svc.find_user(q)
    if not user:
        await message.answer("Не найден. Попробуйте ещё раз или «list».")
        return
    card = await svc.user_card_stats(user)
    text = (
        f"<b>👤 {card['username'] or '—'}</b>\n"
        f"id: {user.id}\n"
        f"telegram_id: {card['telegram_id']}\n"
        f"каналы: {card['channels']}\n"
        f"прочитано: {card['read']}\n"
        f"бан: {'да' if card['banned'] else 'нет'}\n"
        f"создан: {card['created_at']}\n\n"
        "Команды:\n"
        f"<code>ban {user.id}</code>\n"
        f"<code>unban {user.id}</code>\n"
        f"<code>clear {user.id}</code>"
    )
    await message.answer(text)


@router.message(AdminAuthStates.menu, F.text == BTN_NEWS)
async def admin_news(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    stats = await AdminService(session).admin_statistics()
    await message.answer(
        f"<b>📰 Новости</b>\n\n"
        f"Активных событий: <b>{stats['events']}</b>\n"
        f"Постов: <b>{stats['posts']}</b>\n\n"
        "Очистить непрочитанное у всех:\n<code>clear_all_unread</code>"
    )


@router.message(AdminAuthStates.menu, F.text == "clear_all_unread")
async def admin_clear_all(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    n = await AdminService(session).clear_all_unread()
    await message.answer(f"Скрыто непрочитанных записей: {n}")


@router.message(AdminAuthStates.menu, F.text == BTN_CHANNELS)
async def admin_channels(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    stats = await AdminService(session).admin_statistics()
    await message.answer(f"<b>📡 Каналы</b>\n\nВсего в базе: <b>{stats['channels']}</b>")


@router.message(AdminAuthStates.menu, F.text == BTN_AI)
async def admin_ai(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    stats = await AdminService(session).admin_statistics()
    await message.answer(
        f"<b>🤖 AI / Graph</b>\n\n"
        f"AI запросов: <b>{stats['ai_requests']}</b>\n"
        f"Tokens Σ: <b>{stats['tokens_total']}</b>\n"
        f"Nodes: <b>{stats['nodes']}</b>\n"
        f"Edges: <b>{stats['edges']}</b>\n\n"
        "Пересборка графа:\n🚧 Функция в развитии"
    )


@router.message(AdminAuthStates.menu, F.text == BTN_ADMINS)
async def admin_admins_menu(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_session(state):
        return
    svc = AdminService(session)
    if not await svc.is_owner(db_user):
        await message.answer("Только для OWNER.")
        return
    rows = await svc.list_admins()
    lines = ["<b>🛡 Администраторы</b>", ""]
    for acc, u in rows:
        uname = f"@{u.username}" if u.username else str(u.telegram_id)
        lines.append(f"• {acc.role} · {uname} · uid={u.id}")
    lines.append("")
    lines.append("Назначить: пришлите @username или telegram_id")
    lines.append("Снять: <code>remove UID</code>")
    lines.append("Сброс пароля: <code>reset UID</code>")
    await state.set_state(AdminAuthStates.appoint_admin)
    await message.answer(
        "\n".join(lines),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_BACK)]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminAuthStates.appoint_admin, F.text == BTN_BACK)
async def admin_admins_back(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    is_owner = await AdminService(session).is_owner(db_user)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, is_owner=is_owner)
    await message.answer("Админ-меню:", reply_markup=admin_menu_keyboard(is_owner=is_owner))


@router.message(AdminAuthStates.appoint_admin)
async def admin_admins_action(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    svc = AdminService(session)
    if not await svc.is_owner(db_user):
        await message.answer("Только для OWNER.")
        return
    text = (message.text or "").strip()
    if text.lower().startswith("remove "):
        uid = text.split(maxsplit=1)[1].strip()
        if not uid.isdigit():
            await message.answer("Использование: remove UID")
            return
        ok = await svc.remove_admin(target_user_id=int(uid), by=db_user)
        await message.answer("Снято." if ok else "Не удалось (owner или не найден).")
        return
    if text.lower().startswith("reset "):
        uid = text.split(maxsplit=1)[1].strip()
        if not uid.isdigit():
            await message.answer("Использование: reset UID")
            return
        acc = await svc.reset_password(int(uid))
        await message.answer("Пароль сброшен." if acc else "Не найден.")
        return

    target = await svc.find_user(text)
    if not target:
        await message.answer("Пользователь не найден.")
        return
    await svc.appoint_admin(target=target, by=db_user)
    await message.answer(f"Назначен admin: {target.username or target.telegram_id} (uid={target.id})")


# Swallow unknown texts while in admin menu so they don't leak to other handlers
@router.message(StateFilter(AdminAuthStates.menu))
async def admin_menu_fallback(message: Message) -> None:
    await message.answer("Выберите пункт меню или «Выйти».")
