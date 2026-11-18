"""ORM models.

Privacy by design: we store ONLY metadata (token counts, model names, tool names,
error flags, hashed file paths). Prompt and response text is never stored.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user: Mapped[str] = mapped_column(String(64), index=True)
    project: Mapped[str] = mapped_column(String(64), default="unknown")
    source: Mapped[str] = mapped_column(String(32), default="claude_code")  # claude_code | api | simulated
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    task_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # only known for simulated data
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[datetime] = mapped_column(DateTime)

    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Turn.idx"
    )


class Turn(Base):
    """One model call (one assistant response) inside a session."""

    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)  # uncached input
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_creation_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_errors: Mapped[int] = mapped_column(Integer, default=0)
    tool_names: Mapped[list] = mapped_column(JSON, default=list)
    # [{"file": <sha256 prefix>, "tokens": <estimated size of what was read>}]
    file_reads: Mapped[list] = mapped_column(JSON, default=list)

    session: Mapped[AgentSession] = relationship(back_populates="turns")

    @property
    def context_tokens(self) -> int:
        """Total prompt size sent on this call (what grows as a chat gets longer)."""
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def total_tokens(self) -> int:
        return self.context_tokens + self.output_tokens


class Label(Base):
    """Human verdict on a finding — used to measure how accurate each waste rule is."""

    __tablename__ = "labels"
    __table_args__ = (UniqueConstraint("session_id", "rule", name="uq_label_session_rule"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    rule: Mapped[str] = mapped_column(String(32))
    is_waste: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
