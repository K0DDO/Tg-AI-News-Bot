from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import MessageStatus


class Message(Base):
    """Raw Telegram message as ingested by the parser."""

    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "telegram_message_id",
            name="uq_messages_channel_id_telegram_message_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=MessageStatus.RAW.value,
        server_default=MessageStatus.RAW.value,
        nullable=False,
        index=True,
    )
    filter_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    channel = relationship("Channel", back_populates="messages")
    news_sources = relationship("NewsSource", back_populates="message")

    def __repr__(self) -> str:
        return f"<Message id={self.id} channel_id={self.channel_id} status={self.status}>"
