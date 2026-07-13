# Briefly

Умный новостной сервис для Telegram. Пользователь работает с **событиями (Event)**,
а не с отдельными Telegram-постами.

## Архитектура (3 уровня)

```
TelegramPost (messages)     — сырой источник
        ↓ pipeline
Event (events)              — каноническое событие + timeline + entities
        ↓ BriefBuilder
Brief (view-model)          — карточка в ленте / поиске / трендах
```

Поиск, тренды и рекомендации работают **только по Event Index**.

## Pipeline

```
TelegramPost
  → language + rule/ad filter
  → (create) one AI analyze_post  OR  (merge) no LLM
  → embedding + EventMerge
  → Event + timeline + EventSource
  → Brief on read
```

Принцип: **один раз проанализировал — много раз использовал**.

## Сервисы

| Сервис | Роль |
|--------|------|
| `EventPipeline` | оркестратор |
| `EventIndexService` | кандидаты поиска/трендов |
| `SearchService` | строгий поиск по Event |
| `TrendsService` | топ Event-карточек |
| `BriefBuilderService` | UX-представление |
| `AIService` | единственная точка к Groq |

## Быстрый старт

```bash
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/auth_telethon.py
alembic upgrade head
```

Процессы: `uvicorn app.api.main:app`, `python -m app.bot.main`, `python -m app.tasks.worker`.

## Тесты

```bash
pytest -q
```
