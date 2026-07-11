from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    messages = relationship("Message", back_populates="channel")
    user_links = relationship(
        "UserChannel",
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Channel id={self.id} username={self.username!r} enabled={self.enabled}>"


class UserChannel(Base):
    """Many-to-many: which channels a bot user follows / manages."""

    __tablename__ = "user_channels"
    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_user_channels_user_id_channel_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="channels")
    channel = relationship("Channel", back_populates="user_links")
