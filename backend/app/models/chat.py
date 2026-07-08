"""Chat sessions, messages, and execution history."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TimestampMixin


class ChatSession(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_sessions"

    title: Mapped[str] = mapped_column(String(255), default="New chat")
    user_id: Mapped[str] = mapped_column(String(64), default="default", index=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    context_summary: Mapped[str | None] = mapped_column(Text)  # auto-summary of long chats
    connector_id: Mapped[str | None] = mapped_column(String(64))

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base, IdMixin, TimestampMixin):
    __tablename__ = "chat_messages"

    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | clarification
    content: Mapped[str | None] = mapped_column(Text)          # user text or assistant summary
    response_payload: Mapped[dict | None] = mapped_column(JSON)  # full structured BeelineResponse
    execution_id: Mapped[str | None] = mapped_column(ForeignKey("execution_history.id"))

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class ExecutionHistory(Base, IdMixin, TimestampMixin):
    """Every pipeline run: full traceability from prompt to result."""

    __tablename__ = "execution_history"

    session_id: Mapped[str | None] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(64), default="default")
    connector_id: Mapped[str | None] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    refined_prompt: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[dict | None] = mapped_column(JSON)
    execution_plan: Mapped[dict | None] = mapped_column(JSON)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    optimized_sql: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    # pending|clarification|preview|executed|blocked|failed|cancelled
    row_count: Mapped[int | None] = mapped_column(Integer)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    cost_estimate: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[dict | None] = mapped_column(JSON)  # business/metadata/sql/overall
    warnings: Mapped[list | None] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(String(128))
    llm_provider: Mapped[str | None] = mapped_column(String(64))
    token_usage: Mapped[dict | None] = mapped_column(JSON)
    tables_used: Mapped[list | None] = mapped_column(JSON, default=list)
    reused_query_id: Mapped[str | None] = mapped_column(String(32))  # query-library reuse
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Feedback(Base, IdMixin, TimestampMixin):
    __tablename__ = "feedback"

    execution_id: Mapped[str | None] = mapped_column(ForeignKey("execution_history.id"), index=True)
    message_id: Mapped[str | None] = mapped_column(String(32))
    user_id: Mapped[str] = mapped_column(String(64), default="default")
    rating: Mapped[str] = mapped_column(String(8))  # up | down
    category: Mapped[str | None] = mapped_column(String(32))  # incorrect_sql|wrong_data|slow|other
    comment: Mapped[str | None] = mapped_column(Text)
    corrected_sql: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|reviewed|applied
    learning: Mapped[float | None] = mapped_column(Float)  # weight applied to future retrieval
