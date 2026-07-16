"""Telegram admin panel (/admin) — compact: Stats / Logs / Diagnostics."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove
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
BTN_EXIT = "🚪 Выйти"


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATS)],
            [KeyboardButton(text=BTN_LOGS), KeyboardButton(text=BTN_DIAG)],
            [KeyboardButton(text=BTN_EXIT)],
        ],
        resize_keyboard=True,
    )


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
    await state.update_data(admin_ok=True)
    ok = await message.answer("🛠 Админ-меню:", reply_markup=admin_menu_keyboard())
    # Delete ephemeral "password saved" quickly by editing? Keep menu.
    record_admin_log("INFO", f"Admin login uid={db_user.id}")
    _ = ok


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


@router.message(StateFilter(AdminAuthStates.menu))
async def admin_menu_fallback(message: Message) -> None:
    await message.answer("Выберите: Статистика · Логи · Диагностика · Выйти")
