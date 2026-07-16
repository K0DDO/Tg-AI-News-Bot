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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.reply import main_menu
from app.bot.states import AdminAuthStates
from app.config import get_settings
from app.health import admin_logs, diagnostics_snapshot, last_ingest, record_admin_log
from app.models import User
from app.models.admin import AdminAccount
from app.services.admin_service import AdminService, verify_password
from app.services.preferences import PreferencesService
from app.services.redis_client import ping_redis

try:
    from aiogram.dispatcher.event.bases import SkipHandler
except ImportError:  # pragma: no cover
    from aiogram.exceptions import SkipHandler  # type: ignore

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


def _role_emoji(acc: AdminAccount | None, *, is_banned: bool) -> str:
    if is_banned:
        return "🚫"
    if acc is None:
        return "👤"
    if acc.role == "owner":
        return "👑"
    return "🛠"


def _tg_line(u: User) -> str:
    """Telegram ID + @username on one line."""
    if u.username:
        return f"<code>{u.telegram_id}</code> @{u.username}"
    return f"<code>{u.telegram_id}</code>"


def _user_card(u: User, acc: AdminAccount | None = None) -> str:
    role = "обычный"
    if acc and acc.role == "owner":
        role = "owner"
    elif acc:
        role = "admin"
    ban = "запрещён" if u.is_banned else "активен"
    mark = _role_emoji(acc, is_banned=bool(u.is_banned))
    return (
        f"<b>Пользователь</b> {mark}\n"
        f"ID: <code>{u.id}</code>\n"
        f"Telegram: {_tg_line(u)}\n"
        f"Роль: <b>{role}</b>\n"
        f"Статус: {ban}"
    )


def _user_actions_kb(
    user_id: int,
    *,
    is_banned: bool,
    target_acc: AdminAccount | None,
    actor_is_owner: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
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
                text="🔄 Сбросить (каналы оставить)",
                callback_data=f"adm:reset:{user_id}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="🧹 Полная очистка",
                callback_data=f"adm:wipe:{user_id}",
            )
        ]
    )
    # Owner-only promote / demote (never touch another owner)
    if actor_is_owner and not (target_acc and target_acc.role == "owner"):
        if target_acc:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="👤 Снять админа",
                        callback_data=f"adm:demote:{user_id}",
                    )
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text="🛠 Назначить админом",
                        callback_data=f"adm:promote:{user_id}",
                    )
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _require_admin(
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> bool:
    """Hard gate: must be admin in DB + logged in this session."""
    svc = AdminService(session)
    if not await svc.is_admin_user(db_user):
        await state.clear()
        return False
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


async def _track(state: FSMContext, *messages: Message | None) -> None:
    data = await state.get_data()
    ids: list[int] = list(data.get("admin_msg_ids") or [])
    for msg in messages:
        if msg is None:
            continue
        mid = getattr(msg, "message_id", None)
        if mid is not None and int(mid) not in ids:
            ids.append(int(mid))
    await state.update_data(admin_msg_ids=ids)


async def _admin_answer(
    message: Message,
    state: FSMContext,
    text: str,
    **kwargs,
) -> Message:
    await _track(state, message)
    sent = await message.answer(text, **kwargs)
    await _track(state, sent)
    return sent


async def _purge_admin_messages(message: Message, state: FSMContext) -> None:
    await _track(state, message)
    data = await state.get_data()
    ids = list(data.get("admin_msg_ids") or [])
    chat_id = message.chat.id if message.chat else None
    if chat_id is None:
        return
    for mid in ids:
        try:
            await message.bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def _refresh_user_card(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    target: User,
    actor: User,
) -> None:
    svc = AdminService(session)
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(actor)
    if callback.message:
        await _track(state, callback.message)
        await callback.message.edit_text(
            _user_card(target, acc),
            reply_markup=_user_actions_kb(
                target.id,
                is_banned=bool(target.is_banned),
                target_acc=acc,
                actor_is_owner=actor_owner,
            ),
        )


# ── /admin must be registered before the FSM gate ───────────────────────────


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
        # Silent ignore for regular users + unstick leftover FSM
        await state.clear()
        return

    acc = await svc.get_account(db_user.id)
    if not acc:
        await state.clear()
        return

    await state.clear()
    await _safe_delete(message)

    if acc.must_set_password or not acc.password_hash:
        await state.set_state(AdminAuthStates.create_password)
        prompt = await message.answer(
            "Создайте пароль для админ-панели (минимум 6 символов):",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.update_data(admin_msg_ids=[prompt.message_id])
        return

    await state.set_state(AdminAuthStates.enter_password)
    prompt = await message.answer(
        "Введите пароль админ-панели:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.update_data(admin_msg_ids=[prompt.message_id])


# ── Gate: non-admins must never stay in admin FSM ───────────────────────────


@router.message(StateFilter(AdminAuthStates))
@router.callback_query(StateFilter(AdminAuthStates))
async def admin_fsm_gate(
    event: Message | CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    """
    First handler for any admin FSM update (after /admin).
    Non-admins: clear state and skip so normal bot handlers run (no «Неверный пароль»).
    Admins: skip to the specific admin handler below.
    """
    svc = AdminService(session)
    if await svc.is_admin_user(db_user):
        raise SkipHandler()
    await state.clear()
    if isinstance(event, CallbackQuery):
        try:
            await event.answer()
        except Exception:
            pass
        return
    raise SkipHandler()


@router.message(AdminAuthStates.create_password, F.text, ~F.text.startswith("/"))
async def admin_create_password(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await AdminService(session).is_admin_user(db_user):
        await state.clear()
        raise SkipHandler()
    pwd = (message.text or "").strip()
    await _track(state, message)
    await _safe_delete(message)
    if len(pwd) < 6:
        await _admin_answer(message, state, "Пароль слишком короткий. Минимум 6 символов:")
        return
    await state.update_data(new_password=pwd)
    await state.set_state(AdminAuthStates.confirm_password)
    await _admin_answer(message, state, "Повторите пароль:")


@router.message(AdminAuthStates.confirm_password, F.text, ~F.text.startswith("/"))
async def admin_confirm_password(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    svc = AdminService(session)
    if not await svc.is_admin_user(db_user):
        await state.clear()
        raise SkipHandler()
    data = await state.get_data()
    pwd = data.get("new_password") or ""
    await _track(state, message)
    await _safe_delete(message)
    if (message.text or "").strip() != pwd:
        await state.set_state(AdminAuthStates.create_password)
        await _admin_answer(message, state, "Пароли не совпали. Введите новый пароль:")
        return
    await svc.set_password(db_user, pwd)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, new_password=None)
    await _admin_answer(message, state, "🛠 Админ-меню:", reply_markup=admin_menu_keyboard())
    record_admin_log("INFO", f"Admin login uid={db_user.id}")


@router.message(AdminAuthStates.enter_password, F.text, ~F.text.startswith("/"))
async def admin_enter_password(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    svc = AdminService(session)
    # Never unlock panel for non-admins, even with a guessed password
    if not await svc.is_admin_user(db_user):
        await state.clear()
        raise SkipHandler()
    acc = await svc.get_account(db_user.id)
    if not acc or not acc.password_hash:
        await state.clear()
        raise SkipHandler()
    pwd_ok = verify_password(message.text or "", acc.password_hash)
    await _track(state, message)
    await _safe_delete(message)
    if not pwd_ok:
        await _admin_answer(message, state, "Неверный пароль. Попробуйте ещё раз или /admin")
        return
    await _purge_admin_messages(message, state)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, admin_msg_ids=[])
    await _admin_answer(message, state, "🛠 Админ-меню:", reply_markup=admin_menu_keyboard())
    record_admin_log("INFO", f"Admin login uid={db_user.id}")


@router.message(AdminAuthStates.menu, F.text == BTN_EXIT)
async def admin_exit(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    await _purge_admin_messages(message, state)
    await state.clear()
    lang = await PreferencesService(session).lang(db_user)
    await message.answer("Вышли из админ-панели.", reply_markup=main_menu(lang))


@router.message(AdminAuthStates.menu, F.text == BTN_STATS)
async def admin_stats(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
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
    await _admin_answer(message, state, text)


@router.message(AdminAuthStates.menu, F.text == BTN_LOGS)
async def admin_logs_view(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
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
    await _admin_answer(message, state, "\n".join(lines))


@router.message(AdminAuthStates.menu, F.text == BTN_DIAG)
async def admin_diag(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
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
    await _admin_answer(message, state, text)


@router.message(AdminAuthStates.menu, F.text == BTN_USERS)
async def admin_users_start(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    svc = AdminService(session)
    recent = await svc.list_users(limit=8)
    lines = ["<b>👥 Пользователи</b>", ""]
    lines.append("👑 owner · 🛠 admin · 👤 обычный · 🚫 бан")
    lines.append("")
    if recent:
        lines.append("Недавние:")
        for u in recent:
            acc = await svc.get_account(u.id)
            mark = _role_emoji(acc, is_banned=bool(u.is_banned))
            lines.append(f"{mark} {_tg_line(u)}")
    lines.append("")
    lines.append(
        "Пришлите Telegram ID / @username / внутренний id.\n\n"
        f"Или «{BTN_CANCEL}»."
    )
    await state.set_state(AdminAuthStates.find_user)
    await state.update_data(admin_ok=True)
    await _admin_answer(
        message,
        state,
        "\n".join(lines),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminAuthStates.find_user, F.text == BTN_CANCEL)
async def admin_users_cancel(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True)
    await _admin_answer(message, state, "🛠 Админ-меню:", reply_markup=admin_menu_keyboard())


@router.message(AdminAuthStates.find_user, F.text, ~F.text.startswith("/"))
async def admin_users_find(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    svc = AdminService(session)
    target = await svc.find_user(message.text or "")
    if not target:
        await _admin_answer(message, state, "Не найден. Пришлите ID / @username или «Отмена».")
        return
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(db_user)
    await _admin_answer(
        message,
        state,
        _user_card(target, acc),
        reply_markup=_user_actions_kb(
            target.id,
            is_banned=bool(target.is_banned),
            target_acc=acc,
            actor_is_owner=actor_owner,
        ),
    )


@router.callback_query(F.data.startswith("adm:ban:"))
async def admin_ban(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    svc = AdminService(session)
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    await svc.ban_user(target)
    record_admin_log("INFO", f"Banned user id={uid}")
    await callback.answer("Забанен")
    await _refresh_user_card(callback, session, state, target, db_user)


@router.callback_query(F.data.startswith("adm:unban:"))
async def admin_unban(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    svc = AdminService(session)
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    await svc.unban_user(target)
    record_admin_log("INFO", f"Unbanned user id={uid}")
    await callback.answer("Разбанен")
    await _refresh_user_card(callback, session, state, target, db_user)


@router.callback_query(F.data.startswith("adm:reset:"))
async def admin_soft_reset(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
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
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(db_user)
    if callback.message:
        await _track(state, callback.message)
        await callback.message.edit_text(
            _user_card(target, acc)
            + "\n\n🔄 Сброшен: онбординг заново, история/избранное очищены.\n"
            "📡 Каналы у пользователя остались.\n"
            "Пусть нажмёт /start.",
            reply_markup=_user_actions_kb(
                target.id,
                is_banned=bool(target.is_banned),
                target_acc=acc,
                actor_is_owner=actor_owner,
            ),
        )


@router.callback_query(F.data.startswith("adm:wipe:"))
async def admin_full_wipe(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    svc = AdminService(session)
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    stats = await svc.full_reset_user(target)
    record_admin_log(
        "INFO",
        f"Full-wipe user id={uid} states={stats.get('states')} "
        f"channels={stats.get('channels')} reactions={stats.get('reactions')}",
    )
    await callback.answer("Полностью очищен", show_alert=True)
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(db_user)
    if callback.message:
        await _track(state, callback.message)
        await callback.message.edit_text(
            _user_card(target, acc)
            + "\n\n🧹 Полная очистка: как будто бот впервые.\n"
            "📡 Связи с каналами сняты (сами каналы в базе остались).\n"
            "Пусть нажмёт /start и добавит каналы заново.",
            reply_markup=_user_actions_kb(
                target.id,
                is_banned=bool(target.is_banned),
                target_acc=acc,
                actor_is_owner=actor_owner,
            ),
        )


@router.callback_query(F.data.startswith("adm:promote:"))
async def admin_promote(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    svc = AdminService(session)
    if not await svc.is_owner(db_user):
        await callback.answer("Только owner", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    try:
        await svc.appoint_admin(target=target, by=db_user)
    except PermissionError:
        await callback.answer("Только owner", show_alert=True)
        return
    record_admin_log("INFO", f"Appointed admin user id={uid} by={db_user.id}")
    await callback.answer("Назначен админом", show_alert=True)
    await _refresh_user_card(callback, session, state, target, db_user)


@router.callback_query(F.data.startswith("adm:demote:"))
async def admin_demote(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    svc = AdminService(session)
    if not await svc.is_owner(db_user):
        await callback.answer("Только owner", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    try:
        ok = await svc.remove_admin(target_user_id=target.id, by=db_user)
    except PermissionError:
        await callback.answer("Только owner", show_alert=True)
        return
    if not ok:
        await callback.answer("Нельзя снять", show_alert=True)
        return
    record_admin_log("INFO", f"Removed admin user id={uid} by={db_user.id}")
    await callback.answer("Админ снят", show_alert=True)
    await _refresh_user_card(callback, session, state, target, db_user)


@router.message(AdminAuthStates.menu, F.text == BTN_PASSWORD)
async def admin_change_password_start(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    await state.set_state(AdminAuthStates.change_password)
    await state.update_data(admin_ok=True)
    await _admin_answer(
        message,
        state,
        "Введите новый пароль админки (минимум 6 символов):\n"
        f"Или «{BTN_CANCEL}».",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
            resize_keyboard=True,
        ),
    )


@router.message(AdminAuthStates.change_password, F.text == BTN_CANCEL)
@router.message(AdminAuthStates.confirm_change_password, F.text == BTN_CANCEL)
async def admin_change_password_cancel(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, new_password=None)
    await _admin_answer(message, state, "Отменено.", reply_markup=admin_menu_keyboard())


@router.message(AdminAuthStates.change_password, F.text, ~F.text.startswith("/"))
async def admin_change_password_enter(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    pwd = (message.text or "").strip()
    await _track(state, message)
    await _safe_delete(message)
    if len(pwd) < 6:
        await _admin_answer(message, state, "Пароль слишком короткий. Минимум 6 символов:")
        return
    await state.update_data(new_password=pwd)
    await state.set_state(AdminAuthStates.confirm_change_password)
    await _admin_answer(message, state, "Повторите новый пароль:")


@router.message(AdminAuthStates.confirm_change_password, F.text, ~F.text.startswith("/"))
async def admin_change_password_confirm(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    data = await state.get_data()
    pwd = data.get("new_password") or ""
    await _track(state, message)
    await _safe_delete(message)
    if (message.text or "").strip() != pwd:
        await state.set_state(AdminAuthStates.change_password)
        await _admin_answer(message, state, "Пароли не совпали. Введите новый пароль:")
        return
    await AdminService(session).set_password(db_user, pwd)
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True, new_password=None)
    record_admin_log("INFO", f"Admin password changed uid={db_user.id}")
    await _admin_answer(message, state, "🔑 Пароль обновлён.", reply_markup=admin_menu_keyboard())


@router.message(StateFilter(AdminAuthStates.menu))
async def admin_menu_fallback(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    await _admin_answer(
        message,
        state,
        "Выберите: Статистика · Пользователи · Логи · Диагностика · Пароль · Выйти",
    )
