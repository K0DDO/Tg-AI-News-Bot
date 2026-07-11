from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("user_id", "news_id", name="uq_reactions_user_id_news_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    news_id: Mapped[int] = mapped_column(
        ForeignKey("news.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reaction_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="reactions")
    news = relationship("News", back_populates="reactions")

    def __repr__(self) -> str:
        return (
            f"<Reaction id={self.id} user_id={self.user_id} "
            f"news_id={self.news_id} type={self.reaction_type}>"
        )
