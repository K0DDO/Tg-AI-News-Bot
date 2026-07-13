"""Deprecated path — implementation lives in app.services.events.pipeline."""

from app.services.events.pipeline import EventPipeline, NewsService, ProcessResult

__all__ = ["EventPipeline", "NewsService", "ProcessResult"]
