"""Compat re-exports — digest package now fronts EventPipeline."""

from app.services.events.pipeline import EventPipeline, NewsService, ProcessResult

__all__ = ["EventPipeline", "NewsService", "ProcessResult"]
