# Production deploy (VPS + GitHub Actions)

Этот документ описывает безопасный деплой **только** Briefly на общем VPS
рядом с Amnezia VPN и `/opt/moex-bot`. CI не трогает другие проекты.

## Secrets в GitHub

Repository → **Settings → Secrets and variables → Actions**:

| Secret | Значение |
|--------|----------|
| `VPS_HOST` | IP VPS, например `123.123.123.123` |
| `VPS_USER` | `deploy` |
| `VPS_SSH_KEY` | Приватный ключ (целиком, включая `BEGIN`/`END`) |

Не коммитьте ключ и `.env.production`. Не вставляйте секреты в issue/PR.

---

## 1. Создать пользователя `deploy` (один раз, под root)

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo mkdir -p /opt/briefly
sudo chown -R deploy:deploy /opt/briefly
```

Проверка Docker без sudo:

```bash
sudo -u deploy docker ps
```

---

## 2. SSH-ключ только для Deploy

На **локальной** машине (или в CI prep):

```bash
ssh-keygen -t ed25519 -f briefly-deploy -C "github-actions-briefly" -N ""
```

На VPS:

```bash
sudo mkdir -p /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo tee /home/deploy/.ssh/authorized_keys < briefly-deploy.pub
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

Отключить парольный вход для `deploy` (ключ уже в `authorized_keys`):

```bash
# В /etc/ssh/sshd_config (или drop-in): пароли можно оставить глобально,
# но для deploy достаточно отсутствия пароля у пользователя
# (adduser --disabled-password) + вход только по ключу.
sudo systemctl reload ssh
```

---

## 3. Добавить приватный ключ в GitHub Secrets

1. Откройте содержимое **приватного** файла `briefly-deploy` (не `.pub`).
2. GitHub → Secrets → New repository secret → имя `VPS_SSH_KEY`.
3. Вставьте весь приватный ключ.
4. Удалите локальную копию приватного ключа с рабочей машины, если она больше не нужна; публичный ключ остаётся на сервере.

Никогда не печатайте `VPS_SSH_KEY` в workflow (`echo`, `cat`, debug).

---

## 4. Проверить SSH

```bash
ssh -i briefly-deploy deploy@VPS_HOST 'whoami; pwd; docker ps --format "{{.Names}}" | head'
```

Ожидается:

- `whoami` → `deploy`
- доступ к Docker
- в списке могут быть чужие контейнеры (Amnezia и т.д.) — **не останавливайте их**

Проверка, что деплой ограничен каталогом:

```bash
ssh -i briefly-deploy deploy@VPS_HOST 'cd /opt/briefly && ls docker-compose.yml Dockerfile'
```

---

## 5. Первый раз Bootstrap Briefly

Под `deploy`:

```bash
cd /opt/briefly
git clone <repo-url> .
cp .env.production.example .env.production
# заполнить секреты вручную (nano/vim) — файл не в git
mkdir -p data/sessions logs backups postgres redis
docker compose --env-file .env.production run --rm -it briefly-app python scripts/auth_telethon.py
docker compose --env-file .env.production up -d --build
```

---

## 6. Запуск Deploy из GitHub

**Actions → Deploy Briefly → Run workflow** (`workflow_dispatch`),  
или push в `main`.

Цепочка на сервере:

1. `whoami` = `deploy`, `cd /opt/briefly`
2. проверка `docker-compose.yml`, `Dockerfile`, `.env.production`
3. `git pull` (`.env.production` не меняется)
4. `docker compose config`
5. backup PostgreSQL → `backups/predeploy_*.sql`
6. `docker compose build briefly-app` (только app)
7. `alembic upgrade head`
8. `docker compose up -d briefly-app` (**без** `compose down`)
9. health: postgres/redis `healthy`, app `running`

При провале старта/health — rollback образа `briefly-app` на предыдущий tag.

---

## Запрещено в CI / скриптах

- `docker compose down` (особенно вне проекта)
- `docker system prune`, удаление чужих volumes/images
- изменение iptables / firewall / сети
- любые команды в `/opt/moex-bot` или с Amnezia-контейнерами
- `systemctl` чужих сервисов
- вывод `.env.production`, токенов, ключей

Работа только внутри `/opt/briefly` и только с compose-проектом `briefly`.
