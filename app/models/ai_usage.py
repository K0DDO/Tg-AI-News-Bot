"""Track AI provider calls for admin stats (provider-agnostic)."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AiUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
