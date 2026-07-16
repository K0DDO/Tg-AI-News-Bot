# Briefly 

Умный новостной сервис для Telegram. Пользователь работает с **событиями (Event)**,
а не с отдельными Telegram-постами.

Финальный продукт — Telegram-бот. Production — Docker Compose на Linux VPS
(рядом с Amnezia VPN: **не** менять iptables / VPN / чужие контейнеры).

## Конфиг на сервере

Единственный шаблон: `.env.production.example` → копируете в `.env.production` на VPS.

`DATABASE_URL` можно не задавать — соберётся из `POSTGRES_*`.
Compose подставляет `postgres` / `redis` и путь сессии в volume.

Секреты только в `.env.production` на диске — **не** в коде и **не** в git.

---

## Production (Linux VPS + Docker Compose)

Требования: Ubuntu 24.04, Docker + Compose V2. Старая установка удалена → чистая БД при первом `alembic upgrade` в entrypoint.

```bash
sudo mkdir -p /opt/briefly && sudo chown "$USER":"$USER" /opt/briefly
cd /opt/briefly
git clone <repo-url> .
cp .env.production.example .env.production
# Заполнить секреты (BOT_TOKEN, TELEGRAM_API_*, GROQ/Kimi, пароли, ADMIN_TELEGRAM_IDS)

mkdir -p data/sessions logs backups postgres redis
./scripts/check_vps.sh

# Один раз: Telethon session (персистится в ./data/sessions через volume)
docker compose --env-file .env.production run --rm -it briefly-app python scripts/auth_telethon.py

docker compose --env-file .env.production up -d --build
docker compose --env-file .env.production logs -f briefly-app
```

Entrypoint: ждёт Postgres → `alembic upgrade head` → `python -m app.runtime`.

Админы: `ADMIN_TELEGRAM_IDS=111,222` — только числовые Telegram ID (не username).

Бэкапы:

```bash
crontab -e
# 15 3 * * * cd /opt/briefly && ./scripts/backup_postgres.sh >> logs/backup.log 2>&1
```

Деплой: GitHub Actions (только `/opt/briefly`) или вручную `./scripts/deploy.sh`.  
Инструкция: [docs/DEPLOY.md](docs/DEPLOY.md).

Контейнеры (сеть `briefly_net`, **без** host network, порты PG/Redis **не** наружу):

| Контейнер | Роль | Volumes |
|-----------|------|---------|
| `briefly-app` | bot + parser + scheduler | sessions, logs, backups |
| `postgres` | PostgreSQL | `./postgres` |
| `redis` | FSM / cache | `./redis` |

Graceful shutdown: SIGTERM → stop polling + scheduler; Telethon disconnect на каждый ingest; jobs обёрнуты, падение одного цикла не роняет процесс.

---

## Переменные окружения

Полный список — в `.env.production.example`. Ключевые:

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен Telegram Bot API |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | my.telegram.org для Telethon |
| `ADMIN_TELEGRAM_IDS` | Числовые Telegram ID админов через запятую |
| `POSTGRES_*` | Учётка БД; `POSTGRES_HOST=postgres` в compose |
| `GROQ_API_KEYS` / `KIMI_API_KEYS` | Пулы ключей AI (через запятую) |
| `ADMIN_PASSWORD` / `ADMIN_SECRET_KEY` | Bootstrap `/admin` |
| `BRIEFLY_ENV_FILE` / `ENV_FILE` | Явный путь к env-файлу (опционально) |

---

## Архитектура данных

```
TelegramPost (messages)  →  Event (events)  →  Brief (карточка в боте)
```

## Тесты

```bash
pytest -q
```
