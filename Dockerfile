FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/data/hf_cache \
    LOGS_DIR=/app/logs \
    TELEGRAM_SESSION_DIR=/app/data/sessions

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 briefly \
    && useradd --uid 1000 --gid briefly --shell /bin/sh --create-home briefly

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY locales ./locales
COPY scripts ./scripts

RUN mkdir -p /app/data/sessions /app/data/hf_cache /app/logs /app/backups \
    && chmod +x /app/scripts/entrypoint.sh /app/scripts/backup_postgres.sh /app/scripts/check_vps.sh /app/scripts/deploy.sh /app/scripts/ci_deploy.sh \
    && chown -R briefly:briefly /app

USER briefly

# No ports published — Telegram long polling only.
CMD ["sh", "/app/scripts/entrypoint.sh"]
