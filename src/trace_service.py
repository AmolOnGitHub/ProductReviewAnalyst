from __future__ import annotations

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session


from src.models import Conversation, MessageTrace
def fetch_recent_traces(db, limit: int = 50):
    return (
        db.query(MessageTrace)
        .order_by(MessageTrace.created_at.desc())
        .limit(limit)
        .all()
    )


def get_or_create_conversation(db: Session, *, user_id: int, title: str | None = None) -> Conversation:
    # 1 active conversation per Streamlit session
    conv = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .first()
    )
    if conv:
        return conv

    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def log_trace(
    db: Session,
    *,
    conversation_id: int,
    user_id: int,
    user_query: str,
    prompt_payload: Optional[Dict[str, Any]] = None,
    retrieval_payload: Optional[Dict[str, Any]] = None,
    response_payload: Optional[Dict[str, Any]] = None,
    plot_payload: Optional[Dict[str, Any]] = None,
) -> MessageTrace:
    row = MessageTrace(
        conversation_id=conversation_id,
        user_id=user_id,
        user_query=user_query,
        prompt_payload=prompt_payload,
        retrieval_payload=retrieval_payload,
        response_payload=response_payload,
        plot_payload=plot_payload,
    )
    
    db.add(row)
    db.commit()
    db.refresh(row)
    return row