"""Chat service: sessions, messages, conversation context, preview execution."""
from __future__ import annotations

import secrets

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFound, ValidationFailed
from app.core.json_utils import json_safe_tree
from app.models.base import utcnow
from app.models.chat import ChatMessage, ChatSession, ExecutionHistory
from app.pipeline.orchestrator import orchestrator
from app.pipeline.types import ExecutionPlan, PipelineContext
from app.schemas.api import ChatRequest, ChatTurnOut
from app.schemas.response import BeelineResponse


class ChatService:
    # ------------------------------------------------------------- sessions
    async def list_sessions(self, db: AsyncSession, user_id: str, include_archived: bool,
                            search: str | None) -> list[dict]:
        stmt = select(
            ChatSession,
            select(func.count(ChatMessage.id))
            .where(ChatMessage.session_id == ChatSession.id)
            .scalar_subquery(),
        ).where(ChatSession.user_id == user_id)
        if not include_archived:
            stmt = stmt.where(ChatSession.is_archived.is_(False))
        if search:
            stmt = stmt.where(ChatSession.title.ilike(f"%{search}%"))
        stmt = stmt.order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc())
        rows = (await db.execute(stmt)).all()
        return [
            {**{c: getattr(s, c) for c in (
                "id", "title", "is_pinned", "is_archived", "is_shared",
                "share_token", "created_at", "updated_at",
            )}, "message_count": count}
            for s, count in rows
        ]

    async def get_session(self, db: AsyncSession, session_id: str) -> ChatSession:
        session = await db.get(ChatSession, session_id)
        if not session:
            raise NotFound("Chat session not found")
        return session

    async def update_session(self, db: AsyncSession, session_id: str, updates: dict) -> ChatSession:
        session = await self.get_session(db, session_id)
        for key, value in updates.items():
            if value is not None and hasattr(session, key):
                setattr(session, key, value)
        if updates.get("is_shared") and not session.share_token:
            session.share_token = secrets.token_urlsafe(24)
        return session

    async def delete_session(self, db: AsyncSession, session_id: str) -> None:
        session = await self.get_session(db, session_id)
        await db.delete(session)

    async def list_messages(self, db: AsyncSession, session_id: str) -> list[ChatMessage]:
        await self.get_session(db, session_id)
        return list((
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            )
        ).scalars())

    # ------------------------------------------------------------- turns
    async def handle_turn(self, db: AsyncSession, request: ChatRequest,
                          user_id: str = "default") -> ChatTurnOut:
        if request.execute_preview_id:
            return await self._execute_preview(db, request, user_id)

        effective_message = (request.message or "").strip() or (request.clarification_answer or "").strip()
        if not effective_message:
            raise ValidationFailed("Message must not be empty")
        request = request.model_copy(update={"message": effective_message})

        session = await self._ensure_session(db, request, user_id)
        ctx = await self._build_context(db, session, request, user_id)

        db.add(ChatMessage(session_id=session.id, role="user", content=request.message))
        response = await orchestrator.run(ctx, db)
        message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=response.summary,
            response_payload=json_safe_tree(response.model_dump()),
            execution_id=response.execution_id,
        )
        db.add(message)
        session.updated_at = utcnow()
        await db.flush()
        await db.commit()
        return ChatTurnOut(session_id=session.id, message_id=message.id, response=response)

    async def _execute_preview(self, db: AsyncSession, request: ChatRequest,
                               user_id: str) -> ChatTurnOut:
        """User confirmed a previewed query - execute the stored SQL as-is."""
        history = await db.get(ExecutionHistory, request.execute_preview_id)
        if not history or history.status != "preview":
            raise NotFound("No pending preview found for this id")
        session = await self.get_session(db, history.session_id) if history.session_id else None

        ctx = PipelineContext(
            prompt=history.prompt,
            session_id=history.session_id,
            user_id=user_id,
            connector_id=history.connector_id,
            execution_id=history.id,
        )
        ctx.sql = history.generated_sql
        ctx.optimized_sql = history.optimized_sql
        ctx.cost = history.cost_estimate or {}
        ctx.confidence = history.confidence or ctx.confidence
        if history.execution_plan:
            ctx.plan = ExecutionPlan(**history.execution_plan)
        if history.intent:
            from app.pipeline.types import Intent
            ctx.intent = Intent(**{k: v for k, v in history.intent.items()
                                   if k in Intent.model_fields})

        response = await orchestrator.execute_and_respond(ctx, db, history)
        response.execution_id = history.id
        orchestrator._record_history(ctx, history, response)

        message = ChatMessage(
            session_id=history.session_id,
            role="assistant",
            content=response.summary,
            response_payload=json_safe_tree(response.model_dump()),
            execution_id=history.id,
        )
        db.add(message)
        if session:
            session.updated_at = utcnow()
        await db.flush()
        await db.commit()
        return ChatTurnOut(
            session_id=history.session_id or "",
            message_id=message.id,
            response=response,
        )

    async def _ensure_session(self, db: AsyncSession, request: ChatRequest,
                              user_id: str) -> ChatSession:
        if request.session_id:
            return await self.get_session(db, request.session_id)
        title = request.message.strip()[:60] or "New chat"
        session = ChatSession(title=title, user_id=user_id, connector_id=request.connector_id)
        db.add(session)
        await db.flush()
        return session

    async def _build_context(self, db: AsyncSession, session: ChatSession,
                             request: ChatRequest, user_id: str) -> PipelineContext:
        settings = get_settings()
        max_history = settings.get("pipeline.context.max_history_messages", 12)
        messages = await self.list_messages(db, session.id)
        history = [
            {"role": m.role, "content": m.content}
            for m in messages[-max_history:] if m.content
        ]
        if session.context_summary:
            history.insert(0, {"role": "system", "content": f"Summary: {session.context_summary}"})

        ctx = PipelineContext(
            prompt=request.message,
            session_id=session.id,
            user_id=user_id,
            connector_id=request.connector_id or session.connector_id,
            history=history,
            clarification_answer=request.clarification_answer,
        )
        # follow-up support: give the planner the previous successful plan/sql
        last_exec = (
            await db.execute(
                select(ExecutionHistory)
                .where(
                    ExecutionHistory.session_id == session.id,
                    ExecutionHistory.status.in_(["executed", "preview"]),
                )
                .order_by(ExecutionHistory.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if last_exec and last_exec.execution_plan:
            ctx.previous_plan = ExecutionPlan(**last_exec.execution_plan)
            ctx.previous_sql = last_exec.optimized_sql
        return ctx


chat_service = ChatService()
