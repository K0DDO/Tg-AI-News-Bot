"""Full Knowledge Graph rebuild with progress + cooperative cancel."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session_factory
from app.health import record_admin_log
from app.models import Edge, Event, EventNode, Node
from app.services.events.consolidate import EventConsolidateService
from app.services.knowledge.service import KnowledgeGraphService

logger = logging.getLogger(__name__)


@dataclass
class GraphRebuildProgress:
    status: str = "idle"  # idle|running|stopping|done|error|cancelled
    phase: str = ""
    percent: int = 0
    processed: int = 0
    total: int = 0
    merged: int = 0
    unique_events: int = 0
    duplicates_found: int = 0
    nodes: int = 0
    edges: int = 0
    linked_events: int = 0
    message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_STATE = GraphRebuildProgress()
_STOP = False
_LOCK = asyncio.Lock()
_TASK: asyncio.Task | None = None


def get_rebuild_progress() -> GraphRebuildProgress:
    return _STATE


def request_stop_rebuild() -> bool:
    """Ask a running rebuild to stop at the next checkpoint."""
    global _STOP
    if _STATE.status == "running":
        _STOP = True
        _STATE.status = "stopping"
        _STATE.message = "Остановка…"
        return True
    return False


def _should_stop() -> bool:
    return _STOP


def _set_progress(**kwargs: Any) -> None:
    for k, v in kwargs.items():
        if hasattr(_STATE, k):
            setattr(_STATE, k, v)
    phase = _STATE.phase
    if _STATE.total > 0 and phase in {"consolidate", "relink"}:
        base = 10 if phase == "consolidate" else 55
        span = 45 if phase == "consolidate" else 40
        frac = min(1.0, _STATE.processed / max(1, _STATE.total))
        _STATE.percent = min(99, int(base + span * frac))
    elif phase == "wipe":
        _STATE.percent = 5
    elif phase == "seed":
        _STATE.percent = 8
    elif phase == "done":
        _STATE.percent = 100


async def start_full_rebuild(*, force: bool = False) -> GraphRebuildProgress:
    """Launch rebuild in background (own DB sessions). Returns current state."""
    global _TASK, _STOP
    async with _LOCK:
        if _STATE.status == "running" and not force:
            return _STATE
        if _TASK and not _TASK.done():
            if not force:
                return _STATE
            request_stop_rebuild()
            try:
                await asyncio.wait_for(asyncio.shield(_TASK), timeout=2)
            except Exception:
                _TASK.cancel()
        _STOP = False
        _STATE.status = "running"
        _STATE.phase = "starting"
        _STATE.percent = 0
        _STATE.processed = 0
        _STATE.total = 0
        _STATE.merged = 0
        _STATE.unique_events = 0
        _STATE.duplicates_found = 0
        _STATE.linked_events = 0
        _STATE.message = "Запуск полной пересборки…"
        _STATE.started_at = datetime.now(timezone.utc).isoformat()
        _STATE.finished_at = None
        _STATE.last_error = None
        _TASK = asyncio.create_task(_run_full_rebuild(), name="kg_full_rebuild")
        return _STATE


async def _run_full_rebuild() -> None:
    global _STOP
    factory = get_session_factory()
    try:
        _set_progress(phase="wipe", message="Очистка связей графа…", percent=3)
        async with factory() as session:
            await _wipe_graph(session)
            await session.commit()

        if _should_stop():
            _finish("cancelled", "Остановлено после очистки")
            return

        _set_progress(phase="seed", message="Загрузка seed-узлов…", percent=8)
        async with factory() as session:
            kg = KnowledgeGraphService(session)
            await kg.ensure_seed()
            await session.commit()

        if _should_stop():
            _finish("cancelled", "Остановлено после seed")
            return

        _set_progress(phase="consolidate", message="Объединение одинаковых событий…", percent=10)

        def on_cons(payload: dict) -> None:
            _set_progress(
                phase=str(payload.get("phase") or "consolidate"),
                processed=int(payload.get("processed") or 0),
                total=int(payload.get("total") or 0),
                merged=int(payload.get("merged") or 0),
                duplicates_found=int(payload.get("duplicates_found") or 0),
                unique_events=int(payload.get("unique_events") or 0),
                message=f"Consolidate: {payload.get('processed', 0)}/{payload.get('total', 0)}",
            )

        async with factory() as session:
            cons = EventConsolidateService(session)
            stats = await cons.consolidate_all(
                on_progress=on_cons,
                should_stop=_should_stop,
            )
            await session.commit()

        if _should_stop():
            _finish("cancelled", "Остановлено на consolidate")
            return

        _set_progress(
            merged=int(stats.get("merged") or 0),
            duplicates_found=int(stats.get("duplicates_found") or 0),
            unique_events=int(stats.get("unique_events") or 0),
        )

        _set_progress(phase="relink", message="Построение узлов и связей…", percent=55)
        async with factory() as session:
            linked = await _relink_all_events(session, should_stop=_should_stop)
            await session.commit()
            nodes = int(await session.scalar(select(func.count()).select_from(Node)) or 0)
            edges = int(await session.scalar(select(func.count()).select_from(Edge)) or 0)

        if _should_stop():
            _finish("cancelled", "Остановлено на relink")
            return

        _set_progress(
            phase="done",
            percent=100,
            linked_events=linked,
            nodes=nodes,
            edges=edges,
            message="Пересборка завершена",
        )
        _finish("done", "Пересборка завершена")
        record_admin_log(
            "INFO",
            f"KG full rebuild done merged={_STATE.merged} unique={_STATE.unique_events} "
            f"nodes={nodes} edges={edges}",
        )
    except asyncio.CancelledError:
        _finish("cancelled", "Отменено")
        raise
    except Exception as exc:
        logger.exception("KG full rebuild failed")
        _STATE.last_error = str(exc)[:200]
        _finish("error", f"Ошибка: {exc}")
        record_admin_log("ERROR", f"KG full rebuild failed: {exc}")


def _finish(status: str, message: str) -> None:
    global _STOP
    _STOP = False
    _STATE.status = status
    _STATE.message = message
    _STATE.finished_at = datetime.now(timezone.utc).isoformat()
    if status == "done":
        _STATE.percent = 100


async def _wipe_graph(session: AsyncSession) -> None:
    """Delete all graph links and graph structure (Events themselves stay)."""
    await session.execute(delete(EventNode))
    await session.execute(delete(Edge))
    await session.execute(delete(Node))
    await session.execute(
        update(Event).where(Event.status == "active").values(related_event_ids=[])
    )
    await session.flush()


async def _relink_all_events(
    session: AsyncSession,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    kg = KnowledgeGraphService(session)
    await kg.ensure_seed()
    result = await session.execute(
        select(Event)
        .where(Event.status == "active")
        .order_by(Event.updated_at.desc())
    )
    events = list(result.scalars().all())
    total = len(events)
    linked = 0
    for i, event in enumerate(events, start=1):
        if should_stop and should_stop():
            break
        await kg.ingest_event(event)
        linked += 1
        if i % 25 == 0:
            await session.commit()
            _set_progress(
                phase="relink",
                processed=i,
                total=total,
                linked_events=linked,
                message=f"Relink: {i}/{total}",
            )
    await session.flush()
    _set_progress(processed=linked, total=total, linked_events=linked)
    return linked
