# Briefly

Умный новостной сервис для Telegram: читает ваши каналы, убирает шум,
объединяет дубли и показывает только то, что важно — в персональной **Ленте**.

Продукт ощущается как Notion / Perplexity / Telegram Premium: минимум текста, максимум смысла.
Обработка «под капотом» скрыта от пользователя.

## Что умеет

- **Лента** — непрочитанные новости; после открытия больше не повторяются (кроме сильного роста источников/рейтинга)
- **Поиск** — ответ + источники (строгая релевантность, без выдумок); периоды: сегодня / неделя / месяц
- **В тренде** — темы (Topic), а не «популярные слова»
- **Избранное** и **История** (фильтр по дате + поиск)
- **Локализация** — RU / EN / DE / ES (интерфейс + заголовок/summary)
- **Живые обновления** — новая информация по событию обновляет существующую карточку (`📈 Обновлено`)

## Архитектура обработки

```
Telegram message
    → rule filter
    → local embedding + cosine merge
    → дубль: NewsSource + rescore (без LLM)
    → новая: analyze (topic, why, category, score)
    → News сохраняется
```

Провайдер абстрагирован (`AI_PROVIDER=groq|heuristic`). Embeddings по умолчанию: **hashing** (VPS ~2GB).

## Быстрый старт

```bash
copy .env.example .env
```

Заполни: `BOT_TOKEN`, `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`, `GROQ_API_KEY` (опционально),
`ADMIN_USERNAME` / `ADMIN_PASSWORD`.

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/auth_telethon.py
alembic upgrade head
```

Три процесса (или Docker):

```bash
uvicorn app.api.main:app --host 127.0.0.1 --port 8000
python -m app.bot.main
python -m app.tasks.worker
```

## Меню бота

Лента · Поиск · Каналы · Настройки · В тренде · Избранное · История

## Переменные

| Переменная | Описание |
|------------|----------|
| `AI_PROVIDER` | `groq` или `heuristic` |
| `GROQ_API_KEY` | ключ Groq |
| `GROQ_MODEL` | по умолчанию `llama-3.1-8b-instant` |
| `AI_SEARCH_SYNTHESIS` | синтез ответа в поиске |
| `EMBEDDING_BACKEND` | `hashing` / `sentence-transformers` / `auto` |
| `CLUSTER_SIMILARITY_THRESHOLD` | порог merge |

## Тесты

```bash
pytest -q
```
