"""FastAPI admin application."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import admin

app = FastAPI(
    title="TG News Aggregator Admin",
    version="0.1.0",
    docs_url="/docs",
)

app.include_router(admin.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    return app
