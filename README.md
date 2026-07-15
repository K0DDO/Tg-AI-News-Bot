# Briefly

Умный новостной сервис для Telegram. Пользователь работает с **событиями (Event)**,
а не с отдельными Telegram-постами.

Финальный продукт — Telegram-бот. Production — Docker Compose на Linux VPS
(рядом с Amnezia VPN: **не** менять iptables / VPN / чужие контейнеры).

## Режимы окружения

| Режим | Файл | `APP_ENV` | `POSTGRES_HOST` | Session dir |
|-------|------|-----------|-----------------|-------------|
| Local (Windows) | `.env.local` | `development` | `localhost` | `./data/sessions` |
| Production (VPS) | `.env.production` | `production` | `postgres` | `/app/data/sessions` |

`DATABASE_URL` можно не задавать — соберётся из `POSTGRES_*`.
Compose для app принудительно подставляет `postgres` / `redis` и путь сессии в volume.

Секреты только в `.env*` на диске — **не** в коде и **не** в git.

---

## 1. Локальный запуск (Windows)

```powershell
cd "путь\к\Tg Ai News Bot"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

copy .env.local.example .env.local
# Заполнить: BOT_TOKEN, TELEGRAM_API_*, GROQ_API_KEY, ADMIN_TELEGRAM_IDS, POSTGRES_*

# PostgreSQL должен быть доступен на localhost (локальный Postgres или свой docker только для dev)
alembic upgrade head

# Один раз: авторизация Telethon (файл .session в data/sessions)
python scripts/auth_telethon.py

# Бот + scheduler в одном процессе
python -m app.runtime
```

Альтернатива двумя процессами: `python -m app.bot.main` и `python -m app.tasks.worker`.

Redis на localhost опционален: если недоступен, FSM использует MemoryStorage.

Админы: `ADMIN_TELEGRAM_IDS=111,222` — только числовые Telegram ID (не username).
Команда `/status` — только для этих ID (и учёток OWNER/ADMIN в БД).

---

## 2. Production (Linux VPS + Docker Compose)

Требования: Ubuntu 24.04, Docker + Compose V2. Старая установка удалена → чистая БД при первом `alembic upgrade` в entrypoint.

```bash
sudo mkdir -p /opt/briefly && sudo chown "$USER":"$USER" /opt/briefly
cd /opt/briefly
git clone <repo-url> .
cp .env.production.example .env.production
# Заполнить секреты production (другой BOT_TOKEN / GROQ / пароли / ADMIN_TELEGRAM_IDS)

mkdir -p data/sessions logs backups postgres redis
./scripts/check_vps.sh

# Один раз: Telethon session (персистится в ./data/sessions через volume)
docker compose --env-file .env.production run --rm -it briefly-app python scripts/auth_telethon.py

docker compose --env-file .env.production up -d --build
docker compose --env-file .env.production logs -f briefly-app
```

Entrypoint: ждёт Postgres → `alembic upgrade head` (пустая схема на чистом volume) → `python -m app.runtime`.

Бэкапы:

```bash
crontab -e
# 15 3 * * * cd /opt/briefly && ./scripts/backup_postgres.sh >> logs/backup.log 2>&1
```

Деплой: GitHub Actions (только `/opt/briefly`) или вручную `./scripts/deploy.sh`.  
Инструкция по пользователю `deploy`, SSH и Secrets: [docs/DEPLOY.md](docs/DEPLOY.md).

Контейнеры (сеть `briefly_net`, **без** host network, порты PG/Redis **не** наружу):

| Контейнер | Роль | Volumes |
|-----------|------|---------|
| `briefly-app` | bot + parser + scheduler | sessions, logs, backups |
| `postgres` | PostgreSQL | `./postgres` |
| `redis` | FSM / cache | `./redis` |

Graceful shutdown: SIGTERM → stop polling + scheduler; Telethon disconnect на каждый ingest; jobs обёрнуты, падение одного цикла не роняет процесс.

---

## 3. Переменные окружения

### Обязательные

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен Telegram Bot API |
| `TELEGRAM_API_ID` | API ID (my.telegram.org) для Telethon |
| `TELEGRAM_API_HASH` | API hash для Telethon |
| `ADMIN_TELEGRAM_IDS` | Список числовых Telegram ID админов через запятую |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Учётка PostgreSQL |
| `POSTGRES_HOST` | `localhost` (local) или `postgres` (compose) |
| `POSTGRES_PORT` | Обычно `5432` |

Для production compose также обязателен сильный `POSTGRES_PASSWORD` в `.env.production`.

### Настоятельно рекомендуемые

| Переменная | Описание |
|------------|----------|
| `OWNER_TELEGRAM_ID` | OWNER для `/admin`; если пусто — первый из `ADMIN_TELEGRAM_IDS` |
| `GROQ_API_KEY` | Если `AI_PROVIDER=groq` |
| `TELEGRAM_SESSION_NAME` | Имя файла сессии (по умолчанию `news_parser`) |
| `TELEGRAM_SESSION_DIR` | `./data/sessions` / `/app/data/sessions` |
| `REDIS_URL` | Local или `redis://redis:6379/0` в Docker |
| `ADMIN_PASSWORD` / `ADMIN_SECRET_KEY` | Пароли `/admin` bootstrap |

### Необязательные / тюнинг

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `APP_ENV` | `development` | `development` \| `production` |
| `APP_DEBUG` | `false` | Отладка |
| `LOG_LEVEL` | `INFO` | Уровень логов |
| `LOGS_DIR` | `./data/logs` / `/app/logs` | Каталог rotating-логов |
| `DATABASE_URL` | *(из POSTGRES_*)* | Явный async URL; иначе сборка автоматически |
| `PARSER_POLL_INTERVAL_SECONDS` | `120` | Интервал парсера |
| `CLUSTER_*` | — | Пороги кластеризации событий |
| `DIGEST_*` / `DAILY_DIGEST_LIMIT` | — | Лимиты дайджестов |
| `MESSAGE_RETENTION_DAYS` | `31` | Retention сырых постов |
| `EMBEDDING_BACKEND` | `hashing` | На 2 GB VPS только `hashing` |
| `AI_PROVIDER` | `heuristic` | `heuristic` \| `groq` |
| `GROQ_MODEL` / `GROQ_BASE_URL` / `GROQ_TIMEOUT_SECONDS` | — | Groq |
| `AI_SEARCH_SYNTHESIS` | `true` | Синтез поиска через AI |
| `BRIEFLY_ENV_FILE` / `ENV_FILE` | — | Явный путь к env-файлу |

---

## Архитектура данных

```
TelegramPost (messages)  →  Event (events)  →  Brief (карточка в боте)
```

## Тесты

```bash
pytest -q
```
