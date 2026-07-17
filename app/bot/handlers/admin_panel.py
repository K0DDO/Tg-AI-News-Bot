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
BTN_LOGS = "📝 Логи"
BTN_GRAPH = "🕸 Граф"
BTN_AI = "🤖 AI"
BTN_USERS = "👥 Пользователи"
BTN_SYSTEM = "⚙️ Система"
BTN_WHITELIST = "🔐 Вайтлист"
BTN_PASSWORD = "🔑 Сменить пароль"
BTN_EXIT = "🚪 Выйти"
BTN_CANCEL = "❌ Отмена"
# legacy aliases (handlers may still match)
BTN_DIAG = "🧪 Диагностика"


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATS), KeyboardButton(text=BTN_LOGS)],
            [KeyboardButton(text=BTN_GRAPH), KeyboardButton(text=BTN_AI)],
            [KeyboardButton(text=BTN_USERS), KeyboardButton(text=BTN_SYSTEM)],
            [KeyboardButton(text=BTN_DIAG), KeyboardButton(text=BTN_EXIT)],
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
    is_whitelisted: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    rows.append(
        [
            InlineKeyboardButton(
                text="📊 Статистика пользователя",
                callback_data=f"adm:ustats:{user_id}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="📡 Каналы пользователя",
                callback_data=f"adm:uch:{user_id}",
            )
        ]
    )
    if is_whitelisted:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔐 Убрать из вайтлиста",
                    callback_data=f"adm:wlrem:{user_id}",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔐 В вайтлист",
                    callback_data=f"adm:wladd:{user_id}",
                )
            ]
        )
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
                text="🧹 Удалить аккаунт + уникальные каналы",
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
    from app.services.whitelist import WhitelistService

    svc = AdminService(session)
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(actor)
    wl = await WhitelistService(session).is_whitelisted(target.telegram_id)
    if callback.message:
        await _track(state, callback.message)
        await callback.message.edit_text(
            _user_card(target, acc),
            reply_markup=_user_actions_kb(
                target.id,
                is_banned=bool(target.is_banned),
                target_acc=acc,
                actor_is_owner=actor_owner,
                is_whitelisted=wl,
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
    from app.bot.ui.nav import drop_ui_message, remember_ui_message
    from app.bot.ui.texts import format_home

    await _purge_admin_messages(message, state)
    await state.clear()
    prefs = PreferencesService(session)
    lang = await prefs.lang(db_user)
    us = await prefs.get_or_create(db_user)
    await drop_ui_message(message.bot, session, db_user)
    text = format_home(lang, tz_name=us.timezone)
    sent = await message.answer(text, reply_markup=main_menu(lang))
    await remember_ui_message(session, db_user, sent)


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
    lines = [
        "<b>📊 Статистика</b>",
        "",
        "👥 <b>Пользователи</b>",
        f"Всего: <b>{stats['users_total']}</b> · активны за сутки: <b>{stats['users_active_today']}</b>",
        "",
        "📡 <b>Каналы</b>",
        f"Всего в БД: <b>{stats['channels']}</b>",
        f"С подписчиками: <b>{stats['channels_linked']}</b>",
        f"Без подписчиков (orphan): <b>{stats['channels_orphan']}</b>",
        "",
        "<b>Кто сколько каналов</b>",
    ]
    by_user = stats.get("channels_by_user") or []
    if not by_user:
        lines.append("— нет")
    else:
        for row in by_user:
            uname = f"@{row['username']}" if row.get("username") else "—"
            lines.append(
                f"· <code>{row['telegram_id']}</code> {uname}: <b>{row['count']}</b>"
            )
    lines.extend(
        [
            "",
            "📰 Постов: <b>{posts}</b> · 🔥 Events: <b>{events}</b>".format(**stats),
            "🤖 AI запросов: <b>{ai_requests}</b> · токены in/out: "
            "<b>{tokens_in}</b>/<b>{tokens_out}</b>".format(**stats),
            "",
            "🔐 Вайтлист: <b>{status}</b> ({n} id)".format(
                status="ВКЛ" if stats.get("whitelist_enabled") else "выкл",
                n=stats.get("whitelist_count", 0),
            ),
        ]
    )
    kb_rows: list[list[InlineKeyboardButton]] = []
    if int(stats.get("channels_orphan") or 0) > 0:
        kb_rows.append(
            [
                InlineKeyboardButton(
                    text=f"🧹 Удалить orphan-каналы ({stats['channels_orphan']})",
                    callback_data="adm:purge_orphans",
                )
            ]
        )
    await _admin_answer(
        message,
        state,
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None,
    )


@router.message(AdminAuthStates.menu, F.text == BTN_LOGS)
async def admin_logs_view(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    from html import escape as html_escape

    errors = admin_logs(limit=15, errors_only=True)
    infos = [r for r in admin_logs(limit=25) if r["level"] != "ERROR"][:15]
    lines = ["<b>📜 Логи</b>", "", "<b>Ошибки</b>"]
    if errors:
        for r in errors:
            lines.append(f"❌ {html_escape(str(r['ts']))} {html_escape(str(r['message']))}")
    else:
        lines.append("— нет")
    lines.append("")
    lines.append("<b>INFO</b>")
    if infos:
        for r in infos:
            lines.append(f"INFO: {html_escape(str(r['message']))}")
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
    from html import escape as html_escape
    from sqlalchemy import func, select, text as sql_text

    from app.models import Message as TgMessage

    snap = diagnostics_snapshot()
    redis_ok = await ping_redis()
    settings = get_settings()

    db_ok = False
    msg_count = int(snap.get("messages_total") or 0)
    try:
        await session.execute(sql_text("SELECT 1"))
        db_ok = True
        counted = await session.scalar(select(func.count()).select_from(TgMessage))
        if counted is not None:
            msg_count = int(counted)
    except Exception:
        db_ok = False

    tg_ok = True
    try:
        await message.bot.get_me()
    except Exception:
        tg_ok = False

    sched_ok = bool(snap.get("scheduler_running"))
    errs = snap.get("last_errors") or []
    err_n = int(snap.get("errors_total") or 0)

    text = (
        "<b>📊 Диагностика</b>\n\n"
        f"Bot: {'✅ Online' if tg_ok else '❌ Offline'}\n"
        f"Database: {'✅ PostgreSQL' if db_ok else '❌ PostgreSQL'}\n"
        f"Redis: {'✅ Connected' if redis_ok else '❌ Disconnected'}\n"
        f"Telegram API: {'✅ Connected' if tg_ok else '❌ Error'}\n"
        f"Scheduler: {'✅ Running' if sched_ok else '❌ Stopped'}\n\n"
        f"Последний запуск: {html_escape(str(snap.get('last_job_ago') or '—'))}\n"
        f"Количество сообщений: <b>{msg_count}</b>\n"
        f"Ошибки: <b>{err_n}</b>\n"
        f"Uptime: {html_escape(str(snap.get('uptime') or '—'))}\n"
        f"AI: {html_escape(settings.ai_provider or '—')}\n\n"
        "<b>Последняя ошибка</b>\n"
    )
    if errs:
        text += html_escape(str(errs[0]))
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
        f"Или «{BTN_CANCEL}».\n"
        f"Вайтлист: кнопка «{BTN_WHITELIST}» в меню Система."
    )
    await state.set_state(AdminAuthStates.find_user)
    await state.update_data(admin_ok=True)
    await _admin_answer(
        message,
        state,
        "\n".join(lines),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=BTN_WHITELIST)],
                [KeyboardButton(text=BTN_CANCEL)],
            ],
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
    from app.services.whitelist import WhitelistService

    wl = await WhitelistService(session).is_whitelisted(target.telegram_id)
    await _admin_answer(
        message,
        state,
        _user_card(target, acc),
        reply_markup=_user_actions_kb(
            target.id,
            is_banned=bool(target.is_banned),
            target_acc=acc,
            actor_is_owner=actor_owner,
            is_whitelisted=wl,
        ),
    )


@router.callback_query(F.data == "adm:users_back")
async def admin_users_back(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminAuthStates.find_user)
    await state.update_data(admin_ok=True)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "Пришлите Telegram ID / @username / внутренний id.\n\n"
            f"Или «{BTN_CANCEL}» в меню."
        )


@router.callback_query(F.data.startswith("adm:ustats:"))
async def admin_user_stats(
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
    stats = await svc.user_card_stats(target)
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(db_user)

    def _fmt_ts(dt) -> str:
        if dt is None:
            return "—"
        from datetime import timezone as tz

        from app.services.time_prefs import format_local

        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=tz.utc)
        return format_local(dt, "Europe/Moscow") or "—"

    _ACTION_LABELS = {
        "account_wipe_data": "🧹 Очистка данных",
        "account_wipe_full": "📡 Очистка + отвязка каналов",
        "account_wipe_purge": "🗄 Очистка + удаление каналов/аккаунта",
        "admin_ban": "🚫 Бан",
        "admin_unban": "✅ Разбан",
        "admin_soft_reset": "🔄 Soft-reset (админ)",
        "admin_full_wipe": "🧹 Full-wipe (админ)",
    }
    lines = [
        f"<b>📊 Статистика</b> {_role_emoji(acc, is_banned=bool(target.is_banned))}",
        f"Telegram: {_tg_line(target)}",
        "",
        f"📡 Каналы: <b>{stats['channels']}</b>",
        f"👁 Прочитано: <b>{stats['read']}</b>",
        f"🤖 API (AI) запросов: <b>{stats['ai_requests']}</b>",
        f"🔢 Токены: in <b>{stats['tokens_in']}</b> / out <b>{stats['tokens_out']}</b>",
    ]
    ai_ops = stats.get("ai_by_operation") or []
    if ai_ops:
        lines.append("⚙️ По операциям:")
        for op, n in ai_ops:
            lines.append(f"  · <code>{op}</code>: {n}")
    lines.extend(
        [
            f"📅 Регистрация: {_fmt_ts(stats.get('created_at'))}",
            f"🕒 Last seen: {_fmt_ts(stats.get('last_seen_at'))}",
            "",
            "<b>Последние действия</b>",
        ]
    )
    actions = stats.get("actions") or []
    if not actions:
        lines.append("— пока нет")
    else:
        for a in actions:
            label = _ACTION_LABELS.get(a["action"], a["action"])
            detail = (a.get("detail") or "").strip()
            extra = f" — {detail[:80]}" if detail else ""
            lines.append(f"• {_fmt_ts(a['ts'])} {label}{extra}")

    await callback.answer()
    if callback.message:
        from app.services.whitelist import WhitelistService

        wl = await WhitelistService(session).is_whitelisted(target.telegram_id)
        await _track(state, callback.message)
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=_user_actions_kb(
                target.id,
                is_banned=bool(target.is_banned),
                target_acc=acc,
                actor_is_owner=actor_owner,
                is_whitelisted=wl,
            ),
        )


@router.callback_query(F.data.startswith("adm:uch:"))
async def admin_user_channels(
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
    channels = await svc.list_user_channels(target)
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(db_user)
    from app.services.whitelist import WhitelistService

    wl = await WhitelistService(session).is_whitelisted(target.telegram_id)
    lines = [
        f"<b>📡 Каналы</b> {_role_emoji(acc, is_banned=bool(target.is_banned))}",
        f"Telegram: {_tg_line(target)}",
        f"Всего: <b>{len(channels)}</b>",
        "",
    ]
    if not channels:
        lines.append("— нет каналов")
    else:
        for ch in channels[:40]:
            mark = "✅" if ch["active"] else "⏸"
            handle = f"@{ch['username']}" if ch.get("username") else f"id={ch['id']}"
            title = (ch.get("title") or "—")[:40]
            lines.append(f"{mark} {handle} — {title}")
        if len(channels) > 40:
            lines.append(f"… и ещё {len(channels) - 40}")
    await callback.answer()
    if callback.message:
        await _track(state, callback.message)
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=_user_actions_kb(
                target.id,
                is_banned=bool(target.is_banned),
                target_acc=acc,
                actor_is_owner=actor_owner,
                is_whitelisted=wl,
            ),
        )


@router.callback_query(F.data == "adm:purge_orphans")
async def admin_purge_orphans(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    n = await AdminService(session).purge_orphan_channels()
    record_admin_log("INFO", f"Purged orphan channels n={n} by={db_user.id}")
    await callback.answer(f"Удалено: {n}", show_alert=True)
    if callback.message:
        stats = await AdminService(session).admin_statistics()
        await callback.message.edit_text(
            f"✅ Удалено orphan-каналов: <b>{n}</b>\n\n"
            f"Сейчас в БД: <b>{stats['channels']}</b> "
            f"(с подписчиками: {stats['channels_linked']})"
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
    from app.services.user_activity import log_user_action

    await log_user_action(session, user=target, action="admin_ban", detail=f"by={db_user.id}")
    await session.commit()
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
    from app.services.user_activity import log_user_action

    await log_user_action(session, user=target, action="admin_unban", detail=f"by={db_user.id}")
    await session.commit()
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
    from app.services.user_activity import log_user_action

    await log_user_action(
        session,
        user=target,
        action="admin_soft_reset",
        detail=f"by={db_user.id} states={stats.get('states')}",
    )
    await session.commit()
    await callback.answer("Сброшен как новый", show_alert=True)
    acc = await svc.get_account(target.id)
    actor_owner = await svc.is_owner(db_user)
    from app.services.whitelist import WhitelistService

    wl = await WhitelistService(session).is_whitelisted(target.telegram_id)
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
                is_whitelisted=wl,
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
    if target.id == db_user.id:
        await callback.answer("Нельзя удалить себя", show_alert=True)
        return
    tid = target.telegram_id
    uname = f"@{target.username}" if target.username else "—"
    from app.services.user_activity import log_user_action

    await log_user_action(
        session,
        user=target,
        action="admin_full_wipe",
        detail=f"by={db_user.id}",
    )
    stats = await svc.full_reset_user(
        target,
        purge_orphan_channels=True,
        delete_user_row=True,
    )
    record_admin_log(
        "INFO",
        f"Full-wipe user id={uid} tid={tid} purged={stats.get('purged_channels')} "
        f"deleted={stats.get('user_deleted')}",
    )
    await callback.answer("Пользователь удалён из БД", show_alert=True)
    if callback.message:
        await _track(state, callback.message)
        await callback.message.edit_text(
            f"<b>🧹 Пользователь удалён</b>\n\n"
            f"Telegram: <code>{tid}</code> {uname}\n"
            f"Отвязано каналов: <b>{stats.get('channels', 0)}</b>\n"
            f"Удалено уникальных каналов из БД: <b>{stats.get('purged_channels', 0)}</b>\n"
            f"Запись пользователя: "
            f"{'удалена' if stats.get('user_deleted') else 'сохранена'}\n\n"
            "При следующем /start аккаунт создастся заново.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 К поиску", callback_data="adm:users_back")]
                ]
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


@router.message(AdminAuthStates.menu, F.text == BTN_GRAPH)
async def admin_graph_menu(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    from sqlalchemy import func, select

    from app.models import Edge, Event, EventNode, Node
    from app.services.knowledge import get_rebuild_progress

    nodes = await session.scalar(select(func.count()).select_from(Node)) or 0
    edges = await session.scalar(select(func.count()).select_from(Edge)) or 0
    links = await session.scalar(select(func.count()).select_from(EventNode)) or 0
    active = await session.scalar(
        select(func.count()).select_from(Event).where(Event.status == "active")
    ) or 0
    merged = await session.scalar(
        select(func.count()).select_from(Event).where(Event.status == "merged")
    ) or 0
    progress = get_rebuild_progress()
    bar = _progress_bar(progress.percent)
    status_map = {
        "idle": "⏸ idle",
        "running": "🔄 running",
        "stopping": "⏹ stopping",
        "done": "✅ done",
        "error": "❌ error",
        "cancelled": "⏹ cancelled",
    }
    last = progress.finished_at or progress.started_at or "—"
    text = (
        "<b>🕸 Граф новостей</b>\n\n"
        f"Статус: <b>{status_map.get(progress.status, progress.status)}</b>\n"
        f"Последняя пересборка: <code>{last}</code>\n"
        f"{progress.message}\n\n"
        f"{bar} <b>{progress.percent}%</b>\n"
        f"Обработано: <b>{progress.processed}</b> / <b>{progress.total or '—'}</b>\n"
        f"Объединено: <b>{progress.merged}</b>\n"
        f"Уникальных событий: <b>{progress.unique_events or active}</b>\n"
        f"Дублей найдено: <b>{progress.duplicates_found}</b>\n\n"
        f"Узлов: <b>{nodes}</b>\n"
        f"Связей: <b>{edges}</b>\n"
        f"Event↔Node: <b>{links}</b>\n"
        f"Active events: <b>{active}</b>\n"
        f"Merged events: <b>{merged}</b>\n\n"
        "«Пересобрать граф» полностью очищает связи, объединяет дубли событий "
        "и строит граф заново."
    )
    rows: list[list[InlineKeyboardButton]] = []
    if progress.status == "running":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить статус",
                    callback_data="adm:kg:status",
                ),
                InlineKeyboardButton(
                    text="⏹ Остановить",
                    callback_data="adm:kg:stop",
                ),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🕸 Пересобрать граф",
                    callback_data="adm:kg:rebuild",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить статус",
                    callback_data="adm:kg:status",
                )
            ]
        )
    await _admin_answer(
        message,
        state,
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


def _progress_bar(percent: int, width: int = 10) -> str:
    p = max(0, min(100, int(percent)))
    filled = int(round(width * p / 100))
    return "█" * filled + "░" * (width - filled)


async def _graph_status_text(session: AsyncSession) -> str:
    from sqlalchemy import func, select

    from app.models import Edge, Event, EventNode, Node
    from app.services.knowledge import get_rebuild_progress

    nodes = await session.scalar(select(func.count()).select_from(Node)) or 0
    edges = await session.scalar(select(func.count()).select_from(Edge)) or 0
    links = await session.scalar(select(func.count()).select_from(EventNode)) or 0
    active = await session.scalar(
        select(func.count()).select_from(Event).where(Event.status == "active")
    ) or 0
    merged = await session.scalar(
        select(func.count()).select_from(Event).where(Event.status == "merged")
    ) or 0
    progress = get_rebuild_progress()
    bar = _progress_bar(progress.percent)
    return (
        "<b>🕸 Граф новостей</b>\n\n"
        f"Статус: <b>{progress.status}</b>\n"
        f"{progress.message}\n\n"
        f"{bar} <b>{progress.percent}%</b>\n"
        f"Обработано: <b>{progress.processed}</b> / <b>{progress.total or '—'}</b>\n"
        f"Объединено: <b>{progress.merged}</b>\n"
        f"Уникальных событий: <b>{progress.unique_events or active}</b>\n"
        f"Дублей: <b>{progress.duplicates_found}</b>\n"
        f"Связано events: <b>{progress.linked_events}</b>\n\n"
        f"Узлов: <b>{nodes}</b> · Связей: <b>{edges}</b> · Links: <b>{links}</b>\n"
        f"Active: <b>{active}</b> · Merged: <b>{merged}</b>"
    )


def _graph_keyboard() -> InlineKeyboardMarkup:
    from app.services.knowledge import get_rebuild_progress

    progress = get_rebuild_progress()
    rows: list[list[InlineKeyboardButton]] = []
    if progress.status == "running":
        rows.append(
            [
                InlineKeyboardButton(text="🔄 Статус", callback_data="adm:kg:status"),
                InlineKeyboardButton(text="⏹ Стоп", callback_data="adm:kg:stop"),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="🕸 Пересобрать граф", callback_data="adm:kg:rebuild")]
        )
        rows.append(
            [InlineKeyboardButton(text="🔄 Статус", callback_data="adm:kg:status")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "adm:kg:status")
async def admin_kg_status(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    text = await _graph_status_text(session)
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=_graph_keyboard())
        except TelegramBadRequest:
            await _admin_answer(callback.message, state, text, reply_markup=_graph_keyboard())


@router.callback_query(F.data == "adm:kg:stop")
async def admin_kg_stop(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    from app.services.knowledge import request_stop_rebuild

    ok = request_stop_rebuild()
    await callback.answer("Останавливаем…" if ok else "Не запущено", show_alert=True)
    if callback.message:
        text = await _graph_status_text(session)
        try:
            await callback.message.edit_text(text, reply_markup=_graph_keyboard())
        except TelegramBadRequest:
            pass
    record_admin_log("INFO", f"KG rebuild stop by={db_user.id}")


@router.callback_query(F.data == "adm:kg:rebuild")
async def admin_kg_rebuild(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    from app.services.knowledge import get_rebuild_progress, start_full_rebuild

    current = get_rebuild_progress()
    if current.status == "running":
        await callback.answer("Уже идёт пересборка", show_alert=True)
        return
    await callback.answer("Полная пересборка запущена…")
    await start_full_rebuild()
    record_admin_log("INFO", f"KG full rebuild started by={db_user.id}")
    text = await _graph_status_text(session)
    if callback.message:
        try:
            await callback.message.edit_text(text, reply_markup=_graph_keyboard())
        except TelegramBadRequest:
            await _admin_answer(callback.message, state, text, reply_markup=_graph_keyboard())


@router.message(AdminAuthStates.menu, F.text == BTN_AI)
async def admin_ai_menu(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    from sqlalchemy import func, select

    from app.models import AiUsageLog
    from app.services.ai import get_ai_manager, reset_ai_service_cache
    from app.services.queue import queue_depth

    reset_ai_service_cache()
    mgr = get_ai_manager()
    snap = mgr.status_snapshot() if mgr else {"groq_keys": 0, "kimi_keys": 0, "groq_available": 0, "kimi_available": 0}
    depth = await queue_depth(session)
    ai_n = await session.scalar(select(func.count()).select_from(AiUsageLog)) or 0
    tok_in = await session.scalar(
        select(func.coalesce(func.sum(AiUsageLog.tokens_in), 0))
    ) or 0
    tok_out = await session.scalar(
        select(func.coalesce(func.sum(AiUsageLog.tokens_out), 0))
    ) or 0
    settings = get_settings()
    text = (
        "<b>🤖 AI настройки</b>\n\n"
        f"Режим: <code>{settings.ai_provider}</code>\n"
        f"Groq ключей: <b>{snap.get('groq_keys', 0)}</b> "
        f"(доступно {snap.get('groq_available', 0)})\n"
        f"Kimi ключей: <b>{snap.get('kimi_keys', 0)}</b> "
        f"(доступно {snap.get('kimi_available', 0)})\n"
        f"Очередь AI: queued <b>{depth['queued']}</b> · running <b>{depth['running']}</b>\n\n"
        f"Запросов в логе: <b>{ai_n}</b>\n"
        f"Токены: in <b>{tok_in}</b> / out <b>{tok_out}</b>\n\n"
        "Ключи задаются в ENV: <code>GROQ_API_KEYS</code>, <code>KIMI_API_KEYS</code>."
    )
    await _admin_answer(message, state, text)


@router.message(AdminAuthStates.menu, F.text == BTN_SYSTEM)
async def admin_system_menu(
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
    text = (
        "<b>⚙️ Система</b>\n\n"
        f"Uptime: {snap.get('uptime')}\n"
        f"Redis: {'✅' if redis_ok else '❌'}\n"
        f"AI provider: {settings.ai_provider or '—'}\n"
        f"Ingest: +{ingest.get('created_messages', '—')} msgs / "
        f"{ingest.get('processed', '—')} processed\n"
    )
    await _admin_answer(
        message,
        state,
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🌙 Запустить nightly",
                        callback_data="adm:sys:nightly",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🧹 Orphan-каналы",
                        callback_data="adm:purge_orphans",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔐 Вайтлист",
                        callback_data="adm:sys:wl",
                    )
                ],
            ]
        ),
    )
    # Also offer reply shortcuts (must be tracked for exit cleanup)
    extra = await message.answer(
        "Дополнительно:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=BTN_WHITELIST), KeyboardButton(text=BTN_PASSWORD)],
                [KeyboardButton(text=BTN_DIAG), KeyboardButton(text="🔙 Админ-меню")],
            ],
            resize_keyboard=True,
        ),
    )
    await _track(state, extra)


@router.message(AdminAuthStates.menu, F.text == "🔙 Админ-меню")
async def admin_back_main(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    await _admin_answer(message, state, "🛠 Админ-меню:", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "adm:sys:nightly")
async def admin_sys_nightly(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer("Nightly…")
    from app.tasks.pipeline import run_nightly_maintenance

    stats = await run_nightly_maintenance()
    record_admin_log("INFO", f"Manual nightly by={db_user.id} {stats}")
    if callback.message:
        lines = ["<b>🌙 Nightly выполнен</b>", ""]
        for k, v in stats.items():
            lines.append(f"{k}: <b>{v}</b>")
        await callback.message.edit_text("\n".join(lines))


@router.callback_query(F.data == "adm:sys:wl")
async def admin_sys_wl(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.answer()
    # Reuse whitelist menu text via fake message path
    if callback.message:
        from app.services.whitelist import WhitelistService

        wl = WhitelistService(session)
        enabled = await wl.is_whitelist_enabled()
        entries = await wl.list_entries(limit=20)
        lines = [
            f"<b>🔐 Вайтлист</b> — {'ВКЛ' if enabled else 'выкл'}",
            f"Записей: {len(entries)}",
        ]
        for e in entries[:15]:
            lines.append(f"· <code>{e.telegram_id}</code>")
        await callback.message.answer(
            "\n".join(lines) + f"\n\nОткройте «{BTN_WHITELIST}» в reply-меню для управления."
        )


@router.message(AdminAuthStates.find_user, F.text == BTN_WHITELIST)
@router.message(AdminAuthStates.menu, F.text == BTN_WHITELIST)
async def admin_whitelist_menu(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    from app.services.whitelist import WhitelistService

    wl = WhitelistService(session)
    enabled = await wl.is_whitelist_enabled()
    entries = await wl.list_entries(limit=30)
    lines = [
        "<b>🔐 Вайтлист</b>",
        "",
        f"Режим: <b>{'ВКЛЮЧЁН' if enabled else 'выключен'}</b>",
        "Когда включён — ботом могут пользоваться только ID из списка,",
        "админы и ID из ADMIN_TELEGRAM_IDS.",
        "",
        f"Записей: <b>{len(entries)}</b>",
    ]
    if entries:
        lines.append("")
        for e in entries:
            note = f" — {e.note}" if e.note else ""
            lines.append(f"· <code>{e.telegram_id}</code>{note}")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🟢 Включить" if not enabled else "🔴 Выключить",
                    callback_data="adm:wl:toggle",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить Telegram ID",
                    callback_data="adm:wl:ask",
                )
            ],
        ]
    )
    await _admin_answer(message, state, "\n".join(lines), reply_markup=kb)


@router.callback_query(F.data == "adm:wl:toggle")
async def admin_wl_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    from app.services.whitelist import WhitelistService

    wl = WhitelistService(session)
    enabled = await wl.is_whitelist_enabled()
    await wl.set_whitelist_enabled(not enabled)
    # When enabling, auto-add current admins + env admins
    if not enabled:
        from app.config import get_settings

        for tid in get_settings().admin_id_set():
            await wl.add(tid, note="env admin")
        for _acc, u in await AdminService(session).list_admins():
            await wl.add(u.telegram_id, note="admin")
        await wl.add(db_user.telegram_id, note="self")
    record_admin_log(
        "INFO",
        f"Whitelist {'ON' if not enabled else 'OFF'} by={db_user.id}",
    )
    await callback.answer("Вайтлист " + ("ВКЛ" if not enabled else "выкл"), show_alert=True)
    if callback.message:
        enabled2 = await wl.is_whitelist_enabled()
        entries = await wl.list_entries(limit=30)
        lines = [
            "<b>🔐 Вайтлист</b>",
            "",
            f"Режим: <b>{'ВКЛЮЧЁН' if enabled2 else 'выключен'}</b>",
            f"Записей: <b>{len(entries)}</b>",
        ]
        for e in entries:
            note = f" — {e.note}" if e.note else ""
            lines.append(f"· <code>{e.telegram_id}</code>{note}")
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🟢 Включить" if not enabled2 else "🔴 Выключить",
                            callback_data="adm:wl:toggle",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="➕ Добавить Telegram ID",
                            callback_data="adm:wl:ask",
                        )
                    ],
                ]
            ),
        )


@router.callback_query(F.data == "adm:wl:ask")
async def admin_wl_ask(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(AdminAuthStates.whitelist_add)
    await state.update_data(admin_ok=True)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "Пришлите Telegram ID (число) или @username существующего пользователя.\n"
            f"Или «{BTN_CANCEL}».",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
                resize_keyboard=True,
            ),
        )


@router.message(AdminAuthStates.whitelist_add, F.text == BTN_CANCEL)
async def admin_wl_add_cancel(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True)
    await _admin_answer(message, state, "Отменено.", reply_markup=admin_menu_keyboard())


@router.message(AdminAuthStates.whitelist_add, F.text, ~F.text.startswith("/"))
async def admin_wl_add_save(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        raise SkipHandler()
    from app.services.whitelist import WhitelistService

    raw = (message.text or "").strip().lstrip("@")
    tid: int | None = None
    note = ""
    if raw.isdigit():
        tid = int(raw)
    else:
        svc = AdminService(session)
        u = await svc.find_user(raw)
        if u:
            tid = int(u.telegram_id)
            note = u.username or ""
    if tid is None:
        await _admin_answer(message, state, "Не понял ID. Пришлите число или @username.")
        return
    await WhitelistService(session).add(tid, note=note)
    record_admin_log("INFO", f"Whitelist add tid={tid} by={db_user.id}")
    await state.set_state(AdminAuthStates.menu)
    await state.update_data(admin_ok=True)
    await _admin_answer(
        message,
        state,
        f"✅ Добавлен в вайтлист: <code>{tid}</code>",
        reply_markup=admin_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("adm:wladd:"))
async def admin_wl_add_user(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    from app.services.whitelist import WhitelistService

    await WhitelistService(session).add(
        target.telegram_id, note=target.username or f"user#{target.id}"
    )
    record_admin_log("INFO", f"Whitelist add user id={uid} by={db_user.id}")
    await callback.answer("В вайтлисте", show_alert=True)
    await _refresh_user_card(callback, session, state, target, db_user)


@router.callback_query(F.data.startswith("adm:wlrem:"))
async def admin_wl_rem_user(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    if not await _require_admin(session, db_user, state):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int((callback.data or "").split(":")[2])
    target = (await session.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not target:
        await callback.answer("Не найден", show_alert=True)
        return
    from app.services.whitelist import WhitelistService

    await WhitelistService(session).remove(target.telegram_id)
    record_admin_log("INFO", f"Whitelist remove user id={uid} by={db_user.id}")
    await callback.answer("Убран из вайтлиста", show_alert=True)
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
