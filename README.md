# Briefly

Умный новостной сервис для Telegram. Пользователь работает с **событиями (Event)**,
а не с отдельными Telegram-постами.

Финальный продукт — Telegram-бот. Web UI / мобильное приложение / публичный REST API
**не развиваются**. Production — Docker Compose на Linux VPS (2 GB RAM) рядом с Amnezia VPN.

## Архитектура данных

```
TelegramPost (messages)     — сырой источник
        ↓ pipeline
Event (events)              — каноническое событие + timeline + entities
        ↓ BriefBuilder
Brief (view-model)          — карточка в ленте / поиске / трендах
```

## Production (VPS)

Структура на сервере:

```
/opt/briefly/
  docker-compose.yml
  .env
  app/
  scripts/
  logs/
  backups/
  postgres/          # PG data (bind mount)
  redis/             # Redis data (bind mount)
  data/sessions/     # Telethon session
```

Контейнеры (своя Docker-сеть, **без host network**, порты БД/Redis **не** публикуются):

| Контейнер | Роль |
|-----------|------|
| `briefly-app` | Bot (long polling) + Parser + Scheduler + Events + Search + KG |
| `postgres` | PostgreSQL |
| `redis` | FSM + краткий кэш |
| `watchtower` | опционально: `docker compose --profile ops up -d` |

**Amnezia VPN не трогать:** скрипты не меняют iptables / VPN / чужие порты.

### Установка

```bash
# на VPS
sudo mkdir -p /opt/briefly && sudo chown "$USER":"$USER" /opt/briefly
cd /opt/briefly
git clone <repo-url> .
cp .env.example .env   # заполнить секреты
./scripts/check_vps.sh
# Один раз авторизовать Telethon (сессия в data/sessions):
docker compose run --rm -it briefly-app python scripts/auth_telethon.py
docker compose up -d --build
# бэкапы каждую ночь
crontab -e   # 15 3 * * * cd /opt/briefly && ./scripts/backup_postgres.sh >> logs/backup.log 2>&1
```

Деплой после `git push`: GitHub Action SSH → `/opt/briefly/scripts/deploy.sh`  
(секреты: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`).

Админ-команда в боте: `/status` (нужен `ADMIN_TELEGRAM_IDS` в `.env`).

Логи (ротация): `logs/bot.log`, `parser.log`, `search.log`, `graph.log`, `scheduler.log`, `errors.log`.

Память: держать `EMBEDDING_BACKEND=hashing`. Не включать sentence-transformers на 2 GB.

## Local (Windows / разработка)

```bash
copy .env.example .env
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/auth_telethon.py
alembic upgrade head
```

Процессы (локально):

- `python -m app.runtime` — бот + scheduler в одном процессе
- или отдельно: `python -m app.bot.main` и `python -m app.tasks.worker`
- опционально админ-панель: `uvicorn app.api.main:app --port 8000`

## Тесты

```bash
pytest -q
```
