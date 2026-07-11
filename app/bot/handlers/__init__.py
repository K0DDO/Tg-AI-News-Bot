from aiogram import Router

from app.bot.handlers import channels, digest, search, start


def setup_routers() -> Router:
    root = Router()
    root.include_router(start.router)
    root.include_router(digest.router)
    root.include_router(search.router)
    root.include_router(channels.router)
    return root
