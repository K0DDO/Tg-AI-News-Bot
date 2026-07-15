from aiogram import Router

from app.bot.handlers import (
    admin,
    admin_panel,
    channels,
    home,
    library,
    news,
    search,
    settings,
    trends,
)


def setup_routers() -> Router:
    root = Router()
    root.include_router(admin_panel.router)
    root.include_router(admin.router)
    root.include_router(home.router)
    root.include_router(news.router)
    root.include_router(search.router)
    root.include_router(channels.router)
    root.include_router(settings.router)
    root.include_router(trends.router)
    root.include_router(library.router)
    return root
