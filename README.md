# Telegram News Aggregator (AI)

Personal AI News Assistant: читает Telegram-каналы, фильтрует мусор, объединяет дубли,
делает AI-саммари через **Groq** (или heuristic fallback), отдаёт дайджесты в боте.

Архитектура готова к multi-user / рекомендациям / тарифам позже — без Stripe и регистрации сейчас.

## AI-архитектура

```
Telegram message
    → rule filter (бесплатно)
    → local embedding + cosine merge (бесплатно)
    → если дубль: NewsSource + rescore (без Groq)
    → если новая: AIService.analyze_message (Groq)
    → News + embedding сохраняются
```

Провайдер абстрагирован:

- `app/services/ai/base.py` — интерфейс `AIService`
- `app/services/ai/groq_service.py` — Groq
- `app/services/ai/heuristic.py` — fallback без API
- `AI_PROVIDER=groq|heuristic` — смена без переписывания пайплайна

Позже можно добавить OpenAI / Gemini / Claude / DeepSeek тем же интерфейсом.

Embeddings по умолчанию: **HashingEmbedding** (`EMBEDDING_BACKEND=hashing`) — подходит для VPS 2GB.
Опционально: `sentence-transformers` (тяжёлый).

## Быстрый старт

```bash
copy .env.example .env
```

Заполни:

- `BOT_TOKEN`
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`
- `GROQ_API_KEY` (https://console.groq.com)
- `AI_PROVIDER=groq`
- `ADMIN_USERNAME` / `ADMIN_PASSWORD`

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/auth_telethon.py
alembic upgrade head
docker compose up --build
```

Или без Docker — три процесса: `uvicorn app.api.main:app`, `python -m app.bot.main`, `python -m app.tasks.worker`.

## Сервисы Docker

| Сервис | Роль |
|--------|------|
| `postgres` | БД |
| `migrate` | Alembic |
| `api` | админка :8000 |
| `bot` | aiogram |
| `worker` | Telethon + AI pipeline |

Redis пока не нужен (можно добавить для очередей позже).

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | регистрация пользователя |
| `/digest` | топ новостей + реакции |
| `/daily` | топ за 24 часа по importance |
| `/search` | semantic search + AI-ответ |
| `/channels` | каналы |

## Переменные окружения (AI)

| Переменная | Описание |
|------------|----------|
| `AI_PROVIDER` | `groq` или `heuristic` |
| `GROQ_API_KEY` | ключ Groq |
| `GROQ_MODEL` | по умолчанию `llama-3.1-8b-instant` |
| `AI_SEARCH_SYNTHESIS` | AI-ответ в `/search` |
| `EMBEDDING_BACKEND` | `hashing` / `sentence-transformers` / `auto` |
| `CLUSTER_SIMILARITY_THRESHOLD` | порог merge (0.75) |

## Экономия Groq

Не каждое сообщение идёт в API:

1. Regex/keyword filter  
2. Cosine merge похожих → без AI  
3. Groq только для **новых** кластеров и (опционально) AI-поиска  

## Структура

```
app/services/ai/       # AIService + Groq + heuristic
app/services/digest/   # NewsService pipeline
app/services/search/   # semantic + keyword
app/bot/handlers/      # digest, daily, search, channels
```

## Тесты

```bash
pytest -q
```

## Дальше

- Персональные рекомендации по `Reaction`
- pgvector для большого корпуса
- Другие AI-провайдеры через `AIService`
- Подписки / квоты (когда будете готовы к SaaS)
