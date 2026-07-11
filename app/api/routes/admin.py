from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.services.channels import ChannelService
from app.services.stats import StatsService

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    stats = await StatsService(session).snapshot()
    channels = await ChannelService(session).list_all_channels()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"stats": stats, "channels": channels},
    )


@router.post("/channels/add")
async def add_channel(
    telegram_id: int = Form(...),
    title: str = Form(...),
    username: str = Form(""),
    session: AsyncSession = Depends(get_db_session),
):
    service = ChannelService(session)
    await service.upsert_channel(
        telegram_id=telegram_id,
        title=title,
        username=username or None,
        enabled=True,
    )
    await session.commit()
    return RedirectResponse(url="/", status_code=303)


@router.post("/channels/{channel_id}/toggle")
async def toggle_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    service = ChannelService(session)
    channel = await service.get_channel(channel_id)
    if channel:
        await service.set_channel_enabled(channel_id, not channel.enabled)
    return RedirectResponse(url="/", status_code=303)


@router.post("/channels/{channel_id}/delete")
async def delete_channel(
    channel_id: int,
    session: AsyncSession = Depends(get_db_session),
):
    await ChannelService(session).delete_channel(channel_id)
    return RedirectResponse(url="/", status_code=303)
