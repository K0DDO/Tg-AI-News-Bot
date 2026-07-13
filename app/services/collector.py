"""Thin wrapper over Telethon ingest for architecture naming."""

from __future__ import annotations

from app.parser import ChannelFetcher, MessageRepository, create_telegram_client


class TelegramCollectorService:
    """Level-1 collector: fills TelegramPost/Message rows only."""

    def __init__(self, session, client=None) -> None:
        self._session = session
        self._client = client or create_telegram_client()
        self._repo = MessageRepository(session)
        self._fetcher = ChannelFetcher(self._client, self._repo)

    @property
    def client(self):
        return self._client

    @property
    def fetcher(self) -> ChannelFetcher:
        return self._fetcher

    @property
    def messages(self) -> MessageRepository:
        return self._repo
