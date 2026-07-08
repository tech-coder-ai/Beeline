"""Chat API: conversational turns, sessions, previews."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.api import (
    ChatMessageOut,
    ChatRequest,
    ChatSessionOut,
    ChatTurnOut,
    SessionUpdate,
)
from app.services.chat import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatTurnOut)
async def send_message(request: ChatRequest, db: AsyncSession = Depends(get_db)) -> ChatTurnOut:
    """Run a conversational turn through the NL->SQL pipeline."""
    return await chat_service.handle_turn(db, request)


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(include_archived: bool = False, search: str | None = None,
                        db: AsyncSession = Depends(get_db)):
    return await chat_service.list_sessions(db, "default", include_archived, search)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    return await chat_service.list_messages(db, session_id)


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def update_session(session_id: str, update: SessionUpdate,
                         db: AsyncSession = Depends(get_db)):
    session = await chat_service.update_session(db, session_id,
                                                update.model_dump(exclude_none=True))
    await db.commit()
    return ChatSessionOut(
        id=session.id, title=session.title, is_pinned=session.is_pinned,
        is_archived=session.is_archived, is_shared=session.is_shared,
        share_token=session.share_token, created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    await chat_service.delete_session(db, session_id)
    await db.commit()
    return {"deleted": session_id}
