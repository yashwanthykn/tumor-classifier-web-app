"""CRUD operations for conversations and messages.

Follows the same pattern as app/crud/prediction.py:
- Accept db: Session
- Query / create / delete
- Return the ORM object(s)
"""

import json
from datetime import datetime, timezone
from typing import List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import update

from app.database.models import Conversation, Message, MessageRole


# ── Conversation CRUD ────────────────────────────────────────────────


def create_conversation(
    db: Session,
    user_id: int,
    first_message: str,
    conversation_id: Optional[str] = None,
) -> Conversation:
    """Create a new conversation with a title derived from the first message."""
    # Truncate first message to ~50 chars for the title
    title = first_message[:50].strip()
    if len(first_message) > 50:
        title += "..."

    kwargs = {
        "user_id": user_id,
        "title": title,
    }
    # Allow caller to specify ID (e.g. from frontend), otherwise let default generate it
    if conversation_id:
        kwargs["id"] = conversation_id

    db_conversation = Conversation(**kwargs)
    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)
    return db_conversation


def get_conversation(
    db: Session,
    conversation_id: str,
    user_id: int,
) -> Optional[Conversation]:
    """Get a single conversation by ID, scoped to the user for authorization."""
    return (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .first()
    )


def list_user_conversations(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
) -> List[Conversation]:
    """List all conversations for a user, newest first."""
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def delete_conversation(
    db: Session,
    conversation_id: str,
    user_id: int,
) -> bool:
    """Delete a conversation and all its messages (cascade).

    Returns True if deleted, False if not found.
    """
    conversation = get_conversation(db, conversation_id, user_id)
    if conversation is None:
        return False
    db.delete(conversation)
    db.commit()
    return True


# ── Message CRUD ─────────────────────────────────────────────────────


def save_message(
    db: Session,
    conversation_id: str,
    role: MessageRole,
    content: str,
    tool_name: Optional[str] = None,
    tool_input: Optional[Any] = None,
    tool_result: Optional[Any] = None,
    token_count: Optional[int] = None,
) -> Message:
    """Save a message to the database and touch conversation.updated_at."""
    db_message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        tool_name=tool_name,
        tool_input=json.dumps(tool_input) if tool_input else None,
        tool_result=json.dumps(tool_result) if tool_result else None,
        token_count=token_count,
    )
    db.add(db_message)

    # Touch updated_at on the parent conversation.
    # SQLAlchemy's onupdate only fires when a column on the row itself changes,
    # not when a child row is inserted, so we do it manually.
    db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(updated_at=datetime.now(timezone.utc))
    )

    db.commit()
    db.refresh(db_message)
    return db_message


def get_conversation_messages(
    db: Session,
    conversation_id: str,
    user_id: int,
) -> List[Message]:
    """Get all messages for a conversation, ordered chronologically.

    Joins through Conversation to verify user ownership.
    """
    return (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
        .order_by(Message.created_at.asc())
        .all()
    )
