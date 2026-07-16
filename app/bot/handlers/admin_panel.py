"""Telegram admin panel (/admin) — stats, logs, users, password."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.reply import main_menu
from app.bot.states import AdminAuthStates
from app.config import get_settings
from app.health import admin_logs, diagnostics_snapshot, last_ingest, record_admin_log
from app.models import User
from app.services.admin_service import AdminService, verify_password
from app.services.preferences import PreferencesService
from app.services.redis_client import ping_redis

router = Router(name="admin_panel")

BTN_STATS = "📊 Статистика"
BTN_LOGS = "📜 Логи"
BTN_DIAG = "🧪 Диагностика"
BTN_USERS = "👥 Пользователи"
BTN_PASSWORD = "🔑 Сменить пароль"
BTN_EXIT = "🚪 Выйти"
BTN_CANCEL = "❌ Отмена"


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_USERS)],
            [KeyboardButton(text=BTN_LOGS), KeyboardButton(text=BTN_DIAG)],
            [KeyboardButton(text=BTN_PASSWORD)],
            [KeyboardButton(text=BTN_EXIT)],
        ],
        resize_keyboard=True,
    )


def _user_card(u: User) -> str:
    uname = f"@{u.username}" if u.username else "—"
    ban = "🚫 забанен" if u.is_banned else "✅ активен"
    return (
        f"<b>Пользователь</b>\n"
        f"ID: <code>{u.id}</code>\n"
        f"Telegram: <code>{u.telegram_id}</code>\n"
        f"Username: {uname}\n"
        f"Статус: {ban}"
    )


def _user_actions_kb(user_id: int, *, is_banned: bool) -> InlineKeyboardMarkup:
    rows = []
    if is_banned:
        rows.append(
            [InlineKeyboardButton(text="✅ Разбанить", callback_data=f"adm:unban:{user_id}")]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="🚫 Забанить", callback_data=f"adm:ban:{user_id}")]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Сбросить как нового",
                callback_data=f"adm:reset:{user_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _require_session(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(data.get("admin_ok"))


async def _safe_delete(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        pass


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
    await _safe_delete(message)

    if acc.must_set_password or not acc.password_hash:
        await state.set_state(AdminAuthStates.create_password)
        prompt = await message.answer(
            "Создайте пароль для админ-панели (минимум 6 символов):",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.update_data(prompt_id=prompt.message_id)
        return

    await state.set_state(AdminAuthStates.enter_password)
    prompt = await message.answer(
        "Введите пароль админ-панели:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.update_data(prompt_id=prompt.message_id)


@router.message(AdminAuthStates.create_password)
async def admin_create_password(message: Message, state: FSMContext) -> None:
    pwd = (message.text or "").strip()
    await _safe_delete(message)
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
    await _safe_delete(message)
    if (message.text or "").strip() != pwd:
        await state.set_state(AdminAuthStates.create_password)
        await message.answer("Пароли не совпали. Введите новый пароль:")
        return
    svc = AdminService(session)
    await svc.set_password(db_user, pwd)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, new_password=None)
    await message.answer("🛠 Админ-меню:", reply_markup=admin_menu_keyboard())
    record_admin_log("INFO", f"Admin login uid={db_user.id}")


@router.message(AdminAuthStates.enter_password)
async def admin_enter_password(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    svc = AdminService(session)
    acc = await svc.get_account(db_user.id)
    data = await state.get_data()
    prompt_id = data.get("prompt_id")
    pwd_ok = acc and verify_password(message.text or "", acc.password_hash)
    await _safe_delete(message)
    if prompt_id and message.chat:
        try:
            await message.bot.delete_message(message.chat.id, int(prompt_id))
        except Exception:
            pass
    if not pwd_ok:
        await message.answer("Неверный пароль. Попробуйте ещё раз или /admin")
        return
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True)
    accepted = await message.answer("Пароль принят.")
    await _safe_delete(accepted)
    await message.answer("🛠 Админ-меню:", reply_markup=admin_menu_keyboard())
    record_admin_log("INFO", f"Admin login uid={db_user.id}")


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
        f"👥 <b>Пользователи</b>\n"
        f"Всего: <b>{stats['users_total']}</b>\n\n"
        f"📰 <b>Новости</b>\n"
        f"Постов: <b>{stats['posts']}</b>\n\n"
        f"🔥 <b>Events</b>\n"
        f"Событий: <b>{stats['events']}</b>\n\n"
        f"📡 <b>Каналы</b>\n"
        f"Всего: <b>{stats['channels']}</b>\n\n"
        f"🤖 <b>AI запросы</b>\n"
        f"Обращений: <b>{stats['ai_requests']}</b>"
    )
    await message.answer(text)


@router.message(AdminAuthStates.menu, F.text == BTN_LOGS)
async def admin_logs_view(message: Message, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    errors = admin_logs(limit=15, errors_only=True)
    infos = [r for r in admin_logs(limit=25) if r["level"] != "ERROR"][:15]
    lines = ["<b>📜 Логи</b>", "", "<b>Ошибки</b>"]
    if errors:
        for r in errors:
            lines.append(f"❌ {r['ts']} {r['message']}")
    else:
        lines.append("— нет")
    lines.append("")
    lines.append("<b>INFO</b>")
    if infos:
        for r in infos:
            lines.append(f"INFO: {r['message']}")
    else:
        lines.append("— нет")
    await message.answer("\n".join(lines))


@router.message(AdminAuthStates.menu, F.text == BTN_DIAG)
async def admin_diag(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    snap = diagnostics_snapshot()
    ingest = snap.get("last_ingest") or last_ingest() or {}
    redis_ok = await ping_redis()
    settings = get_settings()
    errs = snap.get("last_errors") or []
    ai = settings.ai_provider or "—"
    text = (
        "<b>🧪 Диагностика</b>\n\n"
        f"Scheduler: работает ✅\n"
        f"Uptime: {snap.get('uptime')}\n"
        f"Parser (последний ingest):\n"
        f"  +{ingest.get('created_messages', '—')} msgs / "
        f"{ingest.get('processed', '—')} processed\n"
        f"Redis: {'✅' if redis_ok else '❌'}\n"
        f"AI: {ai}\n\n"
        "<b>Последняя ошибка</b>\n"
    )
    if errs:
        text += f"{errs[0]}"
    else:
        text += "нет"
    await message.answer(text)


@router.message(AdminAuthStates.menu, F.text == BTN_USERS)
async def admin_users_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    svc = AdminService(session)
    recent = await svc.list_users(limit=8)
    lines = ["<b>👥 Пользователи</b>", ""]
    if recent:
        lines.append("Недавние:")
        for u in recent:
            mark = "🚫" if u.is_banned else "·"
            uname = f"@{u.username}" if u.username else "—"
            lines.append(f"{mark} <code>{u.telegram_id}</code> {uname}")
    lines.append("")
    lines.append(
        "Пришлите Telegram ID / @username / внутренний id,\n"
        "чтобы забанить, разбанить или сбросить как нового "
        "(каналы сохранятся).\n\n"
        f"Или нажмите «{BTN_CANCEL}»."
    )
    await state.set_state(AdminAuthStates.find_user)
    await state.update_data(admin_ok=True)
    await message.answer(
        "\n".join(lines),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminAuthStates.find_user, F.text == BTN_CANCEL)
async def admin_users_cancel(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True)
    await message.answer("🛠 Админ-меню:", reply_markup=admin_menu_keyboard())


@router.message(AdminAuthStates.find_user)
async def admin_users_find(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    svc = AdminService(session)
    target = await svc.find_user(message.text or "")
    if not target:
        await message.answer("Не найден. Пришлите ID / @username или «Отмена».")
        return
    await message.answer(
        _user_card(target),
        reply_markup=_user_actions_kb(target.id, is_banned=bool(target.is_banned)),
    )


@router.callback_query(F.data.startswith("adm:ban:"))
async def admin_ban(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        await callback.answer("Сначала /admin", show_alert=True)
        return
    from sqlalchemy import select

    uid = int((callback.data or "").split(":")[2])
    svc = AdminService(session)
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    await svc.ban_user(target)
    record_admin_log("INFO", f"Banned user id={uid}")
    await callback.answer("Забанен")
    if callback.message:
        await callback.message.edit_text(
            _user_card(target),
            reply_markup=_user_actions_kb(target.id, is_banned=True),
        )


@router.callback_query(F.data.startswith("adm:unban:"))
async def admin_unban(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        await callback.answer("Сначала /admin", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    from sqlalchemy import select

    svc = AdminService(session)
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    await svc.unban_user(target)
    record_admin_log("INFO", f"Unbanned user id={uid}")
    await callback.answer("Разбанен")
    if callback.message:
        await callback.message.edit_text(
            _user_card(target),
            reply_markup=_user_actions_kb(target.id, is_banned=False),
        )


@router.callback_query(F.data.startswith("adm:reset:"))
async def admin_soft_reset(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not await _require_session(state):
        await callback.answer("Сначала /admin", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    from sqlalchemy import select

    svc = AdminService(session)
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    stats = await svc.soft_reset_user(target)
    record_admin_log(
        "INFO",
        f"Soft-reset user id={uid} states={stats.get('states')} reactions={stats.get('reactions')}",
    )
    await callback.answer("Сброшен как новый", show_alert=True)
    if callback.message:
        await callback.message.edit_text(
            _user_card(target)
            + "\n\n🔄 Сброшен: онбординг заново, история/избранное очищены.\n"
            "📡 Каналы сохранены.\n"
            "Пусть пользователь нажмёт /start.",
            reply_markup=_user_actions_kb(target.id, is_banned=bool(target.is_banned)),
        )


@router.message(AdminAuthStates.menu, F.text == BTN_PASSWORD)
async def admin_change_password_start(message: Message, state: FSMContext) -> None:
    if not await _require_session(state):
        return
    await state.set_state(AdminAuthStates.change_password)
    await state.update_data(admin_ok=True)
    await message.answer(
        "Введите новый пароль админки (минимум 6 символов):\n"
        f"Или «{BTN_CANCEL}».",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminAuthStates.change_password, F.text == BTN_CANCEL)
@router.message(AdminAuthStates.confirm_change_password, F.text == BTN_CANCEL)
async def admin_change_password_cancel(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, new_password=None)
    await message.answer("Отменено.", reply_markup=admin_menu_keyboard())


@router.message(AdminAuthStates.change_password)
async def admin_change_password_enter(message: Message, state: FSMContext) -> None:
    pwd = (message.text or "").strip()
    await _safe_delete(message)
    if len(pwd) < 6:
        await message.answer("Пароль слишком короткий. Минимум 6 символов:")
        return
    await state.update_data(new_password=pwd)
    await state.set_state(AdminAuthStates.confirm_change_password)
    await message.answer("Повторите новый пароль:")


@router.message(AdminAuthStates.confirm_change_password)
async def admin_change_password_confirm(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    pwd = data.get("new_password") or ""
    await _safe_delete(message)
    if (message.text or "").strip() != pwd:
        await state.set_state(AdminAuthStates.change_password)
        await message.answer("Пароли не совпали. Введите новый пароль:")
        return
    await AdminService(session).set_password(db_user, pwd)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, new_password=None)
    record_admin_log("INFO", f"Admin password changed uid={db_user.id}")
    await message.answer("🔑 Пароль обновлён.", reply_markup=admin_menu_keyboard())


@router.message(StateFilter(AdminAuthStates.menu))
async def admin_menu_fallback(message: Message) -> None:
    await message.answer(
        "Выберите: Статистика · Пользователи · Логи · Диагностика · Пароль · Выйти"
    )
